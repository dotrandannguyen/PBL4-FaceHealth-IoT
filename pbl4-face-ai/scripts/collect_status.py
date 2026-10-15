import cv2
import sys
import os
import time
import pandas as pd
from collections import deque
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thêm src vào sys.path để import status_features
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.status_features import StatusFeatureExtractor

# Thư mục lưu dữ liệu
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = DATA_DIR / "status_dataset.csv"

# Label mapping: 3 cấp độ mệt mỏi
LABELS = {
    '1': 'Normal',
    '2': 'Fatigue',
    '3': 'Exhausted'
}

LABEL_NAMES = {
    'Normal': 'Binh thuong / Tinh tao (EAR >= 0.25)',
    'Fatigue': 'Met moi / Lo do (0.18 <= EAR < 0.25)',
    'Exhausted': 'Kiet suc / Sup mi (EAR < 0.18)'
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

    # Tính toán các chỉ số thống kê
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
    
    print("\n" + "="*60)
    print("📸 CÔNG CỤ THU THẬP DỮ LIỆU 3 CẤP ĐỘ MỆT MỎI (AI 2)")
    print("="*60)
    print("Hướng dẫn thu thập:")
    print("  [1] Normal     : Tỉnh táo / Bình thường (Mắt to, EAR >= 0.25)")
    print("  [2] Fatigue    : Mệt mỏi / Lờ đờ (Lim dim, 0.18 <= EAR < 0.25)")
    print("  [3] Exhausted  : Kiệt sức / Sụp mí (Sụp mắt sâu, EAR < 0.18)")
    print("  [Q] Lưu dataset vào CSV và Thoát")
    print("="*60)

    frame_buffer = deque(maxlen=3)
    current_label = None
    collecting = False
    # Đếm số mẫu theo từng nhãn để theo dõi
    label_counts = {'Normal': 0, 'Fatigue': 0, 'Exhausted': 0}

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        display_frame = frame.copy()
        
        # Trích xuất đặc trưng từng frame
        feats = extractor.extract_features(frame)
        
        if feats is not None:
            frame_buffer.append(feats)
            
            # Vẽ landmark lên màn hình
            for x, y in feats['pts']:
                cv2.circle(display_frame, (int(x), int(y)), 1, (0, 200, 0), -1)
                
            # Chỉ hiển thị số liệu thô — KHÔNG phán xét nhãn theo ngưỡng cứng
            cv2.putText(display_frame, f"EAR : {feats['ear']:.3f}", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2)
            cv2.putText(display_frame, f"MAR : {feats['mar']:.3f}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2)
            cv2.putText(display_frame, f"Pitch: {feats['pitch']:.1f}", (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2)
            cv2.putText(display_frame, f"Roll : {feats['roll']:.1f}", (10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2)
        else:
            cv2.putText(display_frame, "!! Khong thay khuon mat !!", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # Logic thu thập — nhãn hoàn toàn do phím người dùng bấm quyết định
        if collecting and feats is not None:
            if len(frame_buffer) == 3:
                vector = calculate_sequence_features(list(frame_buffer))
                if vector:
                    vector.append(current_label)
                    dataset.append(vector)
                    label_counts[current_label] += 1
                    print(f"[{current_label}] #{label_counts[current_label]:03d} | EAR={vector[1]:.3f}  MAR={vector[2]:.3f}  Pitch={vector[6]:.1f}")
                
                frame_buffer.clear()
                collecting = False
                
        # Vùng hiển thị trạng thái thu thập & phím bấm
        h = display_frame.shape[0]
        
        if collecting:
            # Highlight đỏ khi đang ghi
            cv2.rectangle(display_frame, (0, h-120), (display_frame.shape[1], h), (0, 0, 60), -1)
            cv2.putText(display_frame, f">> DANG GHI NHAN: [{current_label}] ...", (10, h-80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 60, 255), 2)
        else:
            # Hướng dẫn phím — nhãn do BẠN tự chọn, không phụ thuộc EAR
            cv2.rectangle(display_frame, (0, h-120), (display_frame.shape[1], h), (20, 20, 20), -1)
            cv2.putText(display_frame, "[1] Normal  [2] Fatigue  [3] Exhausted  [Q] Luu & Thoat",
                        (10, h-80), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        
        # Bộ đếm mẫu từng nhãn
        counter_text = f"Normal:{label_counts['Normal']}  Fatigue:{label_counts['Fatigue']}  Exhausted:{label_counts['Exhausted']}  | Tong:{len(dataset)}"
        cv2.putText(display_frame, counter_text, (10, h-45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 255, 100), 2)
        
        # Mục tiêu thu thập
        cv2.putText(display_frame, "Muc tieu: moi nhan >= 50 mau",
                    (10, h-15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1)

        cv2.imshow("AI 2 — Thu Thap Du Lieu Trang Thai", display_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key in [ord(k) for k in LABELS.keys()]:
            current_label = LABELS[chr(key)]
            collecting = True
            frame_buffer.clear()

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
