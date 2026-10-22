# HƯỚNG DẪN CHI TIẾT (WALKTHROUGH): THIẾT LẬP VÀ VẬN HÀNH PHẦN CỨNG ESP32-CAM

Tài liệu này hướng dẫn toàn diện từ sơ đồ đấu nối chân, cấu hình mã nguồn, quy trình nạp firmware qua PlatformIO đến kiểm thử kết nối với máy chủ AI cho dự án **PBL4-FaceHealth-IoT**.

---

## 📌 1. Danh sách linh kiện phần cứng

1. **02 Bo mạch ESP32-CAM AI-Thinker** (Kèm module mắt Camera OV2640).
2. **01 Cảm biến đo nhịp tim & nồng độ oxy trong máu MAX30102** (Giao tiếp I2C).
3. **01 Màn hình LCD 1602A** kèm **Module chuyển đổi I2C Backpack (PCF8574)** (4 chân: VCC, GND, SDA, SCL).
4. **01 Đèn LED báo hiệu** (màu đỏ/vàng) + **01 Điện trở hạn dòng 220Ω - 330Ω**.
5. **Dây cắm Jumper** (Đực - Cái, Cái - Cái).
6. **01 Mạch chuyển USB-to-UART** (FTDI FT232RL, CP2102 hoặc CH340) để nạp code.
7. **Nguồn cấp 5V/2A ổn định** (hoặc củ sạc điện thoại 5V chất lượng tốt).

---

## 🔌 2. Sơ đồ đấu nối dây chi tiết (Wiring Schematics)

> [!WARNING]
> ESP32-CAM không tích hợp IC nạp tự động và có rất ít chân GPIO rỗi do camera OV2640 và PSRAM chiếm dụng. **Tuyệt đối không gắn thẻ nhớ MicroSD** để sử dụng an toàn các chân GPIO 12, 13, 15.

### 2.1. Mạch 1 — ESP32-CAM Điểm danh sinh viên (AI 1)

Mạch 1 tập trung tối đa tài nguyên cho Camera và truyền tải ảnh, không gắn thêm cảm biến ngoại vi nhằm tránh sụt áp và suy hao tín hiệu.

| Chân ESP32-CAM | Chức năng / Kết nối |
| :--- | :--- |
| **5V** | Nối nguồn dương 5V DC (Nguồn 5V/2A hoặc chân 5V của FTDI khi nạp) |
| **GND** | Nối cực âm nguồn (Mass GND chung) |
| **GPIO 4** | Đèn Flash LED trắng tích hợp trên bo (tự động nháy khi điểm danh thành công) |
| **GPIO 33** | Đèn LED đỏ nhỏ mặt sau (báo trạng thái khởi động / WiFi) |

---

### 2.2. Mạch 2 — ESP32-CAM Giám sát sức khỏe & Trạng thái (AI 2)

Mạch 2 kết nối với cảm biến MAX30102, màn hình LCD 1602 qua **bus I2C chia sẻ chung chân SDA/SCL**, và 1 đèn LED cảnh báo.

```
                  ┌───────────────────────────────┐
                  │      ESP32-CAM (AI-Thinker)   │
                  │                               │
                  │   GPIO 13 (SDA)  GPIO 15 (SCL)│
                  └───┬──────────────┬────────────┘
                      │              │
        ┌─────────────┴─────┐  ┌─────┴─────────────┐
        │  MAX30102 Sensor  │  │   LCD 1602 I2C    │
        │   SDA      SCL    │  │   SDA      SCL    │
        └───────────────────┘  └───────────────────┘
```

#### Bảng đấu dây chi tiết cho Mạch 2:

| Linh kiện | Chân linh kiện | Chân nối ESP32-CAM | Ghi chú kỹ thuật |
| :--- | :--- | :--- | :--- |
| **MAX30102** | **VIN / VCC** | **3.3V** | Cấp nguồn 3.3V từ chân 3V3 của ESP32-CAM. |
| | **GND** | **GND** | Nối chung GND. |
| | **SDA** | **GPIO 13** | Dùng chung đường dữ liệu SDA của I2C. |
| | **SCL** | **GPIO 15** | Dùng chung đường xung nhịp SCL của I2C. |
| **LCD 1602 I2C** | **VCC** | **5V** | LCD cần nguồn 5V để màn hình có độ sáng và tương phản rõ. |
| | **GND** | **GND** | Nối chung GND. |
| | **SDA** | **GPIO 13** | Nối song song vào chân SDA (GPIO 13). |
| | **SCL** | **GPIO 15** | Nối song song vào chân SCL (GPIO 15). |
| **LED Cảnh báo** | **Chân dài (+ / Anode)** | **GPIO 12** | Nối tiếp qua điện trở 220Ω - 330Ω vào chân dài của LED. |
| | **Chân ngắn (- / Cathode)**| **GND** | Nối vào mass GND. |

> [!TIP]
> **Chỉnh độ nét màn hình LCD 1602**: Nếu sau khi cấp điện mà LCD chỉ sáng đèn nền hoặc xuất hiện các ô vuông đen, hãy dùng tuốc nơ vít nhỏ xoay nhẹ núm chiết áp màu xanh ở mặt sau bo chuyển đổi I2C (PCF8574) cho đến khi chữ hiện rõ.

---

## ⚙️ 3. Cấu hình thông số mạng và máy chủ

