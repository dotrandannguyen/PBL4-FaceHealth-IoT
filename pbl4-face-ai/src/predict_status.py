import sys
import warnings
from collections import deque
from pathlib import Path
import joblib
import numpy as np

# Đảm bảo đường dẫn import src luôn đúng
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from status_features import StatusFeatureExtractor


# Ẩn các cảnh báo phiên bản thừa của thư viện (như scikit-learn, protobuf)
warnings.filterwarnings("ignore")


def calculate_sequence_features(features_list):
    """
    Tính vector đặc trưng tổng hợp từ chuỗi 3 frames.
    features_list: list of dicts (len=3), mỗi dict chứa ear, mar, pitch, yaw, roll
    """
    if len(features_list) != 3:
        return None

    ears = [f['ear'] for f in features_list if f is not None]
    mars = [f['mar'] for f in features_list if f is not None]
    pitches = [f['pitch'] for f in features_list if f is not None]
    rolls = [f['roll'] for f in features_list if f is not None]

    # Cần đủ 3 frame nhận diện được mặt
    if len(ears) < 3:
        return None

    min_ear = min(ears)
    mean_ear = sum(ears) / 3.0
    max_mar = max(mars)
    mean_mar = sum(mars) / 3.0

    delta_pitch = max(pitches) - min(pitches)
    delta_roll = max(rolls) - min(rolls)
    mean_pitch = sum(pitches) / 3.0

    return [min_ear, mean_ear, max_mar, mean_mar, delta_pitch, delta_roll, mean_pitch]


