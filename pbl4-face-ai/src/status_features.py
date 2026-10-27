import cv2
import numpy as np
import mediapipe as mp

mp_face_mesh = mp.solutions.face_mesh

# ─── Cấu hình các điểm mốc (Landmarks) ─────────────────────────────────────────

# Điểm mắt (6 điểm mỗi mắt)
LEFT_EYE_INDICES = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_INDICES = [33, 160, 158, 133, 153, 144]

# Điểm môi (vành trong)
LIP_TOP = 13
LIP_BOTTOM = 14
LIP_LEFT = 78
LIP_RIGHT = 308

# Điểm tính toán Head Pose (3D)
# 1: Đỉnh mũi, 152: Cằm, 33: Mắt phải góc trái, 263: Mắt trái góc phải
# 61: Mép môi phải, 291: Mép môi trái
POSE_INDICES = [33, 263, 1, 61, 291, 152]

# Mô hình 3D chuẩn khuôn mặt (dùng cho solvePnP)
FACE_3D_MODEL_POINTS = np.array([
    [ -225.0,  170.0, -135.0], # Mắt phải góc ngoài
    [  225.0,  170.0, -135.0], # Mắt trái góc ngoài
    [    0.0,    0.0,    0.0], # Đỉnh mũi (gốc tọa độ 0,0,0)
    [ -150.0, -150.0, -125.0], # Mép môi phải
    [  150.0, -150.0, -125.0], # Mép môi trái
    [    0.0, -330.0,  -65.0], # Cằm
], dtype=np.float64)


class StatusFeatureExtractor:
    """
    Trích xuất đặc trưng (EAR, MAR, Pitch, Yaw, Roll) từ ảnh trên RAM.
    Dùng MediaPipe Face Mesh làm lõi nhận diện điểm mốc.
    """
    def __init__(self):
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False, # Tối ưu cho chuỗi frame liên tiếp
            max_num_faces=2,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    def close(self):
        self.face_mesh.close()

    def extract_features(self, frame_bgr):
        """
        Input: cv2 frame (BGR)
        Output: dict {ear, mar, pitch, yaw, roll, landmarks} hoặc None nếu không thấy mặt
        """
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(frame_rgb)

        if not results.multi_face_landmarks or len(results.multi_face_landmarks) != 1:
            return None
        
        # Chỉ lấy khuôn mặt đầu tiên
        landmarks = results.multi_face_landmarks[0].landmark
        h, w, _ = frame_bgr.shape

        # Chuyển landmark tỉ lệ (0-1) thành pixel thực tế
        pts = np.array([(lm.x * w, lm.y * h) for lm in landmarks])
        if len(pts) < 468 or not np.isfinite(pts).all():
            return None

        # 1. Tính EAR (Độ mở mắt)
        ear = self._calculate_ear(pts)

        # 2. Tính MAR (Độ mở miệng)
        mar = self._calculate_mar(pts)
        if not np.isfinite([ear, mar]).all():
            return None

        # 3. Tính Head Pose (Pitch, Yaw, Roll)
        try:
            pitch, yaw, roll = self._calculate_head_pose(pts, w, h)
        except Exception:
            return None
        if not np.isfinite([pitch, yaw, roll]).all():
            return None

        return {
            "ear": ear,
            "mar": mar,
            "pitch": pitch,
            "yaw": yaw,
            "roll": roll,
            "pts": pts # Giữ lại nếu cần vẽ vời
        }

    def _calculate_ear(self, pts):
        def eye_aspect_ratio(eye_pts):
            # Tính khoảng cách dọc (2 cặp điểm)
            v1 = np.linalg.norm(eye_pts[1] - eye_pts[5])
            v2 = np.linalg.norm(eye_pts[2] - eye_pts[4])
            # Tính khoảng cách ngang
            h = np.linalg.norm(eye_pts[0] - eye_pts[3])
            return (v1 + v2) / (2.0 * h) if h > 0 else float('nan')

        left_eye = pts[LEFT_EYE_INDICES]
        right_eye = pts[RIGHT_EYE_INDICES]
        return (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2.0

    def _calculate_mar(self, pts):
        # Chiều dọc môi trong
        v = np.linalg.norm(pts[LIP_TOP] - pts[LIP_BOTTOM])
        # Chiều ngang mép môi
        h = np.linalg.norm(pts[LIP_LEFT] - pts[LIP_RIGHT])
        return v / h if h > 0 else float('nan')

    def _calculate_head_pose(self, pts, w, h):
        # Lấy tọa độ 6 điểm mốc cho Head Pose
        image_pts = pts[POSE_INDICES].astype(np.float64)

        # Trục quang học camera giả định
        focal_length = w
        center = (w / 2, h / 2)
        cam_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        success, rotation_vec, translation_vec = cv2.solvePnP(
            FACE_3D_MODEL_POINTS, image_pts, cam_matrix, dist_coeffs
        )

        if not success:
            return float('nan'), float('nan'), float('nan')

        # Chuyển vector xoay thành ma trận quay, sau đó tính góc Euler
        rmat, _ = cv2.Rodrigues(rotation_vec)
        angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)

        pitch = angles[0] # Cúi / Ngửa (Gục đầu)
        yaw   = angles[1] # Quay trái / phải
        roll  = angles[2] # Nghiêng đầu

        return pitch, yaw, roll
