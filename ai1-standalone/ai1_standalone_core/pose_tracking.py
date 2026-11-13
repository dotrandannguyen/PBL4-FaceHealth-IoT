"""Calibrated relative-pose guidance for Smart Enrollment v2.

The legacy solvePnP yaw/pitch values use Euler angles in an uncalibrated model
frame and can report a frontal face near 180 degrees. Guided enrollment instead
uses the first stable, user-guided frontal rotation as its reference. This is
ordinary RGB landmark pose guidance; it is not depth sensing or liveness.
"""

import math
import time
from collections import deque

import numpy as np
import face_matching

from .config import (
    GUIDED_CALIBRATION_MAX_RAW_YAW_DEG,
    GUIDED_CALIBRATION_MAX_EYE_LINE_TILT_DEG,
    GUIDED_CALIBRATION_MAX_NOSE_OFFSET_FACE_WIDTH,
    GUIDED_CALIBRATION_MIN_EYE_SPAN_FACE_HEIGHT,
    GUIDED_CALIBRATION_MIN_MOUTH_SPAN_FACE_HEIGHT,
    GUIDED_POSE_FPS_DIAGNOSTIC_SECONDS,
    GUIDED_FRONTAL_PITCH_MAX_DEG,
    GUIDED_FRONTAL_YAW_MAX_DEG,
    GUIDED_POSE_MAX_INTERFRAME_GAP_SECONDS,
    GUIDED_POSE_MAX_ROLL_DEG,
    GUIDED_POSE_MAX_STEP_DEG,
    GUIDED_POSE_MIN_INFERENCE_FPS,
    GUIDED_POSE_REPROJECTION_MAX_PX,
    GUIDED_POSE_STABILITY_MAX_DEG,
    GUIDED_POSE_STABILITY_WINDOW_SECONDS,
    GUIDED_POSE_STABLE_FRAMES,
    GUIDED_POSE_TIMEOUT_SECONDS,
    GUIDED_POSE_UNRELIABLE_FRAME_LIMIT,
    GUIDED_SIDE_CROSS_AXIS_MAX_DEG,
    GUIDED_SIDE_YAW_MAX_DEG,
    GUIDED_SIDE_YAW_MIN_DEG,
    GUIDED_VERTICAL_CROSS_AXIS_MAX_DEG,
    GUIDED_VERTICAL_PITCH_MAX_DEG,
    GUIDED_VERTICAL_PITCH_MIN_DEG,
    EMBEDDING_DIMENSIONS,
    ENROLLMENT_IDENTITY_THRESHOLD,
    POSES,
    STALE_FRAME_SECONDS,
)


POSE_DIRECTIONS = {
    "frontal": "Nhìn thẳng vào camera",
    "left": "Quay đầu sang trái",
    "right": "Quay đầu sang phải",
    "up": "Ngẩng đầu lên",
    "down": "Cúi đầu xuống",
}


def wrap_degrees(value):
    """Wrap an angle to [-180, 180), avoiding discontinuities at 360 degrees."""
    value = float(value)
    if not np.isfinite(value):
        raise ValueError("Angle must be finite.")
    return (value + 180.0) % 360.0 - 180.0


def angular_delta_degrees(first, second):
    """Smallest signed difference from first to second, with wrap handling."""
    return wrap_degrees(float(second) - float(first))


def normalize_rotation_matrix(value):
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("Expected a finite 3x3 rotation matrix.")
    if np.linalg.det(matrix) <= 0.0:
        raise ValueError("Pose rotation matrix is reflected or singular.")
    if np.linalg.norm(matrix.T @ matrix - np.eye(3), ord="fro") > 0.05:
        raise ValueError("Pose rotation matrix is not orthonormal.")
    left, _singular, right = np.linalg.svd(matrix)
    correction = np.eye(3)
    correction[2, 2] = 1.0 if np.linalg.det(left @ right) >= 0.0 else -1.0
    result = left @ correction @ right
    if np.linalg.det(result) <= 0.0:
        raise ValueError("Could not normalize pose rotation matrix.")
    return result


