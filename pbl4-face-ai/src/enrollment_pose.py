"""Five-point enrollment pose checks shared by the service and desktop tools.

Landmarks order from InsightFace 2D 5 keypoints:
  [0]: left_eye (in image coordinates, smaller x)
  [1]: right_eye (in image coordinates, larger x)
  [2]: nose
  [3]: mouth_left (smaller x)
  [4]: mouth_right (larger x)
"""
import math

POSES = ("frontal", "left", "right", "up", "down")

# Yaw thresholds:
# On a mirrored image (standard selfie/kiosk mirror preview):
# - Turning to user's left moves nose to the left (smaller x) -> dist_right > dist_left -> yaw > 0.
# - Turning to user's right moves nose to the right (larger x) -> dist_left > dist_right -> yaw < 0.
YAW_THRESHOLD = 0.09      # Relaxed from 0.22 to allow natural 10-15 degree gentle turn
YAW_FRONTAL_MAX = 0.12    # Frontal max yaw deviation

# Pitch thresholds (ratio = (nose_y - eye_y) / vertical_eye_to_mouth):
# Normal resting face with camera at chest/table height: pitch ~ 0.32 - 0.52
PITCH_UP_THRESHOLD = 0.28   # Looking up tilts nose closer to eye line
PITCH_DOWN_THRESHOLD = 0.65 # Looking down pushes nose closer to mouth line
PITCH_FRONTAL_MIN = 0.25
PITCH_FRONTAL_MAX = 0.68


def estimate_pose(keypoints):
    """Ước lượng tư thế khuôn mặt (frontal, left, right, up, down) từ 5 điểm mốc 2D."""
    if len(keypoints) != 5 or any(len(point) != 2 for point in keypoints):
        raise ValueError("Expected five 2D face landmarks")
    points = [(float(point[0]), float(point[1])) for point in keypoints]
    if not all(math.isfinite(value) for point in points for value in point):
        raise ValueError("Landmarks must be finite")

    left, right, nose, mouth_left, mouth_right = points
    eye_width = math.hypot(right[0] - left[0], right[1] - left[1])
    eye_y = (left[1] + right[1]) / 2.0
    vertical = (mouth_left[1] + mouth_right[1]) / 2.0 - eye_y

    if eye_width <= 1e-6 or vertical <= 1e-6:
        raise ValueError("Degenerate face landmarks")

    # Yaw: tỷ lệ bất đối xứng của mũi giữa hai mắt
    # yaw > 0: nghiêng sang trái (trên ảnh gương); yaw < 0: nghiêng sang phải
    dist_right = abs(right[0] - nose[0])
    dist_left = abs(nose[0] - left[0])
    yaw = (dist_right - dist_left) / eye_width

    # Pitch: tỷ lệ độ cao của mũi giữa mắt và miệng
    pitch = (nose[1] - eye_y) / vertical

    # Ưu tiên kiểm tra Yaw trước để tránh góc nghiêng của camera đặt thấp (như ESP32-CAM)
    # đè bẹp hoàn toàn góc quay trái/phải:
    if abs(yaw) >= YAW_THRESHOLD:
        pose = "left" if yaw > 0 else "right"
    elif pitch < PITCH_UP_THRESHOLD:
        pose = "up"
    elif pitch > PITCH_DOWN_THRESHOLD:
        pose = "down"
    else:
        pose = "frontal"

    metrics = {
        "yaw_diff": round(yaw, 3),
        "pitch_ratio": round(pitch, 3),
        "eye_width": round(eye_width, 1),
    }

    return pose, metrics


