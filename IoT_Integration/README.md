# IoT Integration

## Thiết bị

- ESP32-CAM
- NodeMCU ESP8266
- MAX30102

## Kết nối MAX30102

- VIN → 3V3
- GND → GND
- SCL → D1
- SDA → D2

## Luồng dữ liệu

ESP32-CAM<br>
→ Wi-Fi<br>
→ HTTP POST JPEG<br>
→ PHP API<br>
→ MariaDB

MAX30102<br>
→ ESP8266<br>
→ Wi-Fi<br>
→ HTTP POST JSON<br>
→ PHP API<br>
→ MariaDB

## API đang dùng

- `GET /api/device/ping`
- `POST /api/device/camera-test`
- `POST /api/device/health-test`
- `GET /api/device/camera-test/latest-db`
- `GET /api/device/camera-test/image?id={MaTest}`
- `GET /api/device/integration-test`

## Ghi chú

- Đây là phần tích hợp IoT phục vụ kiểm thử ESP32-CAM và MAX30102.
- PHP backend thật vẫn nằm trong `DoAn_ChamCong_AI`.
- `DeviceIntegrationTest` là bảng test tích hợp, không phải bảng nghiệp vụ chính.
- Không dùng phần này để thay thế code backend thật.
