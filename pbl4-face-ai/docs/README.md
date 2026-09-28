# PBL4 — AI Điểm Danh Sinh Viên

Hệ thống nhận diện khuôn mặt sử dụng **InsightFace + ArcFace**, chạy trên PC trước khi tích hợp ESP32-CAM.

## 🏗 Kiến trúc

```
ESP32-CAM → AI SERVER → AI 1 (InsightFace) → User ID
                     → AI 2 (MediaPipe+RF) → Trạng thái
```

## 📁 Cấu trúc

```
pbl4-face-ai/
├── data/
│   ├── registered/<student_id>/   # Ảnh đăng ký
│   ├── test/<student_id>/         # Ảnh đánh giá
│   ├── embeddings.pkl             # Vector đã lưu
│   └── eval_results/              # Biểu đồ FAR/FRR
├── src/
│   ├── face_engine.py             # Core: detect + embed
│   ├── register.py                # Đăng ký sinh viên
│   ├── verify.py                  # Xác minh 1:1 / 1:N
│   └── evaluate.py                # Đánh giá ngưỡng
├── scripts/
│   └── capture_webcam.py          # Thu ảnh webcam
├── main.py                        # Entry point
└── requirements.txt
```

## 🚀 Cài đặt

```powershell
# Kích hoạt môi trường (PowerShell)
.venv\Scripts\Activate.ps1

# Cài thư viện
pip install -r requirements.txt
```

## 📋 Sử dụng

### Bước 1 — Test model
```powershell
python src/face_engine.py --image test.jpg --show
```

### Bước 2 — Đăng ký sinh viên
```powershell
# Thu ảnh từ webcam (10 ảnh)
python main.py capture --id SV001 --name "Nguyen Van A"

# Đăng ký từ folder ảnh
python main.py register folder --id SV001 --name "Nguyen Van A" --images data/registered/SV001/

# Đăng ký trực tiếp qua webcam
python main.py register webcam --id SV001 --name "Nguyen Van A"

# Xem danh sách đã đăng ký
python main.py register list
```

### Bước 3 — Xác minh
```powershell
# 1:1 — kiểm tra ảnh có phải SV001 không
python main.py verify --id SV001 --image photo.jpg

# 1:N — tìm xem đây là ai
python main.py identify --image photo.jpg

# Real-time qua webcam
python main.py identify --webcam
```

### Bước 4 — Đánh giá ngưỡng
```powershell
# Chuẩn bị ảnh test: data/test/<student_id>/<img.jpg>
python main.py evaluate
```

## 🔧 Cấu hình

| Tham số | Mặc định | Ghi chú |
|---------|----------|---------|
| Model | `buffalo_l` | 326MB, tự tải về |
| Ngưỡng | `0.45` | Chỉnh sau Bước 4 |
| ctx_id | `-1` (CPU) | Đổi `0` nếu có GPU CUDA |
| det_size | `640×640` | Kích thước detect |

## ⚠️ Lưu ý

- Model `buffalo_l` (~326MB) tự tải về `~/.insightface/models/buffalo_l/` lần đầu
- Chỉ dùng cho **mục đích nghiên cứu phi thương mại**
- Ngưỡng cosine similarity tối ưu: xem kết quả `evaluate`


///for RUN
.\.venv\Scripts\python.exe gui.py
