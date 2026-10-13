"""
ai_engine.py — Module phân tích trạng thái AI từ luồng camera
==============================================================
Sử dụng MediaPipe FaceMesh để:
  1. Tính EAR (Eye Aspect Ratio) — phát hiện buồn ngủ
  2. Tính góc nghiêng đầu (Head Tilt) — phát hiện gục đầu
  3. Lưu cảnh báo vào DB khi phát hiện vi phạm

Thiết kế:
  - Lớp DrowsinessDetector là singleton, không tạo lại mỗi frame
  - Camera VideoCapture được quản lý bởi app.py (tránh xung đột)
  - Alert cooldown 30 giây — tránh flood database
  - State log cooldown 5 giây — ghi log định kỳ, không phải mỗi frame
"""

import math
import time
import threading
import cv2
import mediapipe as mp
import services

# ============================================================
# Hằng số cấu hình
# ============================================================

EAR_THRESHOLD = 0.25
EAR_CONSEC_FRAMES = 20
HEAD_TILT_THRESHOLD = 30.0
ALERT_COOLDOWN_SEC = 30
STATE_LOG_INTERVAL = 5

# Index landmark FaceMesh cho mắt trái và mắt phải
LEFT_EYE_IDX = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_IDX = [33, 160, 158, 133, 153, 144]

# Landmark điểm đầu để tính góc nghiêng
NOSE_TIP_IDX = 1
CHIN_IDX = 152


# ============================================================
# Utility functions
# ============================================================

def _euclidean(p1, p2):
    """Khoảng cách Euclidean giữa 2 điểm (x, y)."""
    return math.sqrt(
        (p1[0] - p2[0]) ** 2
        + (p1[1] - p2[1]) ** 2
    )


def _calculate_ear(landmarks, eye_indices, img_w, img_h):
    """
    Tính Eye Aspect Ratio (EAR) từ 6 landmark của một mắt.

    Công thức:
    EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    """
    pts = []

    for idx in eye_indices:
        lm = landmarks[idx]
        pts.append(
            (
                lm.x * img_w,
                lm.y * img_h
            )
        )

    # Chiều dọc
    A = _euclidean(pts[1], pts[5])
    B = _euclidean(pts[2], pts[4])

    # Chiều ngang
    C = _euclidean(pts[0], pts[3])

    ear = (
        (A + B) / (2.0 * C)
        if C > 0
        else 0.0
    )

    return ear


def _calculate_head_tilt(landmarks, img_w, img_h):
    """
    Tính góc nghiêng đầu theo trục dọc.

    Dùng vector từ cằm (152) → mũi (1),
    tính góc với trục Y.
    """
    nose = landmarks[NOSE_TIP_IDX]
    chin = landmarks[CHIN_IDX]

    dx = (nose.x - chin.x) * img_w
    dy = (nose.y - chin.y) * img_h

    angle = math.degrees(
        math.atan2(
            abs(dx),
            abs(dy)
        )
    )

    return angle


# ============================================================
# Lớp chính: DrowsinessDetector
# ============================================================

