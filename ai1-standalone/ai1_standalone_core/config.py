"""Configuration for the standalone app; no production settings are modified."""

from pathlib import Path

import face_matching


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "ai1_standalone_data"
IMAGES_ROOT = DATA_ROOT / "images"
EMPLOYEES_PATH = DATA_ROOT / "employees.json"
EMBEDDINGS_PATH = DATA_ROOT / "embeddings.npz"

MODEL_NAME = "buffalo_l"
EMBEDDING_DIMENSIONS = 512
POSES = ("frontal", "left", "right", "up", "down")
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
FRAME_INTERVAL_MS = 250
STALE_FRAME_SECONDS = 0.75
RECOGNITION_TIMEOUT_SECONDS = 8.5
FRAME_CONSISTENCY_THRESHOLD = 0.60
RECOGNITION_COOLDOWN_SECONDS = 2.0
UNKNOWN_RETRY_INTERVAL_SECONDS = 0.75


RECOGNITION_THRESHOLD = 0.45
ENROLLMENT_IDENTITY_THRESHOLD = float(face_matching.ENROLLMENT_IDENTITY_THRESHOLD)

# Standalone enrollment tolerances for solvePnP angles; signs follow the
# production landmark convention (positive yaw=left, positive pitch=up).
POSE_FRONTAL_YAW_MAX_DEG = 18.0
POSE_FRONTAL_PITCH_MAX_DEG = 18.0
POSE_SIDE_YAW_MIN_DEG = 15.0
POSE_SIDE_YAW_MAX_DEG = 45.0
POSE_SIDE_PITCH_MAX_DEG = 30.0
POSE_VERTICAL_PITCH_MIN_DEG = 15.0
POSE_VERTICAL_PITCH_MAX_DEG = 40.0
POSE_VERTICAL_YAW_MAX_DEG = 25.0
POSE_ENROLLMENT_HYSTERESIS_DEG = 2.0

# Smart Enrollment v2 capture settings. AUTO pose tracking uses SCRFD/landmarks
# only; ArcFace runs once for the sharpest selected candidate. Five fresh,
# quality-valid frames may be collected over a bounded 12-second window so a
# CPU inference rate near 0.5 FPS can still form a stable cluster.
GUIDED_POSE_REPROJECTION_MAX_PX = 18.0
GUIDED_POSE_STABLE_FRAMES = 5
GUIDED_POSE_STABILITY_MAX_DEG = 8.0
GUIDED_POSE_MAX_STEP_DEG = 18.0
GUIDED_POSE_STABILITY_WINDOW_SECONDS = 12.0
GUIDED_POSE_MAX_INTERFRAME_GAP_SECONDS = 12.0
# Five unique frames need at least (5 - 1) / 12 = 0.333 FPS to fit the
# configured window. The tracker computes this dynamically.
GUIDED_POSE_MIN_INFERENCE_FPS = 0.0
GUIDED_POSE_FPS_DIAGNOSTIC_SECONDS = 1.0
GUIDED_POSE_UNRELIABLE_FRAME_LIMIT = 3
GUIDED_POSE_TIMEOUT_SECONDS = 60.0
GUIDED_POSE_MAX_ROLL_DEG = 25.0
# Personalized frontal bootstrap uses a broad solvePnP yaw bound together with
# SCRFD five-point face geometry. Raw pitch is intentionally excluded: the
# current 3D model has a valid frontal Euler branch near 180 degrees.
GUIDED_CALIBRATION_MAX_RAW_YAW_DEG = 35.0
GUIDED_CALIBRATION_MIN_EYE_SPAN_FACE_HEIGHT = 0.14
GUIDED_CALIBRATION_MIN_MOUTH_SPAN_FACE_HEIGHT = 0.10
GUIDED_CALIBRATION_MAX_NOSE_OFFSET_FACE_WIDTH = 0.25
GUIDED_CALIBRATION_MAX_EYE_LINE_TILT_DEG = 35.0
GUIDED_FRONTAL_YAW_MAX_DEG = 9.0
GUIDED_FRONTAL_PITCH_MAX_DEG = 9.0
GUIDED_SIDE_YAW_MIN_DEG = 15.0
GUIDED_SIDE_YAW_MAX_DEG = 40.0
GUIDED_SIDE_CROSS_AXIS_MAX_DEG = 14.0
GUIDED_VERTICAL_PITCH_MIN_DEG = 15.0
GUIDED_VERTICAL_PITCH_MAX_DEG = 38.0
GUIDED_VERTICAL_CROSS_AXIS_MAX_DEG = 14.0

ENROLLMENT_CENTER_TOLERANCE = (0.60, 0.55)
ENROLLMENT_MAX_SIZE_RATIO = (1.35, 1.20)
ENROLLMENT_EDGE_MARGIN_RATIO = 0.04