class StatusPredictor:
    """
    Module dự đoán trạng thái thể trạng (Normal / Fatigue / Exhausted)
    Hỗ trợ 2 chế độ:
      1. predict_frame(frame): Cho luồng realtime streaming (1 lần trích xuất/frame, chống giật nhãn, tiết kiệm CPU).
      2. predict_status(frames): Cho batch 3 ảnh chụp tức thời (chấm công snapshot).
    """

    def __init__(self, smoothing_window=5, max_yaw_deg=25.0, max_pitch_deg=35.0):
        # Khởi tạo bộ trích xuất đặc trưng (MediaPipe)
        self.extractor = StatusFeatureExtractor()

        # Load mô hình Random Forest đã train
        model_path = Path(__file__).resolve().parent.parent / "data" / "rf_status_model.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"Chưa có model! Vui lòng chạy train_rf.py trước. Path: {model_path}")

        self.model = joblib.load(model_path)
        self.classes_ = list(getattr(self.model, "classes_", ["Normal", "Fatigue", "Exhausted"]))

        # Cấu hình lọc và làm mịn nhãn
        self.max_yaw_deg = max_yaw_deg
        self.max_pitch_deg = max_pitch_deg
        self.smoothing_window = smoothing_window

        # Buffers nội bộ cho streaming
        self.feature_buffer = deque(maxlen=3)
        self.history_probs = deque(maxlen=smoothing_window)
        self.last_valid_status = "Normal"

    def reset(self):
        """Reset bộ đệm khi chuyển người hoặc bắt đầu phiên mới."""
        self.feature_buffer.clear()
        self.history_probs.clear()
        self.last_valid_status = "Normal"

    def predict_frame(self, frame):
        """
        Dự đoán trạng thái từ từng frame video (tối ưu Streaming Real-time).
        Mỗi frame chỉ chạy MediaPipe trích xuất 1 lần duy nhất, chống lãng phí CPU.
        
        Returns:
            dict chứa thông tin chi tiết:
                - status: "Normal" | "Fatigue" | "Exhausted" | "Turned_Head" | "No_Face"
                - confidence: float (0.0 - 1.0)
                - probabilities: dict từng nhãn
                - ear, mar, pitch, yaw, roll: float
                - is_valid: bool (True nếu đánh giá thành công thể trạng)
        """
        if frame is None:
            return {"status": "No_Face", "desc": "Frame None", "is_valid": False}

        # 1. Trích xuất đặc trưng frame hiện tại
        feats = self.extractor.extract_features(frame)
        if feats is None:
            return {
                "status": "No_Face",
                "desc": "Không thấy khuôn mặt",
                "is_valid": False,
                "confidence": 0.0,
                "ear": 0.0,
                "mar": 0.0,
                "pitch": 0.0,
                "yaw": 0.0,
                "roll": 0.0,
            }

        yaw = float(feats["yaw"])
        pitch = float(feats["pitch"])
        roll = float(feats["roll"])
        ear = float(feats["ear"])
        mar = float(feats["mar"])

        # 2. Lọc góc quay mặt quá lớn (Yaw/Pitch)
        # Theo mô hình 3D solvePnP + RQDecomp3x3:
        # Mặt nhìn thẳng: Yaw ≈ 0°, Roll ≈ 0°, Pitch ≈ ±180°
        yaw_dev = abs(yaw)
        pitch_dev = abs(abs(pitch) - 180.0)

        # Khi ngoảnh mặt quá nghiêng sang hai bên hoặc cúi/ngửa quá mức:
        if yaw_dev > self.max_yaw_deg or pitch_dev > self.max_pitch_deg:
            return {
                "status": "Turned_Head",
                "desc": "Vui lòng nhìn thẳng vào camera",
                "is_valid": False,
                "confidence": 0.0,
                "ear": ear,
                "mar": mar,
                "pitch": pitch,
                "yaw": yaw,
                "roll": roll,
                "pts": feats.get("pts"),
            }

        # 3. Đưa đặc trưng vào bộ đệm chuỗi 3 frame
        self.feature_buffer.append(feats)

        if len(self.feature_buffer) < 3:
            return {
                "status": "Buffering",
                "desc": "Đang phân tích chuỗi chuyển động...",
                "is_valid": False,
                "confidence": 0.0,
                "ear": ear,
                "mar": mar,
                "pitch": pitch,
                "yaw": yaw,
                "roll": roll,
                "pts": feats.get("pts"),
            }

        # 4. Tính toán vector 7 chiều từ 3 frames gần nhất
        vector = calculate_sequence_features(list(self.feature_buffer))
        if not vector:
            return {
                "status": "Error",
                "desc": "Lỗi tính toán vector đặc trưng",
                "is_valid": False,
            }

        # 5. Dự đoán xác suất bằng Random Forest
        raw_pred = self.model.predict([vector])[0]
        if hasattr(self.model, "predict_proba"):
            probs_arr = self.model.predict_proba([vector])[0]
            prob_dict = {cls_name: float(p) for cls_name, p in zip(self.classes_, probs_arr)}
        else:
            prob_dict = {raw_pred: 1.0}

        # 6. Làm mịn theo thời gian (Temporal Smoothing qua k frame gần nhất)
        self.history_probs.append(prob_dict)

        avg_prob = {}
        for cls_name in self.classes_:
            vals = [p.get(cls_name, 0.0) for p in self.history_probs]
            avg_prob[cls_name] = sum(vals) / len(vals)

        # Chọn nhãn có xác suất trung bình cao nhất
        smoothed_label = max(avg_prob, key=avg_prob.get)
        confidence = avg_prob[smoothed_label]
        self.last_valid_status = smoothed_label

        return {
            "status": smoothed_label,
            "raw_status": raw_pred,
            "confidence": float(confidence),
            "probabilities": avg_prob,
            "ear": ear,
            "mar": mar,
            "pitch": pitch,
            "yaw": yaw,
            "roll": roll,
            "pts": feats.get("pts"),
            "is_valid": True,
        }

    def predict_status(self, frames):
        """
        Nhận vào 3 tấm ảnh (frames) từ camera hoặc lúc chấm công snapshot.
        Giữ nguyên tương thích ngược với API cũ.
        Trả về: "Normal", "Fatigue", "Exhausted" (hoặc chuỗi lỗi).
        """
        if len(frames) != 3:
            return "Error: Cần truyền vào đúng 3 tấm ảnh."

        features_list = []
        for frame in frames:
            feats = self.extractor.extract_features(frame)
            if feats is None:
                return "Unknown (Không thấy mặt)"
            features_list.append(feats)

        # Tính toán vector gồm 7 đặc trưng
        vector = calculate_sequence_features(features_list)
        if not vector:
            return "Unknown (Lỗi tính toán)"

        # Dùng predict_proba thay vì predict đơn thuần — chọn nhãn có xác suất cao nhất
        if hasattr(self.model, "predict_proba"):
            probs_arr = self.model.predict_proba([vector])[0]
            label_idx = probs_arr.argmax()
            return self.classes_[label_idx]
        else:
            return self.model.predict([vector])[0]