Trước khi nạp code, mở file cấu hình trung tâm [config.h](file:///D:/PBL4/PBL4-FaceHealth-IoT/ESP32-CAM/include/config.h) và cập nhật thông tin:

```cpp
// 1. Tên và mật khẩu mạng WiFi
#define WIFI_SSID           "TEN_WIFI_CUA_BAN"
#define WIFI_PASSWORD       "MAT_KHAU_WIFI"

// 2. Địa chỉ IP của máy tính chạy server AI
// (Xem bằng lệnh 'ipconfig' trên Windows, ví dụ 192.168.1.15)
#define SERVER_HOST         "192.168.1.15"
#define SERVER_PORT         8000
```

---

## 🚀 4. Hướng dẫn nạp Firmware bằng PlatformIO

### 4.1. Kết nối mạch nạp FTDI với ESP32-CAM

Nối 5 dây từ mạch nạp USB UART sang ESP32-CAM:
- `FTDI 5V` → `ESP32-CAM 5V`
- `FTDI GND` → `ESP32-CAM GND`
- `FTDI TX` → `ESP32-CAM U0R (GPIO 3)`
- `FTDI RX` → `ESP32-CAM U0T (GPIO 1)`
- **Nối dây đưa vào chế độ nạp (Bootloader)**: Dùng 1 dây jumper nối chân **`GPIO 0`** xuống chân **`GND`**.

### 4.2. Thao tác nạp chương trình

1. Cắm cáp USB vào máy tính.
2. Bấm nút **RST / RESET** trên bo ESP32-CAM một lần để bo vào chế độ nạp Flash.
3. Mở terminal tại thư mục `ESP32-CAM/`:

#### Nạp cho Mạch 1 (Điểm danh):
```powershell
cd D:\PBL4\PBL4-FaceHealth-IoT\ESP32-CAM
pio run -e esp32cam_attendance -t upload
```

#### Nạp cho Mạch 2 (Sức khỏe & Trạng thái):
*(Rút cáp nạp từ Mạch 1 chuyển sang nối với Mạch 2, nối GPIO 0 xuống GND và bấm Reset)*:
```powershell
pio run -e esp32cam_health -t upload
```

4. **Khởi động chạy code**:
   - Rút dây nối giữa **`GPIO 0`** và **`GND`**.
   - Bấm nút **RST / RESET** trên bo để bắt đầu chạy chương trình.
   - Mở Serial Monitor để theo dõi log:
     ```powershell
     pio device monitor -b 115200
     ```

---

## 🖥️ 5. Khởi động AI API Server trên Máy tính

Máy chủ nhận dữ liệu được xây dựng bằng FastAPI, tích hợp trực tiếp **AI 1 (InsightFace `buffalo_sc`)** và **AI 2 (MediaPipe Face Mesh + Random Forest)**.

```powershell
# Chuyển vào thư mục pbl4-face-ai
cd D:\PBL4\PBL4-FaceHealth-IoT\pbl4-face-ai

# Kích hoạt môi trường ảo (nếu có)
.venv\Scripts\Activate.ps1

# Cài đặt các thư viện bổ sung (FastAPI, Uvicorn, Multipart)
pip install -r requirements.txt

# Khởi chạy API Server
python src/api_server.py
```

Khi server khởi chạy thành công, terminal sẽ thông báo:
```
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

---

## 🧪 6. Kịch bản kiểm thử toàn diện (End-to-End Testing)

### Test 1: Kiểm thử Mạch 1 (Điểm danh)
1. Bật nguồn Mạch 1. Đèn đỏ nhỏ nháy 3 lần báo hiệu đã kết nối WiFi.
2. Đứng đối diện trước ống kính camera OV2640 ở cự ly khoảng 0.5m - 1.2m.
3. ESP32-CAM tự động chụp ảnh gửi về endpoint `POST /api/attendance`.
4. Quan sát log trên server:
   - Nếu đã đăng ký khuôn mặt trong hệ thống: Trả về `matched: true`, in ra `MSSV - Họ tên`. Đèn Flash trên ESP32-CAM nháy sáng xác nhận thành công.
   - Nếu chưa đăng ký: Trả về `matched: false`, `Chưa đăng ký`.

### Test 2: Kiểm thử Mạch 2 (Sức khỏe & Trạng thái)
1. Bật nguồn Mạch 2. Màn hình LCD 1602 hiển thị dòng chữ:
   ```
   FaceHealth Ready
   Dat tay len cam bien
   ```
2. Đặt nhẹ đầu ngón tay trỏ lên mặt kính cảm biến **MAX30102** (giữ êm, không đè quá mạnh).
3. Đặt Mạch 2 quan sát tư thế khuôn mặt trong lúc làm việc/học tập.
4. Màn hình LCD 1602 sẽ cập nhật liên tục:
   - Dòng 1: `HR: 76  SpO2: 98%` (Nhịp tim và oxy trong máu).
   - Dòng 2: `St: Normal` (Trạng thái bình thường).
5. **Thử nghiệm cảnh báo**:
   - Nhắm mắt lâu (> 1.5 giây) hoặc ngáp mở to miệng hoặc gục đầu xuống bàn:
   - Server phân tích ra nhãn `Drowsy`, `Yawn` hoặc `Head-down`, trả về `alert: true`.
   - **Đèn LED cảnh báo (GPIO 12) lập tức bật sáng**.
   - Màn hình LCD 1602 chuyển sang hiển thị trạng thái cảnh báo tương ứng.
