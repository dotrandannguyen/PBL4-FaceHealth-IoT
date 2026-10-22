# ESP32-CAM Firmware — PBL4 FaceHealth IoT

Thư mục chứa toàn bộ mã nguồn firmware PlatformIO cho 02 bo mạch **ESP32-CAM AI-Thinker (OV2640)** trong dự án điểm danh khuôn mặt và giám sát sức khỏe sinh viên.

---

## 📂 Cấu trúc thư mục

```
ESP32-CAM/
├── include/
│   ├── config.h          # File cấu hình trung tâm (WiFi, Server IP, Pinout, chu kỳ)
│   └── camera_pins.h     # Sơ đồ chân camera OV2640 chuẩn AI-Thinker
├── src/
│   ├── camera_helper.h   # Tiện ích quản lý camera & PSRAM
│   ├── http_helper.h     # Module gửi HTTP POST Multipart (ảnh + metadata JSON)
│   └── main.cpp          # Mã nguồn chính hỗ trợ cả 2 mạch qua cờ biên dịch
├── platformio.ini        # Cấu hình 2 môi trường: esp32cam_attendance & esp32cam_health
├── WALKTHROUGH.md        # Hướng dẫn chi tiết nối dây, nạp code và kiểm thử thực tế
└── README.md
```

---

## ⚡ Bắt đầu nhanh (Quick Start)

1. **Xem sơ đồ nối dây & quy trình nạp**: Đọc file [WALKTHROUGH.md](WALKTHROUGH.md).
2. **Cấu hình WiFi & Server**: Mở [include/config.h](include/config.h) và cập nhật `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_HOST`.
3. **Biên dịch & Nạp code**:
   ```powershell
   # Nạp cho Mạch 1 (Điểm danh)
   pio run -e esp32cam_attendance -t upload

   # Nạp cho Mạch 2 (Sức khỏe: MAX30102 + LCD1602 + LED)
   pio run -e esp32cam_health -t upload
   ```