def to_serializable(result: dict) -> dict:
    """
    Chuyển tất cả numpy types sang Python native types để JSON-safe.
    Dung khi gửi kết quả lên MQTT / REST API.
    Bỏ 'pts' (mảng lớn, không cần serialize).
    """
    safe = {}
    for k, v in result.items():
        if k == "pts":
            continue  # Bỏ landmarks array
        elif isinstance(v, dict):
            safe[k] = {kk: float(vv) if hasattr(vv, "item") else vv for kk, vv in v.items()}
        elif hasattr(v, "item"):  # np.float32, np.float64, np.int64, …
            safe[k] = v.item()
        else:
            safe[k] = v
    return safe


# Test thử nhanh nếu chạy file trực tiếp
if __name__ == "__main__":
    import cv2
    import time

    try:
        predictor = StatusPredictor(smoothing_window=5, max_yaw_deg=25.0)

        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        print("🚀 Bật webcam để test realtime (Đã nâng cấp Streaming + Làm mịn nhãn)...")
        print("Nhấn 'Q' để thoát.")

        # Bảng màu và thông tin hiển thị
        STATUS_CONFIG = {
            "Normal": {"desc": "NORMAL - Tinh tao / Binh thuong", "color": (0, 230, 0)},
            "Fatigue": {"desc": "FATIGUE - Met moi / Lo do", "color": (0, 215, 255)},
            "Exhausted": {"desc": "EXHAUSTED - Kiet suc / Sup mi", "color": (0, 0, 255)},
            "Turned_Head": {"desc": "CHU Y - Vui long nhin thang", "color": (0, 165, 255)},
            "Buffering": {"desc": "Dang phan tich...", "color": (200, 200, 200)},
            "No_Face": {"desc": "Khong thay khuon mat", "color": (150, 150, 150)},
        }

        prev_time = time.time()
        fps = 0.0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            curr_time = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / max(curr_time - prev_time, 1e-5))
            prev_time = curr_time

            display_frame = frame.copy()

            # Sử dụng cơ chế Streaming mới (chỉ 1 lần trích xuất mỗi frame!)
            result = predictor.predict_frame(frame)
            status = result.get("status", "Unknown")

            # Vẽ landmark nếu có
            if result.get("pts") is not None:
                for x, y in result["pts"][::4]:  # Vẽ thưa để tối ưu FPS
                    cv2.circle(display_frame, (int(x), int(y)), 1, (0, 255, 100), -1)

            cfg = STATUS_CONFIG.get(status, {"desc": f"Trang thai: {status}", "color": (200, 200, 200)})

            # 1. Header Box hiển thị trạng thái
            cv2.rectangle(display_frame, (15, 15), (550, 125), (20, 20, 20), -1)
            cv2.rectangle(display_frame, (15, 15), (550, 125), cfg["color"], 2)

            conf_str = f" ({result['confidence']*100:.1f}%)" if result.get("is_valid") else ""
            cv2.putText(
                display_frame,
                f"{cfg['desc']}{conf_str}",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                cfg["color"],
                2,
            )

            # 2. Chi tiết chỉ số đo lường
            ear_val = result.get("ear", 0.0)
            mar_val = result.get("mar", 0.0)
            pitch_val = result.get("pitch", 0.0)
            yaw_val = result.get("yaw", 0.0)

            stats_str = f"EAR: {ear_val:.3f} | MAR: {mar_val:.3f} | Pitch: {pitch_val:.1f} | Yaw: {yaw_val:.1f}"
            cv2.putText(
                display_frame,
                stats_str,
                (30, 85),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (220, 220, 220),
                1,
            )

            # 3. FPS & Hướng dẫn
            cv2.putText(
                display_frame,
                f"FPS: {fps:.1f} | Nhan 'Q' de thoat",
                (30, 112),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (180, 180, 180),
                1,
            )

            cv2.imshow("AI 2 - Trạng Thái Thể Trạng (Streaming + Smooth)", display_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()

    except Exception as e:
        print(f"Lỗi: {e}")
