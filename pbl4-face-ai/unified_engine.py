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

import os
import sys
import time
import json
import enum
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, Future

# Tắt cảnh báo C++ của TensorFlow/MediaPipe ghi vào STDERR làm đỏ console
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("GLOG_minloglevel", "3")

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
    CAPTURING = "CAPTURING"    # Chụp 3 ảnh cách nhau 300ms
    PROCESSING = "PROCESSING"  # Đang phân tích 2 AI & đợi dữ liệu IoT
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    # Giữ alias để tương thích ngược nếu có module gọi
    WARMUP = "CAPTURING"
    SCANNING = "CAPTURING"


class UnifiedAttendanceEngine:
    """
    Bộ điều phối hợp nhất Chấm công Thông minh theo cơ chế Snapshot 3 ảnh rời rạc (cách nhau 300ms).
    Camera không lấy ảnh liên tục: Chỉ mở chụp đúng 3 frame (0ms, 300ms, 600ms) rồi dừng.
    """

    SNAPSHOT_INTERVAL = 0.30    # Khoảng cách giữa các ảnh (300ms)
    TOTAL_SNAPSHOTS = 3         # Đúng 3 ảnh rời rạc
    COMPLETED_DISPLAY_SEC = 5.0 # Giữ màn hình kết quả 5 giây trước khi về IDLE
    ABORTED_DISPLAY_SEC = 2.5   # Giữ màn hình lỗi trước khi về IDLE
    HARD_TIMEOUT_SEC = 6.0      # Giới hạn thời gian tối đa của 1 phiên

    def __init__(
        self,
        logs_dir: Optional[Path] = None,
        face_threshold: float = 0.45,
    ):
        self.logs_dir = logs_dir or (CURRENT_DIR / "logs")
        self.snapshots_dir = self.logs_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_log_path = self.logs_dir / "attendance_logs.jsonl"
        self.web_api_url: str = os.environ.get("PBL4_WEB_API", "http://localhost:8080/api/chamcong")

        # Khởi tạo AI 1 & AI 2
        print("[UnifiedEngine] Đang nạp mô hình AI 1 (InsightFace buffalo_sc)...")
        self.face_engine = FaceEngine(model_name="buffalo_sc")
        self.face_threshold = face_threshold
        # Load cache DB embeddings một lần
        load_db(force_reload=True)

        print("[UnifiedEngine] Đang nạp mô hình AI 2 (MediaPipe Face Mesh + Random Forest)...")
        self.status_predictor = StatusPredictor(smoothing_window=5, max_yaw_deg=25.0)

        # Quản lý State Machine
        self.state = SessionState.IDLE
        self.state_enter_time = time.time()
        self.session_start_time = 0.0

        # Bộ nhớ đệm 3 ảnh rời rạc
        self.captured_frames: List[np.ndarray] = []
        self.captured_timestamps: List[float] = []
        self.captured_sharpness: List[float] = []
        self.last_capture_time = 0.0
        self.flash_timer = 0.0
        self.iot_done_received = False
        self.ai_processed = False

        # Bộ nhớ đệm phiên chấm công
        self.session_status_history: List[str] = []
        self.best_frame_score = -1.0
        self.best_frame_bgr: Optional[np.ndarray] = None
        self.latest_face_metrics: Dict[str, float] = {
            "ear": 0.0, "mar": 0.0, "pitch": 0.0, "yaw": 0.0, "sharpness": 0.0
        }
        # Bộ đệm 3 ảnh bằng chứng: [Ảnh 1 (0ms), Ảnh nét nhất, Ảnh 3 (600ms)]
        self.evidence_frames: List[Optional[np.ndarray]] = [None, None, None]
        self.face_bbox: Optional[Tuple[int, int, int, int]] = None

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
        Bắt đầu chu kỳ chụp đúng 3 ảnh rời rạc (cách nhau 300ms).
        """
        if self.state in [SessionState.CAPTURING, SessionState.PROCESSING]:
            return  # Đang trong phiên, bỏ qua trigger trùng

        now = time.time()
        self.state = SessionState.CAPTURING
        self.state_enter_time = now
        self.session_start_time = now

        # Reset toàn bộ dữ liệu đệm phiên
        self.captured_frames.clear()
        self.captured_timestamps.clear()
        self.captured_sharpness.clear()
        self.last_capture_time = 0.0
        self.flash_timer = 0.0
        self.iot_done_received = False
        self.ai_processed = False

        self.session_status_history.clear()
        self.best_frame_score = -1.0
        self.best_frame_bgr = None
        self.evidence_frames = [None, None, None]
        self.face_bbox = None

        self.identified_id = None
        self.identified_name = "Scanning Identity..."
        self.identity_sim = 0.0
        self.identity_matched = False

        self.iot_hr = 0
        self.iot_spo2 = 0
        self.iot_ir_avg = ir
        self.abort_reason = ""
        self.status_predictor.reset()

        print(f"[UnifiedEngine] 🚀 BẮT ĐẦU PHIÊN CHỤP 3 ẢNH RỜI RẠC (Mỗi ảnh cách 300ms) | IR={ir}")

    def abort_session(self, reason: str = "FINGER_REMOVED") -> None:
        """
        Nhận sự kiện ABORT_SESSION (người dùng rút tay ra sớm hoặc lỗi kết nối).
        """
        if self.state in [SessionState.CAPTURING, SessionState.PROCESSING]:
            self.state = SessionState.ABORTED
            self.state_enter_time = time.time()
            self.abort_reason = reason
            print(f"[UnifiedEngine] ⚠️ HỦY PHIÊN (ABORT_SESSION) | Lý do: {reason}")

    def done_session(self, hr: int, spo2: int, ir_avg: int = 0) -> Optional[Dict[str, Any]]:
        """
        Nhận sự kiện DONE_SESSION từ ESP32 chứa trung vị HR & SpO2.
        Nếu AI đã xử lý xong 3 ảnh -> chốt kết quả Late Fusion ngay lập tức.
        """
        if self.state not in [SessionState.CAPTURING, SessionState.PROCESSING]:
            return None

        self.iot_hr = hr
        self.iot_spo2 = spo2
        self.iot_ir_avg = ir_avg
        self.iot_done_received = True
        print(f"[UnifiedEngine] 🏁 NHẬN DONE_SESSION | HR={hr}, SpO2={spo2}, IR={ir_avg}")

        # Nếu AI đã xử lý xong 3 ảnh -> lập tức hoàn tất phiên
        if self.ai_processed:
            record = self._finalize_session()
            self.state = SessionState.COMPLETED
            self.state_enter_time = time.time()
            self.last_completed_record = record
            return record

        return None

    def update(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Hàm điều phối luồng Snapshot 3 ảnh rời rạc.
        Camera không lấy ảnh liên tục để phân tích:
          - Ảnh 1: T = 0ms
          - Ảnh 2: T = 300ms
          - Ảnh 3: T = 600ms
        Sau khi đủ 3 ảnh, camera DỪNG chụp và nạp vào 2 AI.
        """
        now = time.time()
        elapsed_in_state = now - self.state_enter_time
        elapsed_in_session = now - self.session_start_time if self.session_start_time > 0 else 0.0

        # Kiểm tra Hard Timeout cho phiên đang quét (6.0s)
        if self.state in [SessionState.CAPTURING, SessionState.PROCESSING]:
            if elapsed_in_session >= self.HARD_TIMEOUT_SEC:
                self.abort_session(reason="HARD_TIMEOUT_EXCEEDED")

        # Tự động chuyển trạng thái hoàn tất / hủy
        if self.state == SessionState.COMPLETED:
            if elapsed_in_state >= self.COMPLETED_DISPLAY_SEC:
                self._reset_to_idle()

        elif self.state == SessionState.ABORTED:
            if elapsed_in_state >= self.ABORTED_DISPLAY_SEC:
                self._reset_to_idle()

        # -------------------------------------------------------------
        # TRẠNG THÁI IDLE: CPU NGHỈ HOÀN TOÀN (0% AI LOAD)
        # -------------------------------------------------------------
        if self.state == SessionState.IDLE:
            return {
                "state": self.state,
                "elapsed_in_state": elapsed_in_state,
                "elapsed_in_session": 0.0,
                "captured_count": 0,
                "captured_frames": [],
                "flash_timer": 0.0,
                "ai2_result": None,
                "face_bbox": None,
                "sharpness": 0.0,
                "identified_id": None,
                "identified_name": "Đặt ngón tay lên cảm biến để bắt đầu chấm công",
                "identity_sim": 0.0,
                "completed_record": None,
                "abort_reason": "",
                "latest_metrics": self.latest_face_metrics,
            }

        # -------------------------------------------------------------
        # TRẠNG THÁI CAPTURING: CHỤP 3 ẢNH RỜI RẠC CÁCH NHAU 300MS
        # -------------------------------------------------------------
        if self.state == SessionState.CAPTURING:
            count = len(self.captured_frames)

            # Ảnh 1: Chụp ngay tại thời điểm kích hoạt (T = 0ms)
            if count == 0:
                self.captured_frames.append(frame_bgr.copy())
                self.captured_timestamps.append(elapsed_in_session)
                self.last_capture_time = now
                self.flash_timer = now
                print(f"[UnifiedEngine] 📸 Đã chụp Ảnh 1/3 (T = 0ms)")

            # Ảnh 2: Chụp sau ít nhất 300ms
            elif count == 1 and (now - self.last_capture_time >= self.SNAPSHOT_INTERVAL):
                self.captured_frames.append(frame_bgr.copy())
                self.captured_timestamps.append(elapsed_in_session)
                self.last_capture_time = now
                self.flash_timer = now
                print(f"[UnifiedEngine] 📸 Đã chụp Ảnh 2/3 (T = +300ms)")

            # Ảnh 3: Chụp sau ít nhất 300ms nữa (+600ms)
            elif count == 2 and (now - self.last_capture_time >= self.SNAPSHOT_INTERVAL):
                self.captured_frames.append(frame_bgr.copy())
                self.captured_timestamps.append(elapsed_in_session)
                self.last_capture_time = now
                self.flash_timer = now
                print(f"[UnifiedEngine] 📸 Đã chụp Ảnh 3/3 (T = +600ms)")

                # ĐÃ ĐỦ 3 ẢNH! DỪNG CHỤP VÀ CHUYỂN SANG PHÂN TÍCH 2 AI
                self.state = SessionState.PROCESSING
                self.state_enter_time = now
                print("[UnifiedEngine] 🛑 Đã chụp đủ 3 ảnh rời rạc. Camera NGẮT chụp, nạp vào 2 AI...")
                self._process_3_snapshots()

                # Nếu IoT đã gửi dữ liệu xong từ trước (hoặc khi IoT gửi đồng thời):
                if self.iot_done_received:
                    record = self._finalize_session()
                    self.state = SessionState.COMPLETED
                    self.state_enter_time = time.time()
                    self.last_completed_record = record

        # -------------------------------------------------------------
        # TRẠNG THÁI PROCESSING: ĐÃ CÓ 3 ẢNH, ĐANG PHÂN TÍCH & ĐỢI IOT
        # -------------------------------------------------------------
        elif self.state == SessionState.PROCESSING:
            # Nếu AI đã xong và IoT đã nhận xong -> Hoàn tất
            if self.ai_processed and self.iot_done_received:
                record = self._finalize_session()
                self.state = SessionState.COMPLETED
                self.state_enter_time = time.time()
                self.last_completed_record = record
            elif elapsed_in_session >= 3.5:
                # Quá 3.5s mà chưa có done IoT -> tự động hoàn tất với dữ liệu hiện có
                print("[UnifiedEngine] ⏱️ Tự động chốt phiên (Timeout chờ IoT).")
                record = self._finalize_session()
                self.state = SessionState.COMPLETED
                self.state_enter_time = time.time()
                self.last_completed_record = record

        return {
            "state": self.state,
            "elapsed_in_state": elapsed_in_state,
            "elapsed_in_session": elapsed_in_session,
            "captured_count": len(self.captured_frames),
            "captured_frames": self.captured_frames,
            "flash_timer": self.flash_timer,
            "ai2_result": {"status": self.session_status_history[0]} if self.session_status_history else None,
            "face_bbox": self.face_bbox,
            "sharpness": self.best_frame_score if self.best_frame_score > 0 else 0.0,
            "identified_id": self.identified_id,
            "identified_name": self.identified_name,
            "identity_sim": self.identity_sim,
            "completed_record": self.last_completed_record if self.state == SessionState.COMPLETED else None,
            "abort_reason": self.abort_reason,
            "latest_metrics": self.latest_face_metrics,
        }

    def _process_3_snapshots(self) -> None:
        """
        Phân tích 2 mô hình AI trên đúng 3 tấm ảnh vừa chụp (không lấy thêm bất kỳ frame nào):
          1. AI 1 (InsightFace): Lọc ảnh nét nhất trong 3 ảnh bằng Laplacian để nhận diện danh tính.
          2. AI 2 (MediaPipe + Random Forest): Nạp trọn vẹn cả 3 ảnh để trích xuất 7 đặc trưng cử động.
        """
        if len(self.captured_frames) != 3:
            return

        frames = self.captured_frames

        # ---------------------------------------------------------
        # 1. AI 1: TÍNH ĐỘ NÉT LAPLACIAN VÀ CHỌN ẢNH NÉT NHẤT
        # ---------------------------------------------------------
        sharpness_scores = []
        for f in frames:
            gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            s = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            sharpness_scores.append(s)

        self.captured_sharpness = sharpness_scores
        best_idx = int(np.argmax(sharpness_scores))
        self.best_frame_bgr = frames[best_idx].copy()
        self.best_frame_score = sharpness_scores[best_idx]

        # Lưu 3 ảnh bằng chứng tương ứng: [Ảnh 1 (0ms), Ảnh nét nhất, Ảnh 3 (600ms)]
        self.evidence_frames[0] = frames[0].copy()
        self.evidence_frames[1] = frames[best_idx].copy()
        self.evidence_frames[2] = frames[2].copy()

        # Nạp ảnh nét nhất vào FaceEngine (InsightFace ArcFace)
        try:
            res_ai1 = identify(self.face_engine, self.best_frame_bgr, threshold=self.face_threshold)
            if res_ai1 and res_ai1.get("match"):
                self.identified_id = res_ai1.get("student_id")
                self.identified_name = res_ai1.get("name", "Unknown")
                self.identity_sim = res_ai1.get("similarity", 0.0)
                self.identity_matched = True
            elif res_ai1:
                self.identity_sim = res_ai1.get("similarity", 0.0)
                self.identified_name = "Không xác định"
            print(f"[AI 1] Nhận diện trên Ảnh #{best_idx+1} (Nét nhất: {self.best_frame_score:.1f}) | {self.identified_name} (ID: {self.identified_id}) | Sim={self.identity_sim:.3f}")
        except Exception as e:
            print(f"[AI 1] Lỗi nhận diện khuôn mặt: {e}")

        # ---------------------------------------------------------
        # 2. AI 2: PHÂN TÍCH THỂ TRẠNG QUA CHUỖI 3 ẢNH RỜI RẠC
        # ---------------------------------------------------------
        try:
            ai2_detail = self.status_predictor.predict_status_detailed(frames)
            raw_status = ai2_detail.get("status", "Normal")
            if raw_status in ["Normal", "Fatigue", "Exhausted"]:
                self.session_status_history = [raw_status]
            else:
                self.session_status_history = ["Normal"]

            metrics = ai2_detail.get("metrics", {})
            self.latest_face_metrics = {
                "ear": float(metrics.get("ear", 0.0)),
                "mar": float(metrics.get("mar", 0.0)),
                "pitch": float(metrics.get("pitch", 0.0)),
                "yaw": float(metrics.get("yaw", 0.0)),
                "sharpness": self.best_frame_score,
            }
            print(f"[AI 2] Phân tích 3 ảnh rời rạc -> Thể trạng: {raw_status} | EAR={metrics.get('ear')} | MAR={metrics.get('mar')} | Pitch={metrics.get('pitch')}")
        except Exception as e:
            print(f"[AI 2] Lỗi phân tích thể trạng: {e}")
            self.session_status_history = ["Normal"]

        self.ai_processed = True

    def _reset_to_idle(self) -> None:
        self.state = SessionState.IDLE
        self.state_enter_time = time.time()
        self.session_start_time = 0.0
        self.captured_frames.clear()
        self.captured_timestamps.clear()
        self.captured_sharpness.clear()
        self.last_capture_time = 0.0
        self.flash_timer = 0.0
        self.iot_done_received = False
        self.ai_processed = False
        self.session_status_history.clear()
        self.best_frame_score = -1.0
        self.best_frame_bgr = None
        self.evidence_frames = [None, None, None]
        self.face_bbox = None
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
        if bio_level == "Bio_Danger":
            final_status = "Cảnh báo y tế"
            alert_level = "RED"
            recommendation = "Chỉ số tim mạch hoặc SpO2 bất thường. Cần nghỉ ngơi kiểm tra y tế ngay!"

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

        elif ai2_final_status == "Normal" and bio_level in ["Bio_Normal", "Bio_Missing"]:
            final_status = "Đạt chuẩn sức khỏe"
            alert_level = "GREEN"
            recommendation = "Trạng thái tinh thần và chỉ số sinh tồn hoàn toàn ổn định."

        else:
            final_status = "Đang đánh giá"
            alert_level = "YELLOW"
            recommendation = "Camera chưa bắt đủ góc mặt chuẩn, ghi nhận theo chỉ số sinh trắc học."

        # 5. Lưu 3 ảnh bằng chứng chấm công
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        ts_filename = time.strftime("%Y%m%d_%H%M%S")

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
                cv2.imwrite(str(abs_path), ev_frame)
                evidence_paths.append(rel_path)
            else:
                evidence_paths.append("")  # Frame không có thì để rỗng

        # Tương thích ngược: snapshot_path = ảnh best (index 1)
        snapshot_path_compat = evidence_paths[1] if len(evidence_paths) > 1 else ""

        print(f"[UnifiedEngine] 📸 Đã lưu {sum(1 for p in evidence_paths if p)} ảnh bằng chứng")

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
            # 3 ảnh bằng chứng: [start, best, end]
            "evidence_snapshots": evidence_paths,
            # Tương thích ngược
            "snapshot_path": snapshot_path_compat,
        }

        # 7. Ghi append vào file JSONL
        try:
            with open(self.jsonl_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[UnifiedEngine] 💾 Đã lưu kết quả vào {self.jsonl_log_path}")
        except Exception as e:
            print(f"[UnifiedEngine] Lỗi lưu log JSONL: {e}")

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
            record["attendance_action"] = "CHAM_CONG"
            record["attendance_msg"] = msg or "Đã ghi nhận"
        record["web_result"] = web_res

        return record

    def _sync_attendance_to_web(
        self,
        student_id: str,
        hr: int,
        spo2: int,
        ai2_status: str,
        best_frame: Optional[np.ndarray],
    ) -> Dict[str, Any]:
        """Gửi kết quả điểm danh lên Web backend qua REST API."""
        if not student_id or student_id == "Unknown":
            return {"action": "none", "status": "no_identity", "message": "Chưa xác định danh tính"}

        # Trích xuất số ID (ví dụ SV001 -> 1, NV02 -> 2, 1 -> 1)
        num_str = "".join(filter(str.isdigit, student_id))
        if not num_str:
            return {"action": "none", "status": "no_id", "message": "Không tìm thấy mã số"}
        emp_id = int(num_str)

        img_b64 = None
        if best_frame is not None:
            try:
                ret, buf = cv2.imencode(".jpg", best_frame)
                if ret:
                    import base64
                    img_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
            except Exception:
                pass

        payload: Dict[str, Any] = {
            "MaNV": emp_id,
            "MaTB": 1,
            "NhipTim": hr if hr > 0 else None,
            "SpO2": float(spo2) if spo2 > 0 else None,
            "TrangThai": ai2_status,
            "image": img_b64,
        }

        try:
            import requests
            res = requests.post(self.web_api_url, json=payload, timeout=2.5)
            if res.status_code == 200:
                data = res.json()
                msg = data.get("message", "Thành công")
                st = data.get("status", "")
                if st == "completed":
                    print(f"[SyncWeb] ⛔ TỪ CHỐI: {msg} (MaNV={emp_id})")
                else:
                    print(f"[SyncWeb] ✅ Đã đồng bộ sang Web: {msg} (MaNV={emp_id})")
                return data
            else:
                print(f"[SyncWeb] ⚠️ Web trả về mã {res.status_code}: {res.text[:80]}")
                return {"action": "error", "status": "error", "message": f"HTTP {res.status_code}"}
        except Exception as e:
            # Không làm gián đoạn hệ thống nếu Web/Docker chưa mở
            print(f"[SyncWeb] ℹ️ Chưa kết nối Web API ({self.web_api_url}): {e}")
            return {"action": "offline", "status": "offline", "message": "Ngoại tuyến"}

    def close(self) -> None:
        """Đóng an toàn engine."""
        pass
