import cv2
import sys
import os
import time
import pandas as pd
from collections import deque
from pathlib import Path

# Thêm src vào sys.path để import status_features
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from status_features import StatusFeatureExtractor

# Thư mục lưu dữ liệu
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = DATA_DIR / "status_dataset.csv"

# Label mapping
LABELS = {
    '1': 'Normal',
    '2': 'Drowsy',
    '3': 'Yawn',
    '4': 'Head-down'
}

def calculate_sequence_features(features_list):
    """
    Tính vector đặc trưng tổng hợp từ chuỗi 3 frames.
    features_list: list of dicts (len=3), mỗi dict chứa ear, mar, pitch, yaw, roll
    """
    if len(features_list) != 3:
        return None
    
    ears = [f['ear'] for f in features_list]
    mars = [f['mar'] for f in features_list]
    pitches = [f['pitch'] for f in features_list]
    rolls = [f['roll'] for f in features_list]

    # Tính toán như công thức
    min_ear = min(ears)
    mean_ear = sum(ears) / 3.0
    max_mar = max(mars)
    mean_mar = sum(mars) / 3.0
    
    # delta = max - min
    delta_pitch = max(pitches) - min(pitches)
    delta_roll = max(rolls) - min(rolls)
    
    # mean_pitch để nhận diện cúi đầu rõ hơn
    mean_pitch = sum(pitches) / 3.0

    return [min_ear, mean_ear, max_mar, mean_mar, delta_pitch, delta_roll, mean_pitch]

def main():
    print("🚀 Khởi tạo MediaPipe Extractor...")
    extractor = StatusFeatureExtractor()
    
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    dataset = []
    
    print("\n" + "="*50)
    print("📸 CÔNG CỤ THU THẬP DỮ LIỆU TRẠNG THÁI (3-FRAMES)")
    print("="*50)
    print("Hướng dẫn:")
    print("1. Bấm '1' -> Thu thập trạng thái Normal")
    print("2. Bấm '2' -> Thu thập trạng thái Drowsy (Nhắm mắt/Lờ đờ)")
    print("3. Bấm '3' -> Thu thập trạng thái Yawn (Ngáp)")
    print("4. Bấm '4' -> Thu thập trạng thái Head-down (Cúi đầu)")
    print("5. Bấm 'Q' -> Lưu file CSV và Thoát")
    print("="*50)

    frame_buffer = deque(maxlen=3)
    current_label = None
    collecting = False
    frames_collected = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        display_frame = frame.copy()
        
        # Trích xuất đặc trưng từng frame
        feats = extractor.extract_features(frame)
        
        if feats is not None:
            frame_buffer.append(feats)
            
            # Vẽ landmark lên màn hình cho trực quan
            for x, y in feats['pts']:
                cv2.circle(display_frame, (int(x), int(y)), 1, (0, 255, 0), -1)
                
            # Hiện thông số
            cv2.putText(display_frame, f"EAR: {feats['ear']:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,0,0), 2)
            cv2.putText(display_frame, f"MAR: {feats['mar']:.2f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,0,0), 2)
            cv2.putText(display_frame, f"Pitch: {feats['pitch']:.1f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,0,0), 2)
        else:
            cv2.putText(display_frame, "No face detected!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)

        # Logic thu thập
        if collecting and feats is not None:
            # Mô phỏng việc thu 3 frames cách nhau ~0.5s (ở đây ta lấy luôn 3 frames liên tiếp cho nhanh, 
            # hoặc đợi đủ buffer)
            if len(frame_buffer) == 3:
                vector = calculate_sequence_features(list(frame_buffer))
                if vector:
                    vector.append(current_label) # Thêm label ở cột cuối
                    dataset.append(vector)
                    print(f"✅ Đã lưu 1 chuỗi cho trạng thái: {current_label}")
                
                # Reset buffer
                frame_buffer.clear()
                collecting = False
                
        # Hướng dẫn màn hình
        if collecting:
            cv2.putText(display_frame, f"Recording {current_label}...", (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 3)
        else:
            cv2.putText(display_frame, "Press 1, 2, 3, 4 to record. Q to quit", (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)
            
        cv2.putText(display_frame, f"Data count: {len(dataset)}", (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)

        cv2.imshow("Data Collection", display_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif chr(key) in LABELS.keys():
            current_label = LABELS[chr(key)]
            collecting = True
            frame_buffer.clear() # Xóa buffer cũ, bắt đầu lấy 3 frame mới

    cap.release()
    cv2.destroyAllWindows()
    
    # Lưu ra CSV
    if dataset:
        columns = ['min_ear', 'mean_ear', 'max_mar', 'mean_mar', 'delta_pitch', 'delta_roll', 'mean_pitch', 'label']
        df = pd.DataFrame(dataset, columns=columns)
        
        # Ghi đè hoặc append
        if CSV_FILE.exists():
            df.to_csv(CSV_FILE, mode='a', header=False, index=False)
            print(f"\n💾 Đã append thêm {len(dataset)} dòng vào {CSV_FILE}")
        else:
            df.to_csv(CSV_FILE, index=False)
            print(f"\n💾 Đã lưu dataset mới với {len(dataset)} dòng vào {CSV_FILE}")
    else:
        print("\n❌ Chưa có dữ liệu nào được thu thập.")

if __name__ == "__main__":
    main()
