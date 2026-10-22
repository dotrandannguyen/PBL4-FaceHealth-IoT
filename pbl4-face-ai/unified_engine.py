"""Three-snapshot attendance coordinator; inference and persistence use one worker.

Public events are serialized. Only update() accepts worker results and starts finalization.
Camera preview continues while inference and HTTP run in the background.
"""
from __future__ import annotations

import base64
import enum
import json
import math
import logging
import os
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.attendance_transport import AttendanceTransport
from src.runtime_config import load_environment
from src.sequence_features import SNAPSHOT_INTERVAL as STATUS_SNAPSHOT_INTERVAL, MAX_SNAPSHOT_GAP

load_environment()

CURRENT_DIR = Path(__file__).resolve().parent


class SessionState(enum.Enum):
    IDLE = "IDLE"
    CAPTURING = "CAPTURING"
    PROCESSING = "PROCESSING"
    FINALIZING = "FINALIZING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    WARMUP = "CAPTURING"
    SCANNING = "CAPTURING"


class UnifiedAttendanceEngine:
    SNAPSHOT_INTERVAL = STATUS_SNAPSHOT_INTERVAL
    TOTAL_SNAPSHOTS = 3
    COMPLETED_DISPLAY_SEC = 5.0
    ABORTED_DISPLAY_SEC = 2.5
    HARD_TIMEOUT_SEC = 6.0
    IOT_TIMEOUT_SEC = 3.5

    def __init__(self, logs_dir=None, face_threshold=0.45, *, face_engine=None,
                 status_predictor=None, analyzer=None, transport=None, clock=None, face_only=False, camera_only=False):
        if type(face_only) is not bool or type(camera_only) is not bool or (face_only and camera_only):
            raise ValueError('Choose either face_only or camera_only using boolean flags')
        self.face_only = face_only
        self.camera_only = camera_only
        if not math.isfinite(face_threshold) or not 0 < face_threshold <= 1:
            raise ValueError("Face threshold must be in (0, 1]")
        self.logs_dir = Path(logs_dir) if logs_dir is not None else CURRENT_DIR / "logs"
        self.snapshots_dir = self.logs_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_log_path = self.logs_dir / "attendance_logs.jsonl"
        self.web_api_url = os.environ.get("PBL4_WEB_API", "http://localhost:8080/api/chamcong")
        self.transport = transport or AttendanceTransport(self.logs_dir / "pending", self.web_api_url)
        if face_engine is None:
            from src.face_engine import FaceEngine
            face_engine = FaceEngine(model_name="buffalo_sc")
        if status_predictor is None and not face_only:
            from src.predict_status import StatusPredictor
            status_predictor = StatusPredictor(smoothing_window=5, max_yaw_deg=25.0)
        self.face_engine = face_engine
        self.face_threshold = face_threshold
        self.status_predictor = None if face_only else status_predictor
        self._analyzer = analyzer or self._analyze_snapshots
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._log_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="attendance")
        self._retry_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="attendance-retry")
        self._future = None
        self._retry_future = None
        self._next_retry = self._clock() + 30
        self._closed = False
        self.state = SessionState.IDLE
        self.state_enter_time = self._clock()
        self.session_start_time = 0.0
        self.session_id = None
        self.last_completed_record = None
        self._clear_session()

    def _clear_session(self):
        self.captured_frames = []
        self.captured_timestamps = []
        self.captured_sharpness = []
        self.last_capture_time = 0.0
        self.flash_timer = 0.0
        self.iot_done_received = False
        self.ai_processed = False
        self.ai2_valid = False
        self.ai2_confidence = 0.0
        self.ai2_message = "Chưa phân tích"
        self.session_status_history = []
        self.best_frame_score = -1.0
        self.best_frame_bgr = None
        self.evidence_frames = [None, None, None]
        self.face_bbox = None
        self.identified_id = None
        self.identified_name = "Chưa xác định"
        self.identity_sim = 0.0
        self.identity_matched = False
        self.iot_hr = self.iot_spo2 = self.iot_ir_avg = 0
        self.abort_reason = ""
        self.latest_face_metrics = dict(ear=0.0, mar=0.0, pitch=0.0, yaw=0.0, roll=0.0, sharpness=0.0)

    def start_session(self, ir=0):
        with self._lock:
            if self._closed or self.state != SessionState.IDLE:
                return None
            if self._future is not None and not self._future.done():
                return None
            if isinstance(ir, bool) or not isinstance(ir, (int, float)) or not math.isfinite(ir) or ir < 0:
                return None
            self._clear_session()
            if self.status_predictor is not None:
                self.status_predictor.reset()
            self.session_id = str(uuid4())
            self.occurred_at = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="milliseconds")
            self.state = SessionState.CAPTURING
            self.state_enter_time = self.session_start_time = self._clock()
            self.iot_ir_avg = ir
            return self.session_id

    def abort_session(self, reason="FINGER_REMOVED", session_id=None):
        with self._lock:
            if session_id is not None and session_id != self.session_id:
                return
            if self.state in (SessionState.CAPTURING, SessionState.PROCESSING):
                self.state = SessionState.ABORTED
                self.state_enter_time = self._clock()
                self.abort_reason = reason

    def done_session(self, hr, spo2, ir_avg=0, session_id=None):
        """Record an event only. The preview loop owns completion transitions."""
        with self._lock:
            if self.face_only or self.camera_only:
                return None
            if session_id is not None and session_id != self.session_id:
                return None
            if self.state not in (SessionState.CAPTURING, SessionState.PROCESSING) or self.iot_done_received:
                return None
            try:
                if any(isinstance(value, bool) or not isinstance(value, (int, float))
                       for value in (hr, spo2, ir_avg)):
                    return None
                values = [float(hr), float(spo2), float(ir_avg)]
                if not all(math.isfinite(x) for x in values):
                    return None
                if not (0 <= values[0] <= 300 and 0 <= values[1] <= 100 and values[2] >= 0):
                    return None
            except (ValueError, TypeError):
                return None
            self.iot_hr, self.iot_spo2, self.iot_ir_avg = values
            self.iot_done_received = True
        return None

    def update(self, frame_bgr):
        with self._lock:
            now = self._clock()
            if self._closed:
                return self._info(now)
            if self.state in (SessionState.CAPTURING, SessionState.PROCESSING):
                if now - self.session_start_time >= self.HARD_TIMEOUT_SEC:
                    self.abort_session("HARD_TIMEOUT_EXCEEDED")
            if self.state in (SessionState.COMPLETED, SessionState.ABORTED):
                duration = (self.COMPLETED_DISPLAY_SEC if self.state == SessionState.COMPLETED or self.camera_only
                            else self.ABORTED_DISPLAY_SEC)
                if now - self.state_enter_time >= duration and (self._future is None or self._future.done()):
                    self.state = SessionState.IDLE
                    self.state_enter_time = now
                    self._future = None
                    self._clear_session()
            if self.state == SessionState.CAPTURING:
                if self.captured_frames and now - self.last_capture_time > MAX_SNAPSHOT_GAP + 1e-9:
                    self.abort_session('SNAPSHOT_GAP_EXCEEDED')
                elif frame_bgr is not None and getattr(frame_bgr, "size", 1) > 0:
                    if not self.captured_frames or now - self.last_capture_time >= self.SNAPSHOT_INTERVAL:
                        self.captured_frames.append(frame_bgr.copy())
                        self.captured_timestamps.append(now - self.session_start_time)
                        self.last_capture_time = now
                        self.flash_timer = time.time()
                        if len(self.captured_frames) == self.TOTAL_SNAPSHOTS:
                            self.state = SessionState.PROCESSING
                            self.state_enter_time = now
                            self._future = self._pool.submit(self._analyzer, tuple(self.captured_frames))
            if self.state == SessionState.PROCESSING:
                if not self.ai_processed and self._future is not None and self._future.done():
                    try:
                        self._accept_analysis(self._future.result())
                    except Exception:
                        self.abort_session("AI_PROCESSING_FAILED")
                if self.state == SessionState.PROCESSING and self.ai_processed:
                    if self.face_only or self.camera_only or self.iot_done_received or now - self.session_start_time >= self.IOT_TIMEOUT_SEC:
                        self.state = SessionState.FINALIZING
                        self.state_enter_time = now
                        self._future = self._pool.submit(self._finalize_session)
            if self.state == SessionState.FINALIZING and self._future.done():
                try:
                    self.last_completed_record = self._future.result()
                    self.state = SessionState.COMPLETED
                except Exception:
                    self.state = SessionState.ABORTED
                    self.abort_reason = "PERSISTENCE_FAILED"
                self.state_enter_time = now
            if self.state == SessionState.IDLE and now >= self._next_retry:
                if self._retry_future is None or self._retry_future.done():
                    self._retry_future = self._retry_pool.submit(self._retry_pending)
                    self._next_retry = now + 30
            return self._info(now)

    def _retry_pending(self):
        results = self.transport.retry_pending()
        for event_id, result in results:
            if result.get("status") in ("success", "completed"):
                self._append_log({"event_id": event_id, "type": "sync_result", "web_result": result})
        return results

    def _append_log(self, record):
        try:
            with self._log_lock:
                with open(self.jsonl_log_path, "a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            return True
        except OSError:
            # A server ACK remains true even if this secondary journal is full.
            # The outbox receipt preserves the ACK independently of this log.
            logging.getLogger(__name__).exception("Cannot append attendance journal")
            return False

    def _info(self, now):
        return {"state": self.state, "face_only": self.face_only, "camera_only": self.camera_only, "elapsed_in_state": now - self.state_enter_time,
                "elapsed_in_session": now - self.session_start_time if self.state != SessionState.IDLE else 0.0,
                "session_id": self.session_id, "captured_count": len(self.captured_frames),
                "captured_frames": list(self.captured_frames), "flash_timer": self.flash_timer,
                "ai2_result": {"status": self.session_status_history[0], "is_valid": self.ai2_valid,
                               "confidence": self.ai2_confidence, "message": self.ai2_message,
                               "metrics": dict(self.latest_face_metrics)} if self.session_status_history else None,
                "face_bbox": self.face_bbox, "sharpness": max(0.0, self.best_frame_score),
                "identified_id": self.identified_id, "identified_name": self.identified_name,
                "identity_sim": self.identity_sim,
                "completed_record": self.last_completed_record if self.state == SessionState.COMPLETED else None,
                "abort_reason": self.abort_reason, "latest_metrics": dict(self.latest_face_metrics)}

    def _analyze_snapshots(self, frames):
        import cv2
        import numpy as np
        from src.verify import identify
        scores = [float(cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) for f in frames]
        best = int(np.argmax(scores))
        try:
            embeddings = [self.face_engine.embed(frame) for frame in frames]
            consistent = all(embedding is not None for embedding in embeddings)
            if consistent:
                consistent = all(float(np.dot(embeddings[best], embedding)) >= self.face_threshold
                                 for embedding in embeddings)
            identity = (identify(self.face_engine, frames[best], threshold=self.face_threshold,
                                 probe_embedding=embeddings[best]) if consistent else {"match": False})
        except Exception:
            identity = {"match": False}
        try:
            status = ({"status": "Unknown", "is_valid": False,
                       "message": "Chấm công khuôn mặt; chưa đánh giá thể trạng hoặc đo sinh trắc."}
                      if self.face_only else self.status_predictor.predict_status_detailed(frames))
        except Exception:
            status = {"status": "Unknown", "is_valid": False, "message": "AI 2 không phân tích được"}
        return {"scores": scores, "best": best, "identity": identity, "status": status}

    def _accept_analysis(self, result):
        best = result["best"]
        self.captured_sharpness = result["scores"]
        self.best_frame_score = result["scores"][best]
        if not all(math.isfinite(score) and score >= 0 for score in self.captured_sharpness):
            raise ValueError("Invalid frame quality score")
        self.best_frame_bgr = self.captured_frames[best]
        self.evidence_frames = [self.captured_frames[0], self.best_frame_bgr, self.captured_frames[2]]
        identity = result["identity"]
        self.identity_sim = float(identity.get("similarity", 0.0))
        if not math.isfinite(self.identity_sim):
            self.identity_sim = 0.0
        self.identity_matched = bool(identity.get("match")) and self.face_threshold <= self.identity_sim <= 1.000001
        self.identified_id = identity.get("student_id") if self.identity_matched else None
        self.identified_name = identity.get("name", "Chưa xác định") if self.identity_matched else "Chưa xác định"
        status = ({"status": "Unknown", "is_valid": False,
                   "message": "Chấm công khuôn mặt; chưa đánh giá thể trạng hoặc đo sinh trắc."}
                  if self.face_only else result["status"])
        label = status.get("status", "Unknown")
        self.ai2_valid = bool(status.get("is_valid")) and label in ("Normal", "Fatigue", "Exhausted")
        self.ai2_confidence = float(status.get("confidence", 0.0)) if self.ai2_valid else 0.0
        if not math.isfinite(self.ai2_confidence) or not 0 <= self.ai2_confidence <= 1:
            self.ai2_valid = False
            self.ai2_confidence = 0.0
        self.ai2_message = status.get("message", "")
        self.session_status_history = [label if self.ai2_valid else "Unknown"]
        for key in ("ear", "mar", "pitch", "yaw", "roll"):
            try:
                value = float(status.get("metrics", {}).get(key, 0.0))
            except (TypeError, ValueError):
                value = 0.0
            self.latest_face_metrics[key] = value if math.isfinite(value) else 0.0
        self.latest_face_metrics["sharpness"] = self.best_frame_score
        self.ai_processed = True

    def _finalize_session(self) -> Dict[str, Any]:
        """
        Tổng hợp kết quả cuối cùng từ AI 1, AI 2 và dữ liệu IoT.
        Lưu snapshot ảnh và ghi log JSONL.
        """
        import cv2

        # 1. Chốt nhãn khuôn mặt AI 2 bằng Majority Voting & Quy tắc 30% Exhausted
        if self.session_status_history:
            total_valid = len(self.session_status_history)
            counts = Counter(self.session_status_history)
            exhausted_count = counts.get("Exhausted", 0)

            # Quy tắc ưu tiên 30% để không bỏ lọt ngủ gật
            if (exhausted_count / total_valid) >= 0.30:
                ai2_final_status = "Exhausted"
            else:
                ai2_final_status = counts.most_common(1)[0][0]
        else:
            ai2_final_status = "Unknown"

        # 2. Chốt thông tin danh tính AI 1 (đã được nhận diện trong _process_3_snapshots)
        final_student_id = self.identified_id if self.identified_id else "Unknown"
        final_student_name = self.identified_name if self.identified_id else "Chưa xác định"

        # 3. Phân loại Sinh trắc học (Bio Level)
        hr = self.iot_hr
        spo2 = self.iot_spo2

        if hr <= 0 or spo2 <= 0:
            bio_level = "Bio_Missing"
        elif (hr > 115 or hr < 50) or (spo2 < 94):
            bio_level = "Bio_Danger"
        elif (100 < hr <= 115 or 50 <= hr < 60) or (94 <= spo2 < 96):
            bio_level = "Bio_Warning"
        else:
            bio_level = "Bio_Normal"

        # 4. Ma trận Hợp nhất Quyết định (Late Fusion Decision Matrix)
        if self.face_only:
            final_status = "Chỉ nhận diện khuôn mặt"
            alert_level = "YELLOW"
            recommendation = "AI 2 đang tắt trong phiên này."

        elif bio_level == "Bio_Danger":
            final_status = "Cảnh báo y tế"
            alert_level = "RED"
            recommendation = "Chỉ số tim mạch hoặc SpO2 bất thường. Cần nghỉ ngơi kiểm tra y tế ngay!"

        elif not self.ai2_valid:
            final_status = "Chưa phân tích được thể trạng"
            alert_level = "YELLOW"
            recommendation = self.ai2_message or "Cần đủ ba ảnh mặt hợp lệ để AI 2 phân tích."

        elif bio_level == "Bio_Missing":
            final_status = {'Normal': 'Bình thường', 'Fatigue': 'Mệt mỏi', 'Exhausted': 'Kiệt sức'}[ai2_final_status] + ' (AI 2)'
            alert_level = {'Normal': 'YELLOW', 'Fatigue': 'ORANGE', 'Exhausted': 'RED'}[ai2_final_status]
            recommendation = "Kết quả AI 2; chưa đo nhịp tim/SpO2."

        elif ai2_final_status == "Exhausted":
            final_status = "Kiệt sức / Buồn ngủ nặng"
            alert_level = "RED"
            recommendation = "Mắt nhắm nghiền hoặc gật gù liên tục. Cần nghỉ ngơi để đảm bảo an toàn."

        elif ai2_final_status == "Fatigue" and bio_level == "Bio_Warning":
            final_status = "Mệt mỏi thể chất"
            alert_level = "ORANGE"
            recommendation = "Có biểu hiện lờ đờ trên mặt và nhịp tim/SpO2 hơi bất thường."

        elif ai2_final_status == "Fatigue" and bio_level in ["Bio_Normal", "Bio_Missing"]:
            final_status = "Buồn ngủ / Thiếu ngủ"
            alert_level = "YELLOW"
            recommendation = "Chỉ số sinh tồn ổn định nhưng cơ mặt mệt mỏi. Khuyến nghị rửa mặt nghỉ giải lao."

        elif ai2_final_status == "Normal" and bio_level == "Bio_Warning":
            final_status = "Tỉnh táo / Căng thẳng nhẹ"
            alert_level = "YELLOW"
            recommendation = "Khuôn mặt tỉnh táo, nhịp tim hơi cao (có thể do vừa vận động hoặc căng thẳng)."

        elif ai2_final_status == "Normal" and bio_level == "Bio_Normal":
            final_status = "Đạt chuẩn sức khỏe"
            alert_level = "GREEN"
            recommendation = "Trạng thái tinh thần và chỉ số sinh tồn hoàn toàn ổn định."

        else:
            final_status = "Đang đánh giá"
            alert_level = "YELLOW"
            recommendation = "Camera chưa bắt đủ góc mặt chuẩn, ghi nhận theo chỉ số sinh trắc học."

        # 5. Lưu 3 ảnh bằng chứng chấm công
        now_str = self.occurred_at
        ts_filename = self.session_id

        # Tên 3 ảnh: _start (đầu scanning), _best (chất lượng cao nhất), _end (cuối phiên)
        evidence_labels = ["start", "best", "end"]
        evidence_paths: List[str] = []

        # evidence_frames[1] (best) có thể là best_frame_bgr
        if self.evidence_frames[1] is None and self.best_frame_bgr is not None:
            self.evidence_frames[1] = self.best_frame_bgr

        # Fallback: nếu frame nào None thì mượn từ frame có sẵn (best -> start -> end)
        fallback_frame = (
            self.best_frame_bgr
            if self.best_frame_bgr is not None
            else (self.evidence_frames[0] if self.evidence_frames[0] is not None else self.evidence_frames[2])
        )
        for i in range(3):
            if self.evidence_frames[i] is None and fallback_frame is not None:
                self.evidence_frames[i] = fallback_frame

        for idx, (label, ev_frame) in enumerate(zip(evidence_labels, self.evidence_frames)):
            filename = f"{final_student_id}_{ts_filename}_{label}.jpg"
            rel_path = f"logs/snapshots/{filename}"
            if ev_frame is not None:
                abs_path = self.snapshots_dir / filename
                if cv2.imwrite(str(abs_path), ev_frame):
                    evidence_paths.append(rel_path)
                else:
                    evidence_paths.append("")
            else:
                evidence_paths.append("")  # Frame không có thì để rỗng

        # Tương thích ngược: snapshot_path = ảnh best (index 1)
        snapshot_path_compat = evidence_paths[1] if len(evidence_paths) > 1 else ""

        logging.getLogger(__name__).info("Saved %d evidence images", sum(bool(p) for p in evidence_paths))

        # 6. Tạo gói JSON Output chuẩn
        record: Dict[str, Any] = {
            "assessment_mode": "face_only" if self.face_only else ("face_ai2" if self.camera_only else "full"),
            "timestamp": now_str,
            "event_id": self.session_id,
            "ai2_valid": self.ai2_valid,
            "ai2_confidence": self.ai2_confidence,
            "ai2_message": self.ai2_message,
            "captured_timestamps": self.captured_timestamps,
            "student_id": final_student_id,
            "student_name": final_student_name,
            "face_confidence": round(float(self.identity_sim), 4),
            "ai2_face_status": ai2_final_status,
            "face_metrics": {
                "ear": round(self.latest_face_metrics["ear"], 3),
                "mar": round(self.latest_face_metrics["mar"], 3),
                "pitch": round(self.latest_face_metrics["pitch"], 1),
                "yaw": round(self.latest_face_metrics["yaw"], 1),
                "sharpness": round(self.latest_face_metrics["sharpness"], 1),
            },
            "iot_metrics": {
                "hr": None if self.face_only or self.camera_only else hr,
                "spo2": None if self.face_only or self.camera_only else spo2,
                "bio_level": bio_level,
                "ir_avg": self.iot_ir_avg,
            },
            "fusion_result": {
                "final_status": final_status,
                "alert_level": alert_level,
                "recommendation": recommendation,
            },
            # 3 ảnh bằng chứng: [start, best, end]
            "evidence_snapshots": evidence_paths,
            # Tương thích ngược
            "snapshot_path": snapshot_path_compat,
        }

        # 8. Đồng bộ kết quả chấm công sang Web Backend qua API
        best_img = self.evidence_frames[1] if self.evidence_frames[1] is not None else self.best_frame_bgr
        web_res = self._sync_attendance_to_web(final_student_id, hr, spo2, ai2_final_status, best_img)
        act = web_res.get("action", "")
        msg = web_res.get("message", "")
        if act == "checkin":
            record["attendance_action"] = "CHECK-IN"
            record["attendance_msg"] = "Điểm danh vào ca thành công"
        elif act == "checkout":
            record["attendance_action"] = "CHECK-OUT"
            record["attendance_msg"] = "Điểm danh ra về thành công"
        elif act == "completed":
            record["attendance_action"] = "DA_CHECK_OUT"
            record["attendance_msg"] = "Hôm nay bạn đã hoàn thành ca làm việc"
        else:
            record["attendance_action"] = "PENDING" if web_res.get("status") == "pending" else "NOT_RECORDED"
            record["attendance_msg"] = msg or "Chưa được Web xác nhận"
        record["web_result"] = web_res

        record["local_log_saved"] = True
        if not self._append_log(record):
            record["local_log_saved"] = False
        return record

    def _sync_attendance_to_web(self, student_id, hr, spo2, ai2_status, best_frame):
        if not self.identity_matched or not student_id or student_id == "Unknown":
            return {"action": "none", "status": "no_identity", "message": "Chưa xác định danh tính"}
        match = re.fullmatch(r"(?:SV|NV)?([0-9]+)", str(student_id), flags=re.IGNORECASE)
        if not match or int(match.group(1)) <= 0:
            return {"action": "none", "status": "no_id", "message": "Mã nhân viên không hợp lệ"}
        image = None
        if best_frame is not None:
            import cv2
            success, buffer = cv2.imencode(".jpg", best_frame)
            if success:
                image = base64.b64encode(buffer.tobytes()).decode("ascii")
        payload = {"event_id": self.session_id, "occurred_at": self.occurred_at,
                   "MaNV": int(match.group(1)), "MaTB": int(os.environ.get("PBL4_DEVICE_ID", "1")),
                   "NhipTim": hr if hr > 0 else None, "SpO2": spo2 if spo2 > 0 else None,
                   "TrangThai": ai2_status, "image": image}
        return self.transport.send(payload)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        # Do not cancel an already submitted finalization when the user quits.
        self._pool.shutdown(wait=True, cancel_futures=False)
        self._retry_pool.shutdown(wait=True, cancel_futures=False)
        if self.status_predictor is not None:
            self.status_predictor.close()
