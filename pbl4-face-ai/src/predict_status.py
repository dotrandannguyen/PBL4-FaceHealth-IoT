import joblib
import warnings
from pathlib import Path
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
    def __init__(self):
        # Khởi tạo bộ trích xuất đặc trưng (MediaPipe)
        self.extractor = StatusFeatureExtractor()
        
        # Load mô hình Random Forest đã train
        model_path = Path(__file__).parent.parent / "data" / "rf_status_model.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"Chưa có model! Vui lòng chạy train_rf.py trước. Path: {model_path}")
        
        self.model = joblib.load(model_path)
        
    def predict_status(self, frames):
        """
        Nhận vào 3 tấm ảnh (frames) từ camera hoặc AI 1
        frames: list of 3 numpy arrays (ảnh cv2)
        Trả về: "Normal", "Fatigue", "Exhausted" (hoặc chuỗi lỗi)
        """
        if len(frames) != 3:
            return "Error: Cần truyền vào đúng 3 tấm ảnh."
            
        features_list = []
        for frame in frames:
            feats = self.extractor.extract_features(frame)
            if feats is None:
                return "Unknown (Không thấy mặt)"
            features_list.append(feats)
            
        # Tính toán vector gồm 7 đặc trưng giống hệt lúc thu thập dữ liệu
        vector = calculate_sequence_features(features_list)
        if not vector:
            return "Unknown (Lỗi tính toán)"
            
        # Đưa qua model Random Forest để đọc và dự đoán
        prediction = self.model.predict([vector])[0]
        return prediction

# Test thử nhanh nếu chạy file trực tiếp
if __name__ == "__main__":
    import cv2
    from collections import deque
    
    try:
        predictor = StatusPredictor()
        
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        print("Bật webcam để test realtime... (Bấm Q để thoát)")
        
        frame_buffer = deque(maxlen=3)
        current_status = "Unknown"
        
        # Bảng màu và chú thích cho từng nhãn
        STATUS_INFO = {
            "Normal": {"desc": "Normal: Tinh tao / Binh thuong", "color": (0, 255, 0)},
            "Fatigue": {"desc": "Fatigue: Met moi / Lo do", "color": (0, 255, 255)},
            "Exhausted": {"desc": "Exhausted: Kiet suc / Sup mi", "color": (0, 0, 255)},
        }
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            display_frame = frame.copy()
            frame_buffer.append(frame)
            
            # Chỉ dự đoán khi đủ 3 frame
            if len(frame_buffer) == 3:
                status = predictor.predict_status(list(frame_buffer))
                if not status.startswith("Error") and "Unknown" not in status:
                    current_status = status
            
            # Hiển thị trạng thái lên màn hình
            info = STATUS_INFO.get(current_status, {"desc": f"Trang thai: {current_status}", "color": (200, 200, 200)})
            cv2.putText(display_frame, info["desc"], (20, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, info["color"], 2)
            cv2.putText(display_frame, "Nhan 'Q' de thoat", (20, 90), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 0), 2)
            
            cv2.imshow("Test Trang Thai - AI 2 (Realtime)", display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        cap.release()
        cv2.destroyAllWindows()
            
    except Exception as e:
        print(f"Lỗi: {e}")
