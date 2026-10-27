"""Five-point enrollment pose checks shared by the service and desktop tools."""
import math

POSES = ("frontal", "left", "right", "up", "down")


def estimate_pose(keypoints):
    if len(keypoints) != 5 or any(len(point) != 2 for point in keypoints):
        raise ValueError("Expected five 2D face landmarks")
    points = [(float(point[0]), float(point[1])) for point in keypoints]
    if not all(math.isfinite(value) for point in points for value in point):
        raise ValueError("Landmarks must be finite")
    left, right, nose, mouth_left, mouth_right = points
    eye_width = math.hypot(right[0] - left[0], right[1] - left[1])
    eye_y = (left[1] + right[1]) / 2
    vertical = (mouth_left[1] + mouth_right[1]) / 2 - eye_y
    if eye_width <= 1e-6 or vertical <= 1e-6:
        raise ValueError("Degenerate face landmarks")
    yaw = (abs(right[0] - nose[0]) - abs(nose[0] - left[0])) / eye_width
    pitch = (nose[1] - eye_y) / vertical
    if pitch < .42:
        pose = "up"
    elif pitch > .64:
        pose = "down"
    elif yaw > .22:
        pose = "left"
    elif yaw < -.22:
        pose = "right"
    else:
        pose = "frontal"
    return pose, {"yaw_diff": round(yaw, 3), "pitch_ratio": round(pitch, 3)}


def check_pose_match(expected_pose, detected_pose, metrics=None):
    return expected_pose in POSES and expected_pose == detected_pose