class DrowsinessDetector:
    """
    Phân tích từng frame video để phát hiện
    buồn ngủ và gục đầu.

    Thread-safe với lock khi truy cập
    trạng thái nội bộ.
    """

    def __init__(self):

        self._lock = threading.Lock()

        # ------------------------------------------------------
        # Khởi tạo MediaPipe FaceMesh
        # ------------------------------------------------------

        self._face_mesh = (
            mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
        )

        self._mp_drawing = (
            mp.solutions.drawing_utils
        )

        self._mp_drawing_spec = (
            mp.solutions.drawing_utils.DrawingSpec(
                thickness=1,
                circle_radius=1,
                color=(0, 255, 0)
            )
        )

        # ------------------------------------------------------
        # Trạng thái AI
        # ------------------------------------------------------

        self._ear_counter = 0
        self._current_state = "binh_thuong"
        self._current_ear = 0.0
        self._current_tilt = 0.0

        # ------------------------------------------------------
        # Cooldown
        # ------------------------------------------------------

        self._last_alert_time = {}
        self._last_log_time = 0.0

        # ------------------------------------------------------
        # Nhân viên hiện đang được AI giám sát
        #
        # KHÔNG hardcode MaNV = 1 nữa.
        # app.py sẽ gán khi xác định được nhân viên.
        # ------------------------------------------------------

        self.active_ma_nv = None

        print(
            "[ai_engine] "
            "DrowsinessDetector khoi tao thanh cong."
        )

    # ========================================================
    # Quản lý nhân viên hiện tại
    # ========================================================

    def set_active_employee(self, ma_nv):
        """
        Gán nhân viên hiện tại cho AI Engine.

        Ví dụ:
            detector.set_active_employee(2)
        """

        with self._lock:

            if ma_nv is None:
                self.active_ma_nv = None

            else:
                self.active_ma_nv = int(ma_nv)

    def clear_active_employee(self):
        """
        Xóa nhân viên đang được giám sát.

        Sau khi gọi hàm này,
        AI vẫn phân tích camera nhưng
        không ghi dữ liệu trạng thái/cảnh báo vào DB.
        """

        with self._lock:
            self.active_ma_nv = None

    # ========================================================
    # Phân tích frame
    # ========================================================

    def analyze_frame(self, frame):
        """
        Phân tích một frame BGR từ camera.

        Returns:
            frame:
                Frame đã vẽ thông tin AI.

            alert_info:
                Thông tin cảnh báo nếu vừa
                phát hiện cảnh báo mới.
        """

        img_h, img_w = frame.shape[:2]

        frame_rgb = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        results = self._face_mesh.process(
            frame_rgb
        )

        alert_info = None

        # ------------------------------------------------------
        # Có khuôn mặt
        # ------------------------------------------------------

        if results.multi_face_landmarks:

            face_landmarks = (
                results
                .multi_face_landmarks[0]
                .landmark
            )

            # --------------------------------------------------
            # EAR mắt trái
            # --------------------------------------------------

            ear_left = _calculate_ear(
                face_landmarks,
                LEFT_EYE_IDX,
                img_w,
                img_h
            )

            # --------------------------------------------------
            # EAR mắt phải
            # --------------------------------------------------

            ear_right = _calculate_ear(
                face_landmarks,
                RIGHT_EYE_IDX,
                img_w,
                img_h
            )

            # Trung bình 2 mắt
            ear = (
                ear_left
                + ear_right
            ) / 2.0

            # --------------------------------------------------
            # Tính góc nghiêng đầu
            # --------------------------------------------------

            tilt = _calculate_head_tilt(
                face_landmarks,
                img_w,
                img_h
            )

            # --------------------------------------------------
            # Cập nhật trạng thái
            # --------------------------------------------------

            with self._lock:

                self._current_ear = ear
                self._current_tilt = tilt

            # --------------------------------------------------
            # Vẽ FaceMesh
            # --------------------------------------------------

            mp.solutions.drawing_utils.draw_landmarks(
                image=frame,

                landmark_list=(
                    results
                    .multi_face_landmarks[0]
                ),

                connections=(
                    mp.solutions.face_mesh
                    .FACEMESH_TESSELATION
                ),

                landmark_drawing_spec=None,

                connection_drawing_spec=(
                    mp.solutions.drawing_styles
                    .get_default_face_mesh_tesselation_style()
                )
            )

            # --------------------------------------------------
            # Phân tích trạng thái
            # --------------------------------------------------

            alert_info = self._evaluate_state(
                ear,
                tilt
            )

            # --------------------------------------------------
            # Vẽ overlay
            # --------------------------------------------------

            self._draw_overlay(
                frame,
                ear,
                tilt,
                self._current_state
            )

        # ------------------------------------------------------
        # Không có khuôn mặt
        # ------------------------------------------------------

        else:

            with self._lock:

                self._ear_counter = 0

                self._current_state = (
                    "khong_co_khuon_mat"
                )

                self._current_ear = 0.0
                self._current_tilt = 0.0

            self._draw_overlay(
                frame,
                0,
                0,
                "khong_co_khuon_mat"
            )

        return frame, alert_info

    # ========================================================
    # Đánh giá trạng thái
    # ========================================================

    def _evaluate_state(
        self,
        ear,
        tilt
    ):

        now = time.time()

        alert_info = None

        # ------------------------------------------------------
        # Kiểm tra buồn ngủ
        # ------------------------------------------------------

        if ear < EAR_THRESHOLD:

            with self._lock:

                self._ear_counter += 1

                counter = (
                    self._ear_counter
                )

            if counter >= EAR_CONSEC_FRAMES:

                with self._lock:

                    self._current_state = (
                        "buon_ngu"
                    )

                alert_info = (
                    self._try_save_alert(
                        now,
                        "Buon ngu",

                        (
                            f"EAR={ear:.3f} — "
                            f"Mat nham qua "
                            f"{counter} frame lien tiep"
                        ),

                        ear
                    )
                )

        # ------------------------------------------------------
        # Kiểm tra gục đầu
        # ------------------------------------------------------

        elif tilt > HEAD_TILT_THRESHOLD:

            with self._lock:

                self._ear_counter = 0

                self._current_state = (
                    "guc_dau"
                )

            alert_info = (
                self._try_save_alert(
                    now,
                    "Guc dau",

                    (
                        f"Goc nghieng="
                        f"{tilt:.1f} do — "
                        f"Vuot nguong "
                        f"{HEAD_TILT_THRESHOLD} do"
                    ),

                    tilt
                )
            )

        # ------------------------------------------------------
        # Bình thường
        # ------------------------------------------------------

        else:

            with self._lock:

                self._ear_counter = 0

                self._current_state = (
                    "binh_thuong"
                )

        # ------------------------------------------------------
        # Log trạng thái mỗi 5 giây
        # ------------------------------------------------------

        if (
            now - self._last_log_time
            >= STATE_LOG_INTERVAL
        ):

            with self._lock:

                state = (
                    self._current_state
                )

                ma_nv = (
                    self.active_ma_nv
                )

                self._last_log_time = now

            # Chỉ lưu nếu biết nhân viên nào
            if ma_nv is not None:

                threading.Thread(
                    target=services.save_state_log,

                    args=(
                        ma_nv,
                        state,
                        ear
                    ),

                    daemon=True
                ).start()

        return alert_info

    # ========================================================
    # Lưu cảnh báo
    # ========================================================

    def _try_save_alert(
        self,
        now,
        loai,
        mo_ta,
        gia_tri
    ):
        """
        Lưu cảnh báo nếu:

        1. Đã xác định được nhân viên.
        2. Đã hết cooldown của loại cảnh báo đó.
        """

        # ------------------------------------------------------
        # Lấy MaNV hiện tại thread-safe
        # ------------------------------------------------------

        with self._lock:

            ma_nv = (
                self.active_ma_nv
            )

        # ------------------------------------------------------
        # Chưa xác định nhân viên
        #
        # Không ghi cảnh báo để tránh
        # gán sai người.
        # ------------------------------------------------------

        if ma_nv is None:

            return None

        # ------------------------------------------------------
        # Kiểm tra cooldown
        # ------------------------------------------------------

        last = self._last_alert_time.get(
            loai,
            0
        )

        if (
            now - last
            >= ALERT_COOLDOWN_SEC
        ):

            self._last_alert_time[
                loai
            ] = now

            # --------------------------------------------------
            # Lưu DB trong background thread
            # --------------------------------------------------

            threading.Thread(
                target=services.save_alert,

                args=(
                    ma_nv,
                    loai,
                    mo_ta,
                    gia_tri
                ),

                daemon=True
            ).start()

            return {
                "loai": loai,
                "mo_ta": mo_ta,
                "gia_tri": gia_tri
            }

        return None

    # ========================================================
    # Vẽ overlay
    # ========================================================

    def _draw_overlay(
        self,
        frame,
        ear,
        tilt,
        state
    ):

        color_map = {

            "binh_thuong":
                (0, 255, 0),

            "buon_ngu":
                (0, 0, 255),

            "guc_dau":
                (0, 165, 255),

            "khong_co_khuon_mat":
                (128, 128, 128)
        }

        color = color_map.get(
            state,
            (255, 255, 255)
        )

        # ------------------------------------------------------
        # Nền mờ
        # ------------------------------------------------------

        overlay = frame.copy()

        cv2.rectangle(
            overlay,
            (0, 0),
            (300, 90),
            (0, 0, 0),
            -1
        )

        cv2.addWeighted(
            overlay,
            0.5,
            frame,
            0.5,
            0,
            frame
        )

        # ------------------------------------------------------
        # EAR
        # ------------------------------------------------------

        cv2.putText(
            frame,

            f"EAR: {ear:.3f}",

            (10, 20),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            (255, 255, 255),

            1
        )

        # ------------------------------------------------------
        # Head Tilt
        # ------------------------------------------------------

        cv2.putText(
            frame,

            f"Tilt: {tilt:.1f} deg",

            (10, 45),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            (255, 255, 255),

            1
        )

        # ------------------------------------------------------
        # Trạng thái
        # ------------------------------------------------------

        state_labels = {

            "binh_thuong":
                "BINH THUONG",

            "buon_ngu":
                "! BUON NGU !",

            "guc_dau":
                "! GUC DAU !",

            "khong_co_khuon_mat":
                "KHONG CO KHUON MAT"
        }

        label = state_labels.get(
            state,
            state.upper()
        )

        cv2.putText(
            frame,

            label,

            (10, 75),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.7,

            color,

            2
        )

    # ========================================================
    # API trạng thái AI
    # ========================================================

    def get_current_status(self):
        """
        Trả trạng thái hiện tại cho /api/ai_status.
        """

        with self._lock:

            return {

                "state":
                    self._current_state,

                "ear":
                    round(
                        self._current_ear,
                        3
                    ),

                "tilt":
                    round(
                        self._current_tilt,
                        1
                    ),

                "ma_nv":
                    self.active_ma_nv
            }

    # ========================================================
    # Giải phóng MediaPipe
    # ========================================================

    def release(self):
        """
        Giải phóng tài nguyên FaceMesh.
        """

        self._face_mesh.close()


# ============================================================
# Singleton — với fallback nếu MediaPipe lỗi version/environment
# ============================================================

class _DummyDetector:
    """
    Fallback khi MediaPipe không khởi tạo được.
    Cung cấp đủ interface để app.py không bị AttributeError.
    analyze_frame trả frame gốc và không có alert.
    """
    active_ma_nv = None

    def analyze_frame(self, frame):
        return frame, None

    def set_active_employee(self, ma_nv):
        self.active_ma_nv = ma_nv

    def clear_active_employee(self):
        self.active_ma_nv = None

    def get_current_status(self):
        return {"status": "AI_UNAVAILABLE", "message": "MediaPipe init failed"}


try:
    detector = DrowsinessDetector()
except Exception as _ai_init_err:
    print(f"[ai_engine] WARN: MediaPipe init failed — using DummyDetector.\n"
          f"            Error: {_ai_init_err}")
    detector = _DummyDetector()