def rotation_distance_degrees(first, second):
    """Geodesic SO(3) distance; stable around Euler angle wrap boundaries."""
    a = normalize_rotation_matrix(first)
    b = normalize_rotation_matrix(second)
    relative = a.T @ b
    cosine = float(np.clip((np.trace(relative) - 1.0) * 0.5, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def average_rotation_matrices(matrices):
    """Project the arithmetic matrix mean back onto SO(3) with SVD."""
    matrices = [normalize_rotation_matrix(item) for item in matrices]
    if not matrices:
        raise ValueError("At least one rotation is required for calibration.")
    mean = np.mean(np.stack(matrices), axis=0)
    left, _singular, right = np.linalg.svd(mean)
    correction = np.eye(3)
    correction[2, 2] = 1.0 if np.linalg.det(left @ right) >= 0.0 else -1.0
    return normalize_rotation_matrix(left @ correction @ right)


def relative_pose_angles(reference_rotation, current_rotation):
    """Decompose relative rotation into yaw(Y), pitch(X), then roll(Z).

    The order is ``R_y(yaw) @ R_x(-pitch) @ R_z(roll)`` in the face-model
    coordinate system. Positive yaw means turn left and positive pitch means
    look up. This is a proper Euler decomposition; Rodrigues axis-angle vector
    components are deliberately not treated as Euler angles.
    """
    reference = normalize_rotation_matrix(reference_rotation)
    current = normalize_rotation_matrix(current_rotation)
    relative = reference.T @ current
    # For R = Ry(yaw) Rx(a) Rz(roll), R[1,2] = -sin(a).
    # We define positive pitch as looking up, so pitch = -a.
    sin_a = float(np.clip(-relative[1, 2], -1.0, 1.0))
    a = math.asin(sin_a)
    cos_a = math.cos(a)
    if abs(cos_a) < 0.15:
        raise ValueError("Relative pose is near Euler gimbal lock.")
    yaw = math.degrees(math.atan2(relative[0, 2], relative[2, 2]))
    pitch = -math.degrees(a)
    roll = math.degrees(math.atan2(relative[1, 0], relative[1, 1]))
    yaw, pitch, roll = map(wrap_degrees, (yaw, pitch, roll))

    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    ca, sa = math.cos(math.radians(-pitch)), math.sin(math.radians(-pitch))
    cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    reconstructed = np.asarray([
        [cy * cr + sy * sa * sr, -cy * sr + sy * sa * cr, sy * ca],
        [ca * sr, ca * cr, -sa],
        [-sy * cr + cy * sa * sr, sy * sr + cy * sa * cr, cy * ca],
    ], dtype=np.float64)
    if np.linalg.norm(relative - reconstructed, ord="fro") > 1e-5:
        raise ValueError("Relative pose Euler decomposition is inconsistent.")
    return {"yaw": yaw, "pitch": pitch, "roll": roll,
            "relative_rotation": relative}


def classify_relative_pose(yaw, pitch, roll=0.0):
    """Classify configured guided zones; angle settings are bootstrap values."""
    yaw, pitch, roll = map(float, (yaw, pitch, roll))
    if not all(np.isfinite(value) for value in (yaw, pitch, roll)):
        return "unreliable"
    if abs(roll) > GUIDED_POSE_MAX_ROLL_DEG:
        return "between"
    if (abs(yaw) <= GUIDED_FRONTAL_YAW_MAX_DEG
            and abs(pitch) <= GUIDED_FRONTAL_PITCH_MAX_DEG):
        return "frontal"
    if (GUIDED_SIDE_YAW_MIN_DEG <= yaw <= GUIDED_SIDE_YAW_MAX_DEG
            and abs(pitch) <= GUIDED_SIDE_CROSS_AXIS_MAX_DEG):
        return "left"
    if (-GUIDED_SIDE_YAW_MAX_DEG <= yaw <= -GUIDED_SIDE_YAW_MIN_DEG
            and abs(pitch) <= GUIDED_SIDE_CROSS_AXIS_MAX_DEG):
        return "right"
    if (GUIDED_VERTICAL_PITCH_MIN_DEG <= pitch <= GUIDED_VERTICAL_PITCH_MAX_DEG
            and abs(yaw) <= GUIDED_VERTICAL_CROSS_AXIS_MAX_DEG):
        return "up"
    if (-GUIDED_VERTICAL_PITCH_MAX_DEG <= pitch <= -GUIDED_VERTICAL_PITCH_MIN_DEG
            and abs(yaw) <= GUIDED_VERTICAL_CROSS_AXIS_MAX_DEG):
        return "down"
    return "between"


def assess_frontal_camera_alignment(face, pose_data):
    """Check broad camera-facing geometry before creating a personal reference.

    SCRFD's five keypoints are eye centers, nose tip, and mouth corners; they do
    not encode pupil direction. A broad solvePnP yaw bound is combined with
    landmark spread, nose offset, and eye-line tilt so no single uncalibrated
    Euler value can authorize frontal calibration by itself.
    """
    try:
        points = np.asarray(face.get("keypoints"), dtype=np.float64)
        box = np.asarray(face.get("bbox"), dtype=np.float64).reshape(-1)
        raw_yaw = float(pose_data.get("raw_yaw", pose_data.get("yaw")))
    except (AttributeError, TypeError, ValueError):
        return False, "Không đủ landmark/pose để xác nhận mặt hướng về camera.", {}
    if (points.shape != (5, 2) or not np.all(np.isfinite(points))
            or box.size != 4 or not np.all(np.isfinite(box))):
        return False, "Landmark SCRFD không đủ tin cậy để hiệu chỉnh frontal.", {}
    x1, y1, x2, y2 = box
    face_width, face_height = x2 - x1, y2 - y1
    if face_width <= 0.0 or face_height <= 0.0 or not np.isfinite(raw_yaw):
        return False, "Kích thước mặt hoặc raw yaw không hợp lệ.", {}

    eye_vector = points[1] - points[0]
    eye_span = float(np.linalg.norm(eye_vector)) / face_height
    mouth_span = float(np.linalg.norm(points[4] - points[3])) / face_height
    nose_offset = abs(float(points[2, 0] - np.mean(points[:2, 0]))) / face_width
    eye_tilt = abs(math.degrees(math.atan2(float(eye_vector[1]), float(eye_vector[0]))))
    metrics = {
        "raw_yaw": raw_yaw,
        "eye_span_face_height": eye_span,
        "mouth_span_face_height": mouth_span,
        "nose_offset_face_width": nose_offset,
        "eye_line_tilt_deg": eye_tilt,
    }
    # These limits deliberately allow ordinary left/right eye and facial
    # asymmetry while rejecting a clear profile or unreliable point layout.
    failures = []
    if abs(raw_yaw) > GUIDED_CALIBRATION_MAX_RAW_YAW_DEG:
        failures.append(
            f"yaw sơ bộ {raw_yaw:+.1f}° vượt ±{GUIDED_CALIBRATION_MAX_RAW_YAW_DEG:.0f}°"
        )
    if eye_span < GUIDED_CALIBRATION_MIN_EYE_SPAN_FACE_HEIGHT:
        failures.append("khoảng cách hai tâm mắt quá hẹp so với chiều cao mặt")
    if mouth_span < GUIDED_CALIBRATION_MIN_MOUTH_SPAN_FACE_HEIGHT:
        failures.append("bề rộng miệng nhìn thấy quá hẹp")
    if nose_offset > GUIDED_CALIBRATION_MAX_NOSE_OFFSET_FACE_WIDTH:
        failures.append("mũi lệch nhiều khỏi trục giữa hai mắt")
    if eye_tilt > GUIDED_CALIBRATION_MAX_EYE_LINE_TILT_DEG:
        failures.append("đường mắt nghiêng quá mức để xác nhận frontal")
    if failures:
        return False, "Chưa xác nhận được mặt hướng về camera: " + "; ".join(failures) + ".", metrics
    return True, "Frontal camera-facing check PASS.", metrics


class GuidedPoseTracker:
    """Calibrate from a stable frontal reference and emit one best frame per pose."""

    def __init__(self, stable_frames=GUIDED_POSE_STABLE_FRAMES,
                 max_stability_deg=GUIDED_POSE_STABILITY_MAX_DEG,
                 max_step_deg=GUIDED_POSE_MAX_STEP_DEG,
                 stability_window_seconds=GUIDED_POSE_STABILITY_WINDOW_SECONDS,
                 max_interframe_gap_seconds=GUIDED_POSE_MAX_INTERFRAME_GAP_SECONDS,
                 min_inference_fps=GUIDED_POSE_MIN_INFERENCE_FPS,
                 same_person_threshold=ENROLLMENT_IDENTITY_THRESHOLD,
                 max_reprojection_px=GUIDED_POSE_REPROJECTION_MAX_PX,
                 unreliable_frame_limit=GUIDED_POSE_UNRELIABLE_FRAME_LIMIT,
                 pose_timeout_seconds=GUIDED_POSE_TIMEOUT_SECONDS,
                 stale_seconds=STALE_FRAME_SECONDS):
        self.stable_frames = int(stable_frames)
        self.max_stability_deg = float(max_stability_deg)
        self.max_step_deg = float(max_step_deg)
        self.stability_window_seconds = float(stability_window_seconds)
        self.max_interframe_gap_seconds = float(max_interframe_gap_seconds)
        self.min_inference_fps = float(min_inference_fps)
        self.same_person_threshold = float(same_person_threshold)
        self.max_reprojection_px = float(max_reprojection_px)
        self.unreliable_frame_limit = int(unreliable_frame_limit)
        self.pose_timeout_seconds = float(pose_timeout_seconds)
        self.stale_seconds = float(stale_seconds)
        if (self.stable_frames < 2 or self.max_stability_deg <= 0 or self.max_step_deg <= 0
                or self.stability_window_seconds <= 0
                or self.max_interframe_gap_seconds <= 0
                or not 0.0 <= self.min_inference_fps
                or not -1.0 <= self.same_person_threshold <= 1.0):
            raise ValueError("Pose stability settings are invalid.")
        if (self.max_reprojection_px <= 0 or self.unreliable_frame_limit < 1
                or self.pose_timeout_seconds <= 0
                or self.stale_seconds <= 0):
            raise ValueError("Pose reliability settings are invalid.")
        self.reference_rotation = None
        self.expected_pose = None
        self.window = []
        self.last_sequence = -1
        self.unreliable_count = 0
        self.capture_issued = False
        self.manual_fallback = False
        self.pose_started_at = None
        self.stability_window_expirations = 0
        self.stale_frame_count = 0
        self.identity_reference = None
        self.last_valid_captured_at = None
        self.inference_times = deque(maxlen=32)
        self.inference_fps = None
        self.low_fps_since = None
        self.pending_candidate = None
        self.last_observation_time = None

    @property
    def stable_count(self):
        return len(self.window)

    def _clear_window(self):
        self.window = []
        self.capture_issued = False
        self.pending_candidate = None

    def _response(self, status, **values):
        response = {"status": status, "stable_count": self.stable_count,
                    "valid_frames": self.stable_count,
                    "inference_fps": self.inference_fps,
                    "pose_timeout_seconds": self.pose_timeout_seconds,
                    "time_remaining_seconds": self._time_remaining()}
        response.update(values)
        return response

    def _time_remaining(self):
        if self.pose_started_at is None or self.last_observation_time is None:
            return self.pose_timeout_seconds
        return max(0.0, self.pose_timeout_seconds - max(
            0.0, self.last_observation_time - self.pose_started_at
        ))

    def _update_inference_rate(self, now):
        now = float(now)
        if self.inference_times and now <= self.inference_times[-1]:
            return
        self.inference_times.append(now)
        # Keep the last interval even if it exceeds the capture window: a
        # delayed inference is itself useful low-throughput evidence.
        while (len(self.inference_times) > 2
               and now - self.inference_times[0] > self.stability_window_seconds):
            self.inference_times.popleft()
        if len(self.inference_times) >= 2:
            duration = self.inference_times[-1] - self.inference_times[0]
            self.inference_fps = ((len(self.inference_times) - 1) / duration
                                  if duration > 0 else None)

    def _prune_window(self, captured_at):
        if not self.window:
            return False
        captured_at = float(captured_at)
        latest_gap = captured_at - float(self.window[-1]["captured_at"])
        if latest_gap > self.max_interframe_gap_seconds:
            self._clear_window()
            self.stability_window_expirations += 1
            return True
        expired = False
        if self.window:
            original_size = len(self.window)
            self.window = [
                item for item in self.window
                if captured_at - float(item["captured_at"]) <= self.stability_window_seconds
            ]
            if len(self.window) != original_size:
                self.stability_window_expirations += 1
                expired = True
            if not self.window:
                self.capture_issued = False
        return expired

    def _low_fps_reason(self, now):
        required = max(
            self.min_inference_fps,
            (self.stable_frames - 1) / self.stability_window_seconds,
        )
        if (self.inference_fps is None or len(self.inference_times) < 2
                or self.inference_times[-1] - self.inference_times[0]
                < GUIDED_POSE_FPS_DIAGNOSTIC_SECONDS
                or self.inference_fps >= required):
            self.low_fps_since = None
            return None
        if self.low_fps_since is None:
            self.low_fps_since = float(now)
        return (
            f"FPS inference thấp: {self.inference_fps:.1f} FPS; cần tối thiểu "
            f"{max(self.min_inference_fps, required):.1f} FPS để thu đủ "
            f"{self.stable_frames} frame trong {self.stability_window_seconds:.1f}s."
        )

    def note_missing_frame(self, now=None):
        """Keep brief camera hiccups visible; expire candidates after the gap limit."""
        now = time.monotonic() if now is None else float(now)
        self.last_observation_time = now
        self._prune_window(now)
        low_fps_reason = self._low_fps_reason(now)
        return self._response(
            "LOW_FPS" if low_fps_reason else "STALE_FRAME",
            reason=low_fps_reason or "Chưa có frame mới từ camera.",
            stale_frame_count=self.stale_frame_count,
        )

    def note_repeated_frame(self, now=None):
        """Report a repeated FramePump packet without counting it as a sample."""
        now = time.monotonic() if now is None else float(now)
        self.last_observation_time = now
        self.stale_frame_count += 1
        self._prune_window(now)
        low_fps_reason = self._low_fps_reason(now)
        reason = "Frame trùng từ camera; đang chờ frame mới."
        if low_fps_reason:
            reason = f"{reason} {low_fps_reason}"
        return self._response("STALE_FRAME", reason=reason,
                              stale_frame_count=self.stale_frame_count)

    def reset(self):
        self.reference_rotation = None
        self.expected_pose = None
        self.unreliable_count = 0
        self.manual_fallback = False
        self.pose_started_at = None
        self.stability_window_expirations = 0
        self.stale_frame_count = 0
        self.identity_reference = None
        self.last_valid_captured_at = None
        self.inference_times.clear()
        self.inference_fps = None
        self.low_fps_since = None
        self.last_sequence = -1
        self.pending_candidate = None
        self.last_observation_time = None
        self._clear_window()

    def force_manual_fallback(self, reason):
        self.manual_fallback = True
        self._clear_window()
        return self._response("AUTO_PAUSED", reason=str(reason))

    def _unreliable(self, reason):
        self.unreliable_count += 1
        if self.unreliable_count >= self.unreliable_frame_limit:
            return self.force_manual_fallback(
                f"Pose chưa đủ tin cậy sau {self.unreliable_count} frame: {reason}"
            )
        return self._response("POSE_UNRELIABLE", reason=str(reason),
                              unreliable_count=self.unreliable_count)

    def _timeout_reason(self, expected_pose):
        reasons = []
        required_fps = max(
                self.min_inference_fps,
                (self.stable_frames - 1) / self.stability_window_seconds,
        )
        if self.inference_fps is not None and self.inference_fps < required_fps:
            reasons.append(
                f"FPS inference thấp: {self.inference_fps:.1f}; cần ít nhất "
                f"{required_fps:.1f} FPS để gom {self.stable_frames} frame "
                f"trong {self.stability_window_seconds:.1f}s"
            )
        elif self.stability_window_expirations:
            reasons.append(
                f"Cửa sổ {self.stable_frames} frame/{self.stability_window_seconds:.1f}s "
                f"đã hết hạn {self.stability_window_expirations} lần."
            )
        if self.stale_frame_count:
            reasons.append(
                f"{self.stale_frame_count} frame cũ hoặc trùng, có thể do camera chậm "
                "hoặc inference chậm"
            )
        if not reasons:
            return (f"Pose {expected_pose} chưa đạt quality/hướng đáng tin cậy trong "
                    f"{self.pose_timeout_seconds:.0f}s.")
        return (
            f"Pose {expected_pose} quá {self.pose_timeout_seconds:.0f}s: "
            + "; ".join(reasons)
            + ". AUTO tạm dừng; chọn MANUAL để tiếp tục hoặc khởi động lại AUTO."
        )

    def observe(self, expected_pose, outcome, frame, sequence, captured_at, now=None):
        """Consume one unique fresh quality-valid frame from the FramePump."""
        now = time.monotonic() if now is None else float(now)
        self.last_observation_time = now
        if expected_pose not in POSES:
            self._clear_window()
            return self._response("COMPLETE")
        if expected_pose != self.expected_pose:
            self.expected_pose = expected_pose
            self.pose_started_at = now
            self.stability_window_expirations = 0
            self.stale_frame_count = 0
            self._clear_window()
            self.unreliable_count = 0
        if self.manual_fallback:
            return self._response(
                "AUTO_PAUSED",
                reason="AUTO đã tạm dừng; cần chọn MANUAL hoặc khởi động lại AUTO.",
            )
        if (self.pose_started_at is not None
                and now - self.pose_started_at >= self.pose_timeout_seconds):
            return self.force_manual_fallback(self._timeout_reason(expected_pose))

        try:
            sequence = int(sequence)
            age = now - float(captured_at)
        except (TypeError, ValueError):
            self.stale_frame_count += 1
            self._prune_window(now)
            return self._response("STALE_FRAME", reason="Timestamp/frame sequence invalid.",
                                  stale_frame_count=self.stale_frame_count)
        if sequence <= self.last_sequence:
            self.stale_frame_count += 1
            self._prune_window(now)
            return self._response("STALE_FRAME", reason="Frame sequence is repeated; ignored.",
                                  stale_frame_count=self.stale_frame_count)
        self.last_sequence = sequence
        self._update_inference_rate(now)
        try:
            captured_at = float(captured_at)
        except (TypeError, ValueError):
            captured_at = float("nan")
        if (self.last_valid_captured_at is not None
                and np.isfinite(captured_at)
                and captured_at <= self.last_valid_captured_at):
            self.stale_frame_count += 1
            self._prune_window(now)
            return self._response("STALE_FRAME",
                                  reason="Timestamp không mới hơn mẫu đã nhận; bỏ frame trùng.",
                                  stale_frame_count=self.stale_frame_count)
        if not np.isfinite(age) or age < -0.1 or age > self.stale_seconds:
            self.stale_frame_count += 1
            self._prune_window(now)
            low_fps_reason = self._low_fps_reason(now)
            reason = "Frame is outside the freshness window."
            if low_fps_reason:
                reason = f"{reason} {low_fps_reason}"
            return self._response("STALE_FRAME", reason=reason,
                                  stale_frame_count=self.stale_frame_count)
        window_expired = self._prune_window(float(captured_at))
        if not isinstance(outcome, dict) or outcome.get("status") != "OK":
            code = str(outcome.get("code", "QUALITY CHECK")).upper() \
                if isinstance(outcome, dict) else "QUALITY CHECK"
            reason = str(outcome.get("reason") or code) if isinstance(outcome, dict) else code
            # Multiple faces invalidate identity continuity; a brief blur/no-face
            # result only skips that sample and leaves the bounded time window intact.
            if code in {"MULTIPLE FACES", "MULTIPLE_FACE"}:
                self._clear_window()
            low_fps_reason = self._low_fps_reason(now)
            return self._response("QUALITY_REJECTED", reason=reason,
                                  rejected_code=code, fps_reason=low_fps_reason)

        face = outcome.get("face")
        face_count = outcome.get("face_count")
        diagnostics = outcome.get("diagnostics") or {}
        faces = outcome.get("faces")
        if isinstance(faces, (list, tuple)) and len(faces) > 1:
            face_count = len(faces)
        if face_count is None:
            face_count = diagnostics.get("face_count")
        if face_count is None:
            face_count = (len(faces) if isinstance(faces, (list, tuple))
                          else 1 if isinstance(face, dict) else 0)
        try:
            face_count = int(face_count)
        except (TypeError, ValueError):
            face_count = 0
        if face_count != 1:
            if face_count > 1:
                self._clear_window()
                return self._response("QUALITY_REJECTED", rejected_code="MULTIPLE FACES",
                                      reason="Chỉ được có đúng một khuôn mặt trong khung.")
            return self._response("QUALITY_REJECTED", rejected_code="NO FACE",
                                  reason="Không tìm thấy khuôn mặt hợp lệ.")

        embedding = None
        if outcome.get("embedding") is not None:
            try:
                embedding = face_matching.normalize_embedding(
                    outcome.get("embedding"), EMBEDDING_DIMENSIONS
                )
            except (TypeError, ValueError) as exc:
                return self._response("IDENTITY_MISMATCH", rejected_code="INVALID EMBEDDING",
                                      reason=f"Embedding không hợp lệ: {exc}")
        identity_anchor = self.identity_reference
        if identity_anchor is None and self.window:
            identity_anchor = next((item.get("embedding") for item in self.window
                                     if item.get("embedding") is not None), None)
        if identity_anchor is not None and embedding is not None:
            try:
                similarity = face_matching.cosine_similarity(identity_anchor, embedding)
            except (TypeError, ValueError) as exc:
                return self._response("IDENTITY_MISMATCH", reason=f"Embedding lỗi: {exc}")
            if similarity < self.same_person_threshold:
                self._clear_window()
                return self._response(
                    "IDENTITY_MISMATCH", reason=(
                        f"Khuôn mặt không nhất quán với mẫu frontal: cosine={similarity:.3f}, "
                        f"cần ≥ {self.same_person_threshold:.3f}."
                    ), similarity=similarity,
                )

        pose_data = face.get("head_pose") if isinstance(face, dict) else None
        if not isinstance(pose_data, dict):
            return self._unreliable("solvePnP did not return a rotation.")
        try:
            rotation = normalize_rotation_matrix(pose_data["rotation_matrix"])
            reprojection_error = float(pose_data["reprojection_error_px"])
            positive_depth = bool(pose_data.get("positive_depth", True))
        except (KeyError, TypeError, ValueError) as exc:
            return self._unreliable(f"invalid rotation/reprojection ({exc}).")
        if (not positive_depth or not np.isfinite(reprojection_error)
                or reprojection_error > self.max_reprojection_px):
            raw_yaw = pose_data.get("raw_yaw", pose_data.get("yaw"))
            raw_pitch = pose_data.get("raw_pitch", pose_data.get("pitch"))
            return self._unreliable(
                f"reprojection={reprojection_error:.1f}px (limit {self.max_reprojection_px:.1f}px), "
                f"positive_depth={positive_depth}, raw_yaw={raw_yaw}, raw_pitch={raw_pitch}."
            )
        self.unreliable_count = 0

        if expected_pose == "frontal" and self.reference_rotation is None:
            frontal_ok, frontal_reason, frontal_metrics = assess_frontal_camera_alignment(
                face, pose_data
            )
            if not frontal_ok:
                return self._response(
                    "POSE_NOT_READY",
                    detected_pose="between", expected_pose="frontal", yaw=None, pitch=None,
                    roll=None, raw_yaw=frontal_metrics.get("raw_yaw"),
                    raw_pitch=pose_data.get("raw_pitch", pose_data.get("pitch")),
                    reprojection_error_px=reprojection_error, calibrating=True,
                    frontal_view=frontal_metrics,
                    frontal_ok=False,
                    reason=(frontal_reason + " Raw pitch chỉ là thông tin debug; "
                            "nhìn thẳng tự nhiên, không cần căn hai mắt cân đối."),
                )
            # There is no calibrated angle until a stable frontal reference has
            # been collected. Keep it unset instead of displaying fabricated 0°.
            angles = None
            detected_pose = "frontal"
            calibrating = True
            frontal_ok = True
        else:
            try:
                angles = relative_pose_angles(self.reference_rotation, rotation)
            except (TypeError, ValueError) as exc:
                return self._unreliable(f"relative Euler pose failed ({exc}).")
            detected_pose = classify_relative_pose(angles["yaw"], angles["pitch"], angles["roll"])
            calibrating = False
            frontal_ok = None
            frontal_metrics = None
            if detected_pose != expected_pose:
                return self._response(
                    "WRONG_POSE", detected_pose=detected_pose,
                    expected_pose=expected_pose, yaw=angles["yaw"],
                    pitch=angles["pitch"], roll=angles["roll"],
                    reprojection_error_px=reprojection_error,
                    frontal_view=None,
                    frontal_ok=None,
                    reason=(f"Sai hướng: yêu cầu {expected_pose}, hiện phát hiện "
                            f"{detected_pose} (yaw={angles['yaw']:+.1f}°, "
                            f"pitch={angles['pitch']:+.1f}°)."),
                )

        if self.capture_issued:
            return self._response("CAPTURE_PENDING", detected_pose=detected_pose,
                    expected_pose=expected_pose,
                    yaw=None if angles is None else angles["yaw"],
                    pitch=None if angles is None else angles["pitch"],
                    roll=None if angles is None else angles["roll"])

        step_reset = False
        trimmed_unstable = False
        if self.window:
            max_delta = rotation_distance_degrees(self.window[-1]["rotation"], rotation)
            if max_delta > self.max_step_deg:
                self._clear_window()
                step_reset = True
        quality = outcome.get("quality") or {}
        try:
            sharpness = float(quality.get("sharpness", 0.0))
        except (TypeError, ValueError):
            sharpness = 0.0
        if not np.isfinite(sharpness):
            sharpness = 0.0
        reported_angles = {
            "yaw": None if angles is None else angles["yaw"],
            "pitch": None if angles is None else angles["pitch"],
            "roll": None if angles is None else angles["roll"],
        }
        self.window.append({
            "rotation": rotation,
            "sequence": sequence,
            "captured_at": float(captured_at),
            "sharpness": sharpness,
            "frame": np.asarray(frame).copy(),
            "outcome": outcome,
            "embedding": None if embedding is None else embedding.copy(),
            **reported_angles,
            "reprojection_error_px": reprojection_error,
        })
        self.window = self.window[-self.stable_frames:]
        # Keep the newest mutually stable cluster instead of throwing away all
        # progress after gradual movement or one outlying valid pose estimate.
        while len(self.window) > 1:
            spread = max(
                rotation_distance_degrees(first["rotation"], second["rotation"])
                for index, first in enumerate(self.window)
                for second in self.window[index + 1:]
            )
            if spread <= self.max_stability_deg:
                break
            self.window.pop(0)
            trimmed_unstable = True
        self.last_valid_captured_at = float(captured_at)
        if self.stable_count < self.stable_frames:
            low_fps_reason = self._low_fps_reason(now)
            return self._response(
                    "LOW_FPS" if low_fps_reason else "STABILIZING",
                    detected_pose=detected_pose,
                    expected_pose=expected_pose,
                    yaw=None if angles is None else angles["yaw"],
                    pitch=None if angles is None else angles["pitch"],
                    roll=None if angles is None else angles["roll"],
                    reprojection_error_px=reprojection_error,
                    calibrating=calibrating,
                    frontal_view=frontal_metrics,
                    frontal_ok=frontal_ok,
                    stability_window_expirations=self.stability_window_expirations,
                    reason=low_fps_reason or (
                        f"Đã bỏ frame cũ/dao động khỏi cửa sổ; còn {self.stable_count} frame ổn định."
                        if trimmed_unstable else (
                            f"Đã bỏ các mẫu cũ ngoài cửa sổ {self.stability_window_seconds:.1f}s; "
                            "đang gom lại frame hợp lệ."
                            if window_expired else (
                                f"Đầu di chuyển nhanh hơn {self.max_step_deg:.1f}° giữa frame; "
                                "đang gom lại."
                                if step_reset else None
                            )
                        )
                    ))

        reference = (average_rotation_matrices([item["rotation"] for item in self.window])
                     if calibrating else self.reference_rotation)
        candidate = max(self.window, key=lambda item: item["sharpness"])
        if calibrating:
            angles = relative_pose_angles(reference, candidate["rotation"])
        self.capture_issued = True
        candidate["calibrated_reference"] = reference.copy() if calibrating else None
        candidate["calibrating"] = calibrating
        self.pending_candidate = dict(candidate)
        low_fps_reason = self._low_fps_reason(now)
        return self._response(
            "CAPTURE_READY", detected_pose=detected_pose,
            expected_pose=expected_pose,
            yaw=None if angles is None else angles["yaw"],
            pitch=None if angles is None else angles["pitch"],
            roll=None if angles is None else angles["roll"],
            reprojection_error_px=reprojection_error,
            calibrating=calibrating, frontal_view=frontal_metrics,
            frontal_ok=frontal_ok, candidate=candidate,
            fps_reason=low_fps_reason)

    def validate_selected_candidate(self, candidate, outcome, expected_pose):
        """Bind an ArcFace embedding to the already pose/quality-validated frame."""
        if not isinstance(candidate, dict) or not isinstance(outcome, dict):
            return {"status": "RETRY", "code": "INVALID CANDIDATE",
                    "reason": "Mẫu AUTO đã chọn không hợp lệ."}
        if outcome.get("status") != "OK":
            return {"status": "RETRY", "code": outcome.get("code", "QUALITY CHECK"),
                    "reason": outcome.get("reason", "Quality gate không đạt.")}
        faces = outcome.get("faces")
        face_count = outcome.get("face_count", len(faces) if isinstance(faces, (list, tuple)) else 1)
        try:
            face_count = int(face_count)
        except (TypeError, ValueError):
            face_count = 0
        if face_count != 1:
            return {"status": "RETRY", "code": "MULTIPLE FACES" if face_count > 1 else "NO FACE",
                    "reason": "Frame được chọn không còn đúng một khuôn mặt."}
        face = outcome.get("face")
        quality = outcome.get("quality") or {}
        if not isinstance(face, dict) or quality.get("ready") is not True:
            return {"status": "RETRY", "code": "QUALITY CHECK",
                    "reason": "Quality gate của frame được chọn không đạt."}
        try:
            embedding = face_matching.normalize_embedding(
                outcome.get("embedding"), EMBEDDING_DIMENSIONS
            )
            pose_data = face.get("head_pose") or {}
            rotation = normalize_rotation_matrix(pose_data["rotation_matrix"])
            reprojection = float(pose_data["reprojection_error_px"])
            positive_depth = bool(pose_data.get("positive_depth", True))
            selected_rotation = normalize_rotation_matrix(candidate["rotation"])
        except (KeyError, TypeError, ValueError) as exc:
            return {"status": "RETRY", "code": "INVALID POSE OR EMBEDDING",
                    "reason": f"Frame được chọn không hợp lệ: {exc}."}
        if (not positive_depth or not np.isfinite(reprojection)
                or reprojection > self.max_reprojection_px):
            return {"status": "RETRY", "code": "POSE UNRELIABLE",
                    "reason": (f"Pose của frame đã chọn không đáng tin cậy: reprojection="
                               f"{reprojection:.1f}px, positive_depth={positive_depth}.")}
        same_frame_delta = rotation_distance_degrees(selected_rotation, rotation)
        if same_frame_delta > self.max_stability_deg:
            return {"status": "RETRY", "code": "POSE CHANGED",
                    "reason": (f"Pose khi trích embedding khác frame đã xét "
                               f"({same_frame_delta:.1f}°); đang thu lại mẫu.")}
        if expected_pose == "frontal" and candidate.get("calibrating"):
            valid_front, reason, _metrics = assess_frontal_camera_alignment(
                face, pose_data
            )
            if not valid_front:
                return {"status": "RETRY", "code": "WRONG POSE", "reason": reason}
        else:
            if self.reference_rotation is None:
                return {"status": "RETRY", "code": "FRONTAL REFERENCE MISSING",
                        "reason": "Chưa có frontal reference để xác minh hướng pose."}
            try:
                angles = relative_pose_angles(self.reference_rotation, rotation)
            except (TypeError, ValueError) as exc:
                return {"status": "RETRY", "code": "POSE UNRELIABLE", "reason": str(exc)}
            detected = classify_relative_pose(angles["yaw"], angles["pitch"], angles["roll"])
            if detected != expected_pose:
                return {"status": "RETRY", "code": "WRONG POSE",
                        "reason": (f"Sai hướng ở frame được chọn: yêu cầu {expected_pose}, "
                                   f"phát hiện {detected} (yaw={angles['yaw']:+.1f}°, "
                                   f"pitch={angles['pitch']:+.1f}°).")}
        if self.identity_reference is not None:
            similarity = face_matching.cosine_similarity(self.identity_reference, embedding)
            if similarity < self.same_person_threshold:
                return {"status": "RETRY", "code": "SAME PERSON",
                        "reason": (f"Frame được chọn không khớp mẫu frontal: cosine={similarity:.3f}, "
                                   f"cần ≥ {self.same_person_threshold:.3f}.")}
        return {"status": "OK", "embedding": embedding, "face": face,
                "quality": quality, "pose_delta_deg": same_frame_delta}

    def capture_result(self, captured, next_pose=None, now=None, embedding=None):
        """Advance once after gallery state has accepted the candidate sample."""
        self.capture_issued = False
        if now is not None:
            self.last_observation_time = float(now)
        if captured:
            candidate = self.pending_candidate or {}
            selected_embedding = embedding if embedding is not None else candidate.get("embedding")
            if selected_embedding is not None:
                selected_embedding = face_matching.normalize_embedding(
                    selected_embedding, EMBEDDING_DIMENSIONS
                )
            if candidate.get("calibrating"):
                self.reference_rotation = candidate.get("calibrated_reference")
                self.identity_reference = selected_embedding
            elif self.identity_reference is None:
                self.identity_reference = selected_embedding
            self.expected_pose = next_pose
            self.pose_started_at = (
                (time.monotonic() if now is None else float(now))
                if next_pose in POSES else None
            )
            self.stability_window_expirations = 0
            self.stale_frame_count = 0
            self._clear_window()
            self.unreliable_count = 0
        else:
            self._clear_window()
        self.pending_candidate = None
