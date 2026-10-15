"""
unified_engine.py — Core Engine hợp nhất AI 1 (Face Recognition) & AI 2 (Status Detection)
kết hợp dữ liệu Sinh trắc học IoT (MAX30102 qua ESP32).

Kiến trúc:
  - Máy trạng thái (State Machine): IDLE -> WARMUP (1.2s) -> SCANNING -> COMPLETED / ABORTED
  - Xử lý bất đồng bộ (Multi-threading): AI 2 chạy liên tục trên Main Thread (30 FPS),
    AI 1 (InsightFace) chạy ngầm trên Worker Thread để chống nghẽn CPU và sụt FPS.
  - Bộ lọc chất lượng Frame (Sharpness Laplacian + Head Pose)
  - Ma trận hợp nhất quyết định (Late Fusion Decision Matrix) 7 mức ưu tiên.
"""

import sys
import time
import json
import enum
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, Future

import cv2
import numpy as np

# Đảm bảo đường dẫn import src luôn đúng
CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from src.face_engine import FaceEngine
    from src.verify import load_db, identify
    from src.predict_status import StatusPredictor
except ImportError:
    from face_engine import FaceEngine  # type: ignore
    from verify import load_db, identify  # type: ignore
    from predict_status import StatusPredictor  # type: ignore