def check_pose_match(expected_pose, detected_pose, metrics=None):
    """Kiểm tra xem tư thế hiện tại có thỏa mãn tư thế mong đợi không (có dung sai linh hoạt theo mục tiêu)."""
    if expected_pose not in POSES:
        return False

    if detected_pose == expected_pose:
        return True

    # Nếu có metrics, áp dụng dung sai thông minh theo pose mục tiêu:
    if metrics:
        yaw = float(metrics.get("yaw_diff", 0.0))
        pitch = float(metrics.get("pitch_ratio", 0.45))

        if expected_pose == "left":
            # Đang cần góc trái: chỉ cần yaw lệch sang trái đủ rõ ràng (yaw >= 0.08)
            # cho phép dung sai pitch linh hoạt để người dùng không bị kẹt khi camera hơi thấp
            return yaw >= 0.08 and 0.20 <= pitch <= 0.75

        if expected_pose == "right":
            # Đang cần góc phải: yaw lệch sang phải đủ rõ ràng (yaw <= -0.08)
            return yaw <= -0.08 and 0.20 <= pitch <= 0.75

        if expected_pose == "up":
            # Đang cần ngẩng: pitch thấp hơn ngưỡng bình thường và không bị lệch quay ngang quá nhiều
            return pitch < 0.32 and abs(yaw) <= 0.18

        if expected_pose == "down":
            # Đang cần cúi: pitch cao hơn ngưỡng bình thường
            return pitch > 0.62 and abs(yaw) <= 0.18

        if expected_pose == "frontal":
            # Đang cần chính diện: yaw ở dải trung tâm và pitch trong vùng tự nhiên
            return abs(yaw) <= YAW_FRONTAL_MAX and PITCH_FRONTAL_MIN <= pitch <= PITCH_FRONTAL_MAX

    return False


def get_pose_instruction(expected_pose, detected_pose, metrics=None):
    """Sinh hướng dẫn tiếng Việt rõ ràng, thân thiện giúp người dùng điều chỉnh góc mặt."""
    if expected_pose not in POSES:
        return "Tư thế không hợp lệ."

    yaw = float(metrics.get("yaw_diff", 0.0)) if metrics else 0.0
    pitch = float(metrics.get("pitch_ratio", 0.45)) if metrics else 0.45

    if check_pose_match(expected_pose, detected_pose, metrics):
        labels = {
            "frontal": "Chính diện",
            "left": "Nghiêng trái",
            "right": "Nghiêng phải",
            "up": "Ngẩng nhẹ",
            "down": "Cúi nhẹ",
        }
        return f"🎯 Đúng tư thế: {labels.get(expected_pose, expected_pose)}! Giữ yên để chụp..."

    if expected_pose == "left":
        if yaw < 0.08:
            return "⬅️ Hãy quay đầu nhẹ sang bên TRÁI một chút."
        return "🎯 Đã đạt góc trái, giữ yên..."

    if expected_pose == "right":
        if yaw > -0.08:
            return "➡️ Hãy quay đầu nhẹ sang bên PHẢI một chút."
        return "🎯 Đã đạt góc phải, giữ yên..."

    if expected_pose == "up":
        if pitch >= 0.32:
            return "⬆️ Hãy hơi ngẩng cằm lên trên một chút."
        return "🎯 Đã đạt góc ngẩng, giữ yên..."

    if expected_pose == "down":
        if pitch <= 0.62:
            return "⬇️ Hãy hơi cúi đầu xuống dưới một chút."
        return "🎯 Đã đạt góc cúi, giữ yên..."

    if expected_pose == "frontal":
        if yaw > YAW_FRONTAL_MAX:
            return "Hơi quay đầu sang phải một chút để nhìn thẳng."
        if yaw < -YAW_FRONTAL_MAX:
            return "Hơi quay đầu sang trái một chút để nhìn thẳng."
        if pitch < PITCH_FRONTAL_MIN:
            return "Hạ cằm xuống một chút để nhìn thẳng vào camera."
        if pitch > PITCH_FRONTAL_MAX:
            return "Ngẩng đầu lên một chút để nhìn thẳng vào camera."
        return "Nhìn thẳng vào tâm camera."

    return f"Yêu cầu: {expected_pose} (hiện tại: {detected_pose})"
