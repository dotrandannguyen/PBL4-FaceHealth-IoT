# ESP32-CAM Firmware — PBL4 FaceHealth IoT

Thư mục chứa toàn bộ mã nguồn firmware PlatformIO cho bo mạch **ESP32-CAM AI-Thinker (OV2640)** trong dự án điểm danh khuôn mặt và giám sát sức khỏe sinh viên.

---

## 📂 Cấu trúc thư mục chuẩn chỉnh

```
ESP32-CAM/
├── include/
│   ├── config.h             # Cấu hình WiFi, mDNS, Server IP, Cổng Stream 81
│   └── camera_pins.h        # Sơ đồ chân camera OV2640 chuẩn AI-Thinker
├── src/
│   ├── main.cpp             # Mã nguồn chính (Khởi tạo Cam, mDNS esp32cam.local, AP Portal)
│   └── stream_server.h      # Server phát luồng MJPEG Stream On-Demand (Cổng 81)
├── server/
│   ├── app.py               # Flask Server phụ trợ quản lý kết nối (Cổng 5000)
│   └── received_images/     # Thư mục lưu ảnh khi cần (đã dọn dẹp)
├── arduino_legacy/          # [Backup 1 bản] Toàn bộ code Arduino IDE cũ
├── platformio.ini           # Cấu hình nạp firmware qua PlatformIO (môi trường esp32cam_node1)
├── WALKTHROUGH.md           # Hướng dẫn chi tiết nối dây, nạp code và kiểm thử thực tế
└── README.md
```

---

## ⚡ Bắt đầu nhanh (Quick Start)

1. **Xem sơ đồ nối dây & quy trình nạp**: Đọc file [WALKTHROUGH.md](WALKTHROUGH.md).
2. **Cấu hình WiFi**: Mở [include/config.h](include/config.h) và cập nhật `DEFAULT_WIFI_SSID`, `DEFAULT_WIFI_PASS`.
3. **Biên dịch & Nạp code qua PlatformIO**:
   ```powershell
   pio run -e esp32cam_node1 -t upload
   ```
4. **Kiểm tra luồng Stream trực tiếp (On-Demand)**:
   - Truy cập trình duyệt: `http://esp32cam.local:81/stream`
   - Hoặc chạy từ Dashboard Python: Click **"Xem Trực Tiếp Stream"**.
