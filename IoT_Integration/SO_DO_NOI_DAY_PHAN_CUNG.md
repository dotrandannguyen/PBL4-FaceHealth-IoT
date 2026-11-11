# Hướng Dẫn Sơ Đồ Nối Dây Phần Cứng (ESP8266 + ESP32-CAM + MAX30102 + LCD 1602)

Tài liệu này hướng dẫn chi tiết cách đấu nối 2 bo mạch **ESP8266** và **ESP32-CAM** cùng cảm biến **MAX30102** và màn hình **LCD 1602 I2C** vào chung một trạm chấm công.

---

## 1. Nguyên Tắc Cấp Nguồn (Cực Kỳ Quan Trọng ⚠️)

- **ESP32-CAM** khi truyền video qua WiFi và nạp camera tiêu thụ dòng điện đỉnh từ **350mA - 500mA**.
- **ESP8266** khi phát WiFi tiêu thụ khoảng **150mA - 200mA**.
- **LCD 1602 (có đèn nền)** tiêu thụ khoảng **50mA**.
- **Khuyến nghị nguồn**: Dùng chung một Adapter nguồn ngoài **5V - 2A hoặc 5V - 3A** (hoặc củ sạc điện thoại 5V 2A tốt).
- **Quy tắc vàng**: **NỐI CHUNG TẤT CẢ CÁC CHÂN GND** (Mass) của nguồn 5V, ESP8266, ESP32-CAM, LCD và MAX30102 với nhau để đảm bảo mức điện áp tham chiếu đồng nhất.

---

## 2. Bảng Cấu Hình Chân Nối (Pinout Mapping)

### A. Bo mạch ESP8266 (Xử lý Cảm biến & Màn hình LCD)

| Thiết bị ngoại vi | Chân trên linh kiện | Chân nối trên ESP8266 | Ghi chú kỹ thuật |
| :--- | :--- | :--- | :--- |
| **Cảm biến MAX30102** | **VCC** | **3V3** (3.3V) | *Nên dùng 3.3V để bảo vệ diode quang* |
| | **GND** | **GND** | Nối Mass chung |
| | **SDA** | **D2** (GPIO 4) | Đường truyền dữ liệu I2C |
| | **SCL** | **D1** (GPIO 5) | Đường xung nhịp I2C (100kHz) |
| | **INT** | *Không nối* | Có thể bỏ trống (chạy chế độ FIFO Polling) |
| **Màn hình LCD 1602 (I2C)** | **VCC** | **VIN (5V)** | *Bắt buộc cấp 5V để chữ và đèn nền sáng rõ* |
| | **GND** | **GND** | Nối Mass chung |
| | **SDA** | **D2** (GPIO 4) | Mắc song song với SDA của MAX30102 |
| | **SCL** | **D1** (GPIO 5) | Mắc song song với SCL của MAX30102 |
| **(Tùy chọn) Đồng bộ cứng** | **Trigger Out** | **D5** (GPIO 14) | Nối sang GPIO 13 của ESP32-CAM (nếu dùng dây) |

> 💡 **Mẹo I2C**: Cả MAX30102 (địa chỉ I2C `0x57`) và LCD 1602 (địa chỉ I2C `0x27` hoặc `0x3F`) đều dùng chung 2 chân **D1 (SCL)** và **D2 (SDA)** của ESP8266 mà không hề xung đột, vì chúng khác địa chỉ I2C.

---

### B. Bo mạch ESP32-CAM (AI-Thinker OV2640)

| Chân trên ESP32-CAM | Kết nối đến | Ghi chú |
| :--- | :--- | :--- |
| **5V** | Nguồn **5V ngoài** | *Không lấy 5V từ chân 3.3V của ESP8266 vì sẽ bị sụt áp (Brownout)* |
| **GND** | **GND chung** | Nối chung với GND của hệ thống |
| **GPIO 33** | LED báo hiệu đỏ sau lưng | Tự động báo trạng thái stream |
| **GPIO 4** | Đèn Flash công suất cao | Có thể cấu hình bật/tắt khi chụp đêm |
| **(Tùy chọn) GPIO 13** | Nối chân **D5** của ESP8266 | Nhận tín hiệu kích hoạt chụp cứng (nếu không dùng WiFi) |

---

## 3. Sơ Đồ Nguyên Lý Khối (Block Diagram)

```
                       ┌────────────────────────┐
                       │  NGUỒN 5V - 2A / 3A    │
                       └───┬────────────────┬───┘
                           │ +5V            │ GND (Chung)
             ┌─────────────┴────────┐       │
             │                      │       │
             ▼                      ▼       ▼
    ┌────────────────┐     ┌───────────────────────────────────┐
    │   ESP32-CAM    │     │             ESP8266               │
    │  (Chụp ảnh)    │     │     (Đo sức khỏe & Hiển thị)      │
    │                │     │                                   │
    │ 5V   <─── +5V  │     │ VIN  <─── +5V                     │
    │ GND  <─── GND  │     │ GND  <─── GND                     │
    │                │     │ 3V3  ─────────┐                   │
    └────────────────┘     │ D1 (SCL) ───┐ │                   │
                           │ D2 (SDA) ─┐ │ │                   │
                           └───────────┼─┼─┼───────────────────┘
                                       │ │ │
                      ┌────────────────┘ │ │
                      │   ┌──────────────┘ │
                      ▼   ▼                ▼
             ┌────────────────┐   ┌────────────────┐
             │  LCD 1602 I2C  │   │ CẢM BIẾN NHỊP  │
             │ (Địa chỉ 0x27) │   │ MAX30102(0x57) │
             │                │   │                │
             │ VCC <── +5V    │   │ VCC <── 3V3    │
             │ GND <── GND    │   │ GND <── GND    │
             │ SDA <── D2     │   │ SDA <── D2     │
             │ SCL <── D1     │   │ SCL <── D1     │
             └────────────────┘   └────────────────┘
```

---

## 4. Kiểm Tra Trước Khi Cắm Điện

1. Dùng đồng hồ VOM đo kiểm tra thông mạch xem chân **GND** của tất cả các module đã nối liền với nhau chưa.
2. Kiểm tra biến trở vi chỉnh (núm vặn màu xanh) ở mặt sau module I2C của màn hình LCD 1602: dùng tua-vít vặn để chỉnh độ tương phản chữ rõ nét nhất.
3. Không chạm tay vào mạch trần khi đang cấp điện để tránh phóng tĩnh điện làm chết cổng I2C của MAX30102.