class SessionState(enum.Enum):
    IDLE = "IDLE"
    WARMUP = "WARMUP"
    SCANNING = "SCANNING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class UnifiedAttendanceEngine:
    """
    Bộ điều phối hợp nhất Chấm công Thông minh (Face Recognition + Status + Bio IoT).
    """

    WARMUP_DURATION = 1.2      # Giây khởi động ổn định vị trí & tín hiệu ngón tay
    COMPLETED_DISPLAY_SEC = 3.0 # Giữ màn hình kết quả trước khi về IDLE
    ABORTED_DISPLAY_SEC = 2.5   # Giữ màn hình lỗi trước khi về IDLE
    HARD_TIMEOUT_SEC = 7.0      # Giới hạn thời gian tối đa của 1 phiên

    def __init__(
        self,
        logs_dir: Optional[Path] = None,
        face_threshold: float = 0.45,
    ):
        self.logs_dir = logs_dir or (CURRENT_DIR / "logs")
        self.snapshots_dir = self.logs_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_log_path = self.logs_dir / "attendance_logs.jsonl"

        # Khởi tạo AI 1 & AI 2
        print("[UnifiedEngine] Đang nạp mô hình AI 1 (InsightFace buffalo_sc)...")
        self.face_engine = FaceEngine(model_name="buffalo_sc")
        self.face_threshold = face_threshold
        # Load cache DB embeddings một lần
        load_db(force_reload=True)

        print("[UnifiedEngine] Đang nạp mô hình AI 2 (MediaPipe Face Mesh + Random Forest)...")
        self.status_predictor = StatusPredictor(smoothing_window=5, max_yaw_deg=25.0)

        # Worker thread cho AI 1 (nhận diện khuôn mặt 1:N)
        self.thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="AI1_Worker")
        self._worker_future: Optional[Future] = None
        self._worker_running = False

        # Quản lý State Machine
        self.state = SessionState.IDLE
        self.state_enter_time = time.time()
        self.session_start_time = 0.0

        # Bộ nhớ đệm phiên chấm công
        self.session_status_history: List[str] = []
        self.best_frame_score = -1.0
        self.best_frame_bgr: Optional[np.ndarray] = None
        self.latest_face_metrics: Dict[str, float] = {
            "ear": 0.0, "mar": 0.0, "pitch": 0.0, "yaw": 0.0, "sharpness": 0.0
        }

        # Kết quả AI 1 trong phiên
        self.identified_id: Optional[str] = None
        self.identified_name: str = "Chưa xác định"
        self.identity_sim: float = 0.0
        self.identity_matched: bool = False

        # Dữ liệu IoT
        self.iot_hr: int = 0
        self.iot_spo2: int = 0
        self.iot_ir_avg: int = 0
        self.abort_reason: str = ""

        # Kết quả cuối cùng
        self.last_completed_record: Optional[Dict[str, Any]] = None

    def start_session(self, ir: int = 0) -> None:
        """
        Nhận sự kiện START_SESSION từ ESP32 hoặc Mock Trigger.
        """
        if self.state in [SessionState.WARMUP, SessionState.SCANNING]:
            return  # Đang trong phiên, bỏ qua trigger trùng

        now = time.time()
        self.state = SessionState.WARMUP
        self.state_enter_time = now
        self.session_start_time = now

        # Reset dữ liệu đệm phiên
        self.session_status_history.clear()
        self.best_frame_score = -1.0
        self.best_frame_bgr = None
        self.identified_id = None
        self.identified_name = "Scanning Identity..."
        self.identity_sim = 0.0
        self.identity_matched = False
        self.iot_hr = 0
        self.iot_spo2 = 0
        self.iot_ir_avg = ir
        self.abort_reason = ""
        self.status_predictor.reset()

        print(f"[UnifiedEngine] 🚀 BẮT ĐẦU PHIÊN (START_SESSION) | IR={ir}")

    def abort_session(self, reason: str = "FINGER_REMOVED") -> None:
        """
        Nhận sự kiện ABORT_SESSION (người dùng rút tay ra sớm hoặc lỗi kết nối).
        """
        if self.state in [SessionState.WARMUP, SessionState.SCANNING]:
            self.state = SessionState.ABORTED
            self.state_enter_time = time.time()
            self.abort_reason = reason
            print(f"[UnifiedEngine] ⚠️ HỦY PHIÊN (ABORT_SESSION) | Lý do: {reason}")

    def done_session(self, hr: int, spo2: int, ir_avg: int = 0) -> Optional[Dict[str, Any]]:
        """
        Nhận sự kiện DONE_SESSION từ ESP32 chứa trung vị HR & SpO2.
        Kích hoạt Late Fusion và chốt kết quả.
        """
        if self.state not in [SessionState.WARMUP, SessionState.SCANNING]:
            return None

        self.iot_hr = hr
        self.iot_spo2 = spo2
        self.iot_ir_avg = ir_avg
        print(f"[UnifiedEngine] 🏁 NHẬN DONE_SESSION | HR={hr}, SpO2={spo2}, IR={ir_avg}")

        record = self._finalize_session()
        self.state = SessionState.COMPLETED
        self.state_enter_time = time.time()
        self.last_completed_record = record
        return record

    def update(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Hàm xử lý trên từng frame camera (Main Thread).
        Đảm bảo MediaPipe + UI chạy mượt 25-30 FPS.
        """
        now = time.time()
        elapsed_in_state = now - self.state_enter_time
        elapsed_in_session = now - self.session_start_time if self.session_start_time > 0 else 0.0

        # Kiểm tra Hard Timeout cho phiên đang quét
        if self.state in [SessionState.WARMUP, SessionState.SCANNING]:
            if elapsed_in_session >= self.HARD_TIMEOUT_SEC:
                self.abort_session(reason="HARD_TIMEOUT_EXCEEDED")

        # Kiểm tra tự động chuyển trạng thái theo thời gian
        if self.state == SessionState.WARMUP:
            if elapsed_in_state >= self.WARMUP_DURATION:
                self.state = SessionState.SCANNING
                self.state_enter_time = now
                print("[UnifiedEngine] 🔍 Chuyển sang SCANNING — Thu thập AI 1 & AI 2 song song")

        elif self.state == SessionState.COMPLETED:
            if elapsed_in_state >= self.COMPLETED_DISPLAY_SEC:
                self._reset_to_idle()

        elif self.state == SessionState.ABORTED:
            if elapsed_in_state >= self.ABORTED_DISPLAY_SEC:
                self._reset_to_idle()

        # Kiểm tra kết quả từ Worker Thread (AI 1)
        if self._worker_future is not None and self._worker_future.done():
            try:
                res = self._worker_future.result()
                if res and res.get("match"):
                    self.identified_id = res.get("student_id")
                    self.identified_name = res.get("name", "Unknown")
                    self.identity_sim = res.get("similarity", 0.0)
                    self.identity_matched = True
                elif res:
                    # Cập nhật kết quả tốt nhất dù chưa vượt threshold
                    if res.get("similarity", 0.0) > self.identity_sim:
                        self.identity_sim = res.get("similarity", 0.0)
                        if self.identified_id is None:
                            self.identified_name = "Không xác định"
            except Exception as e:
                print(f"[UnifiedEngine] Lỗi Worker AI 1: {e}")
            finally:
                self._worker_future = None

        # -------------------------------------------------------------
        # XỬ LÝ THEO TRẠNG THÁI HIỆN TẠI
        # -------------------------------------------------------------
        ai2_res: Dict[str, Any] = {}
        sharpness_val = 0.0
        face_bbox: Optional[Tuple[int, int, int, int]] = None

        if self.state == SessionState.IDLE:
            # CPU nghỉ: Không chạy MediaPipe hay InsightFace
            return {
                "state": self.state,
                "elapsed_in_state": elapsed_in_state,
                "elapsed_in_session": 0.0,
                "ai2_result": None,
                "face_bbox": None,
                "sharpness": 0.0,
                "identified_id": None,
                "identified_name": "Đặt ngón tay lên cảm biến để bắt đầu chấm công",
                "identity_sim": 0.0,
                "completed_record": None,
                "abort_reason": "",
            }

        # Trạng thái WARMUP hoặc SCANNING: Chạy MediaPipe trích xuất cử động
        ai2_res = self.status_predictor.predict_frame(frame_bgr)
        pts = ai2_res.get("pts")
        h, w = frame_bgr.shape[:2]

        if pts is not None and len(pts) > 0:
            x_min, y_min = np.min(pts, axis=0)
            x_max, y_max = np.max(pts, axis=0)
            # Thêm lề padding 10%
            pad_w = (x_max - x_min) * 0.1
            pad_h = (y_max - y_min) * 0.1
            bx1 = max(0, int(x_min - pad_w))
            by1 = max(0, int(y_min - pad_h))
            bx2 = min(w, int(x_max + pad_w))
            by2 = min(h, int(y_max + pad_h))
            face_bbox = (bx1, by1, bx2, by2)
            face_w = bx2 - bx1

            # Tính độ sắc nét ROI khuôn mặt
            roi = frame_bgr[by1:by2, bx1:bx2]
            if roi.size > 0:
                roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                sharpness_val = float(cv2.Laplacian(roi_gray, cv2.CV_64F).var())

            # Cập nhật metrics tức thời
            self.latest_face_metrics = {
                "ear": float(ai2_res.get("ear", 0.0)),
                "mar": float(ai2_res.get("mar", 0.0)),
                "pitch": float(ai2_res.get("pitch", 0.0)),
                "yaw": float(ai2_res.get("yaw", 0.0)),
                "sharpness": sharpness_val,
            }

            # Giai đoạn WARMUP & SCANNING: Thu thập dữ liệu AI 1 & AI 2
            if self.state in [SessionState.WARMUP, SessionState.SCANNING]:
                raw_status = ai2_res.get("status")
                yaw = abs(self.latest_face_metrics["yaw"])

                # 1. Thu thập nhãn AI 2 nếu mặt nhìn thẳng (chỉ ghi nhận trong SCANNING)
                if self.state == SessionState.SCANNING and ai2_res.get("is_valid") and yaw <= 25.0:
                    if raw_status in ["Normal", "Fatigue", "Exhausted"]:
                        self.session_status_history.append(raw_status)

                # 2. Cập nhật Frame tốt nhất dựa trên điểm chất lượng tương đối
                quality_score = (sharpness_val + 1.0) * max(0.1, 1.0 - yaw / 45.0)
                if self.best_frame_bgr is None or quality_score > self.best_frame_score:
                    self.best_frame_score = quality_score
                    self.best_frame_bgr = frame_bgr.copy()

                # 3. Kích hoạt Worker AI 1 liên tục trong SCANNING khi Worker đang rảnh
                # Không chặn cứng độ nét 45 (vì webcam laptop trong phòng thường chỉ đạt 15-30)
                if (
                    self.state == SessionState.SCANNING
                    and self._worker_future is None
                    and not self.identity_matched
                    and yaw <= 30.0
                    and face_w >= 50
                ):
                    frame_to_send = frame_bgr.copy()
                    self._worker_future = self.thread_pool.submit(
                        self._run_ai1_worker, frame_to_send
                    )

        return {
            "state": self.state,
            "elapsed_in_state": elapsed_in_state,
            "elapsed_in_session": elapsed_in_session,
            "ai2_result": ai2_res,
            "face_bbox": face_bbox,
            "sharpness": sharpness_val,
            "identified_id": self.identified_id,
            "identified_name": self.identified_name,
            "identity_sim": self.identity_sim,
            "completed_record": self.last_completed_record if self.state == SessionState.COMPLETED else None,
            "abort_reason": self.abort_reason,
            "latest_metrics": self.latest_face_metrics,
        }

    def _run_ai1_worker(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """Worker Thread: Chạy nhận diện InsightFace không gây khựng main thread."""
        try:
            res = identify(self.face_engine, frame_bgr, threshold=self.face_threshold)
            sim = res.get("similarity", 0.0)
            name = res.get("name", "Unknown")
            matched = res.get("match", False)
            sid = res.get("student_id")
            print(f"[AI 1 Worker] Đã quét: {name} (ID: {sid}) | Sim={sim:.3f} | Ngưỡng={self.face_threshold} | Match={matched}")
            return res
        except Exception as e:
            print(f"[UnifiedEngine Worker] Lỗi: {e}")
            return {"match": False, "student_id": None, "name": "Error", "similarity": 0.0}

    def _reset_to_idle(self) -> None:
        self.state = SessionState.IDLE
        self.state_enter_time = time.time()
        self.session_start_time = 0.0
        self.session_status_history.clear()
        self.best_frame_score = -1.0
        self.best_frame_bgr = None
        self.abort_reason = ""
        self.status_predictor.reset()
        print("[UnifiedEngine] 💤 Trở về IDLE. Sẵn sàng cho phiên tiếp theo.")

    # -------------------------------------------------------------
    # MA TRẬN HỢP NHẤT QUYẾT ĐỊNH (LATE FUSION)
    # -------------------------------------------------------------
    def _finalize_session(self) -> Dict[str, Any]:
        """
        Tổng hợp kết quả cuối cùng từ AI 1, AI 2 và dữ liệu IoT.
        Lưu snapshot ảnh và ghi log JSONL.
        """
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

        # 2. Chốt thông tin danh tính AI 1
        # Đợi Worker thread hoàn thành nốt nếu đang chạy
        if self._worker_future is not None:
            try:
                res = self._worker_future.result(timeout=1.0)
                if res and res.get("match"):
                    self.identified_id = res.get("student_id")
                    self.identified_name = res.get("name", "Unknown")
                    self.identity_sim = res.get("similarity", 0.0)
                    self.identity_matched = True
                elif res and res.get("similarity", 0.0) > self.identity_sim:
                    self.identity_sim = res.get("similarity", 0.0)
            except Exception:
                pass
            self._worker_future = None

        # Fallback kiểm tra thêm lần cuối trên frame tốt nhất nếu chưa tìm thấy
        if not self.identity_matched and self.best_frame_bgr is not None:
            try:
                res = identify(self.face_engine, self.best_frame_bgr, threshold=self.face_threshold)
                if res and res.get("match"):
                    self.identified_id = res.get("student_id")
                    self.identified_name = res.get("name", "Unknown")
                    self.identity_sim = res.get("similarity", 0.0)
                    self.identity_matched = True
                elif res and res.get("similarity", 0.0) > self.identity_sim:
                    self.identity_sim = res.get("similarity", 0.0)
            except Exception:
                pass

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
        if bio_level == "Bio_Danger":
            final_status = "CẢNH BÁO Y TẾ (Medical Alert)"
            alert_level = "RED"
            recommendation = "Chỉ số tim mạch/SpO2 bất thường. Cần nghỉ ngơi kiểm tra y tế ngay!"

        elif ai2_final_status == "Exhausted":
            final_status = "KIỆT SỨC / NGỦ GẬT (Exhausted)"
            alert_level = "RED"
            recommendation = "Mắt nhắm nghiền hoặc gật gù nặng. Không đảm bảo an toàn học tập/làm việc."

        elif ai2_final_status == "Fatigue" and bio_level == "Bio_Warning":
            final_status = "MỆT MỎI THỂ CHẤT (Physical Fatigue)"
            alert_level = "ORANGE"
            recommendation = "Có cả biểu hiện lờ đờ trên mặt lẫn nhịp tim/SpO2 suy giảm nhẹ."

        elif ai2_final_status == "Fatigue" and bio_level in ["Bio_Normal", "Bio_Missing"]:
            final_status = "BUỒN NGỦ / THIẾU NGỦ (Drowsy)"
            alert_level = "YELLOW"
            recommendation = "Chỉ số sinh tồn ổn định nhưng mắt/cơ mặt mỏi. Khuyến nghị rửa mặt tỉnh táo."

        elif ai2_final_status == "Normal" and bio_level == "Bio_Warning":
            final_status = "TỈNH TÁO - TIM ĐẬP NHANH (Active/Stressed)"
            alert_level = "YELLOW"
            recommendation = "Khuôn mặt tỉnh táo nhưng nhịp tim hơi cao (có thể vừa đi bộ nhanh hoặc căng thẳng)."

        elif ai2_final_status == "Normal" and bio_level in ["Bio_Normal", "Bio_Missing"]:
            final_status = "ĐẠT CHUẨN (Fit to Study/Work)"
            alert_level = "GREEN"
            recommendation = "Trạng thái tinh thần và thể chất hoàn toàn ổn định."

        else:
            final_status = f"CHƯA RÕ MẶT ({bio_level})"
            alert_level = "YELLOW"
            recommendation = "Camera không bắt đủ góc mặt chuẩn, chỉ ghi nhận chỉ số sinh trắc học."

        # 5. Lưu snapshot ảnh chất lượng cao nhất của phiên
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        ts_filename = time.strftime("%Y%m%d_%H%M%S")
        snapshot_filename = f"{final_student_id}_{ts_filename}.jpg"
        snapshot_path = self.snapshots_dir / snapshot_filename

        if self.best_frame_bgr is not None:
            cv2.imwrite(str(snapshot_path), self.best_frame_bgr)
        relative_snapshot_path = f"logs/snapshots/{snapshot_filename}"

        # 6. Tạo gói JSON Output chuẩn
        record: Dict[str, Any] = {
            "timestamp": now_str,
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
                "hr": hr,
                "spo2": spo2,
                "bio_level": bio_level,
                "ir_avg": self.iot_ir_avg,
            },
            "fusion_result": {
                "final_status": final_status,
                "alert_level": alert_level,
                "recommendation": recommendation,
            },
            "snapshot_path": relative_snapshot_path,
        }

        # 7. Ghi append vào file JSONL
        try:
            with open(self.jsonl_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[UnifiedEngine] 💾 Đã lưu kết quả vào {self.jsonl_log_path}")
        except Exception as e:
            print(f"[UnifiedEngine] Lỗi lưu log JSONL: {e}")

        return record

    def close(self) -> None:
        """Đóng an toàn ThreadPool."""
        self.thread_pool.shutdown(wait=False)
