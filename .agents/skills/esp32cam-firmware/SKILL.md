---
name: esp32cam-firmware
description: >-
  Workflows, pinout rules, and commands for developing, compiling, flashing, and debugging
  ESP32-CAM (AI-Thinker OV2640) firmware for PBL4 FaceHealth IoT. Covers dual-node architecture,
  PlatformIO environments, MAX30102, I2C LCD1602, and FastAPI integration.
---

# ESP32-CAM Firmware & Hardware Skill Guide

Kỹ năng này chuyên sâu về phần cứng vi điều khiển **ESP32-CAM (AI-Thinker)**, thiết lập PlatformIO, tích hợp cảm biến nhịp tim/SpO2 MAX30102, màn hình LCD 1602 qua I2C Backpack, và giao tiếp HTTP POST multipart với máy chủ AI.

---

## 1. Kiến trúc hệ thống 2 Mạch ESP32-CAM

```
[MẠCH 1: ESP32-CAM Điểm danh]
    OV2640 Camera
    Flash LED (GPIO 4)
    Onboard LED (GPIO 33)
           │ HTTP POST (image/jpeg)
           ▼
    API Server (/api/attendance) ──> AI 1: InsightFace (buffalo_sc) ──> User ID & Name

[MẠCH 2: ESP32-CAM Sức khỏe & Trạng thái]
    OV2640 Camera
    MAX30102 (I2C: GPIO 13/15)
    LCD 1602 I2C (I2C: GPIO 13/15)
    Warning LED (GPIO 12)
           │ HTTP POST (image + HR + SpO2)
           ▼
    API Server (/api/health)     ──> AI 2: MediaPipe + Random Forest ──> Status & Alert
```

---

## 2. Sơ đồ chân & Nguyên tắc an toàn phần cứng

> [!IMPORTANT]
> ESP32-CAM AI-Thinker chỉ có một số ít chân GPIO khả dụng do hầu hết đã dùng cho Camera OV2640 và PSRAM. **Không gắn thẻ nhớ MicroSD** để giải phóng các chân GPIO 12, 13, 14, 15.

| Linh kiện | Chân linh kiện | Chân ESP32-CAM | Lưu ý kỹ thuật |
| :--- | :--- | :--- | :--- |
| **Bus I2C chung** | **SDA** | `GPIO 13` | Cắm chung cho cả MAX30102 và LCD 1602 I2C. |
| **Bus I2C chung** | **SCL** | `GPIO 15` | Cần đảm bảo mức logic ổn định khi boot. |
| **LED Cảnh báo** | Anode (+) | `GPIO 12` | Nối tiếp trở hạn dòng 220Ω - 330Ω xuống GND. Tránh kéo lên 3.3V khi boot. |
| **MAX30102** | VCC / VIN | `3.3V` | Cấp nguồn 3.3V từ chân 3V3 của ESP32-CAM hoặc nguồn ổn áp riêng. |
| **MAX30102** | GND | `GND` | Nối chung mass (GND) với ESP32-CAM. |
| **LCD 1602 I2C** | VCC | `5V` | LCD1602 cần nguồn 5V để có độ tương phản hiển thị sắc nét nhất. |
| **LCD 1602 I2C** | GND | `GND` | Nối chung mass. |
| **Nguồn ESP32-CAM** | 5V & GND | `5V` & `GND` | Cần nguồn **5V / 2A** độc lập hoặc tụ hóa 470µF-1000µF giữa 5V và GND để chống sụt áp (Brownout). |

---

## 3. PlatformIO Commands (CLI)

Dự án nằm tại thư mục `ESP32-CAM/`. Các lệnh điều khiển qua terminal:

### 3.1. Biên dịch (Build)
```powershell
# Chuyển vào thư mục firmware
cd D:\PBL4\PBL4-FaceHealth-IoT\ESP32-CAM

# Build cả 2 node
pio run

# Chỉ build Mạch 1 (Điểm danh)
pio run -e esp32cam_attendance

# Chỉ build Mạch 2 (Sức khỏe & Trạng thái)
pio run -e esp32cam_health
```

### 3.2. Nạp chương trình (Upload)
```powershell
# Nạp code cho Mạch 1 (khi cắm cổng COM của Mạch 1)
pio run -e esp32cam_attendance -t upload

# Nạp code cho Mạch 2 (khi cắm cổng COM của Mạch 2)
pio run -e esp32cam_health -t upload

# Chỉ định cổng COM cụ thể (ví dụ COM4)
pio run -e esp32cam_health -t upload --upload-port COM4
```

### 3.3. Xem Serial Monitor
```powershell
pio device monitor -b 115200
```

---

## 4. Quy trình nạp code bằng Mạch FTDI / USB-to-UART

Vì ESP32-CAM không tích hợp sẵn chip nạp USB, phải dùng mạch chuyển USB UART (FTDI FT232RL, CH340, CP2102):
1. **Nối dây nạp**:
   - `FTDI TX` → `ESP32-CAM U0R (GPIO 3)`
   - `FTDI RX` → `ESP32-CAM U0T (GPIO 1)`
   - `FTDI VCC (5V)` → `ESP32-CAM 5V`
   - `FTDI GND` → `ESP32-CAM GND`
   - **BƯỚC QUAN TRỌNG**: Nối chân `GPIO 0` xuống `GND` bằng 1 dây jumper.
2. **Kích hoạt Bootloader**: Bấm nút **RST / RESET** trên bo ESP32-CAM (hoặc rút nguồn cắm lại).
3. **Chạy lệnh nạp**: Chạy lệnh `pio run -e ... -t upload`.
4. **Vận hành**: Sau khi nạp thành công (100%), **rút dây jumper giữa GPIO 0 và GND**, sau đó nhấn nút **RST** để ESP32-CAM khởi động chương trình bình thường.

---

## 5. Khắc phục lỗi thường gặp (Troubleshooting Runbook)

### 🔴 Lỗi 1: `Brownout detector was triggered`
- **Nguyên nhân**: Nguồn 5V bị sụt áp đột ngột khi bật WiFi hoặc kích hoạt Camera OV2640 (dòng đỉnh ~300-500mA). Cáp USB quá dài hoặc cổng USB máy tính không đủ công suất.
- **Xử lý**:
  1. Dùng củ sạc 5V/2A cấp trực tiếp vào chân 5V và GND của ESP32-CAM.
  2. Hàn/gắn thêm một tụ điện hóa `470µF` hoặc `1000µF` (10V-16V) song song giữa chân `5V` và `GND`.

### 🔴 Lỗi 2: `Camera probe failed with error 0x20002`
- **Nguyên nhân**: Cáp dẹt FPC của mắt camera OV2640 bị lỏng chân tiếp xúc hoặc cắm ngược chiều.
- **Xử lý**:
  1. Mở chốt gài cáp camera màu đen, nhấc cáp ra.
  2. Vệ sinh nhẹ các chân tiếp xúc màu vàng.
  3. Cắm thẳng và gài chặt lại chốt nẹp.

### 🔴 Lỗi 3: `MAX30102 not found` hoặc `LCD I2C không sáng chữ`
- **Nguyên nhân**: Sai chân I2C SDA/SCL, lỏng dây, hoặc sai địa chỉ I2C.
- **Xử lý**:
  1. Kiểm tra lại nối dây: SDA nối `GPIO 13`, SCL nối `GPIO 15`.
  2. Với LCD 1602: Xoay biến trở vi chỉnh (núm vặn màu xanh) ở mặt sau bo I2C PCF8574 để tăng độ tương phản hiển thị chữ.
  3. Kiểm tra địa chỉ I2C: Hầu hết màn LCD I2C dùng `0x27`, một số dòng dùng `0x3F`. Điều chỉnh lại trong [config.h](file:///D:/PBL4/PBL4-FaceHealth-IoT/ESP32-CAM/include/config.h) nếu cần.
