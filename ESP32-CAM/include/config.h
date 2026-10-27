#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>
#include "camera_pins.h"

// =========================================================================
// 1. CẤU HÌNH MẠNG WIFI GIA ĐÌNH (MẶC ĐỊNH)
// =========================================================================
#define DEFAULT_WIFI_SSID       "Phuong Thao"       // Tên WiFi gia đình (2.4 GHz)
#define DEFAULT_WIFI_PASS       "0796781776"        // Mật khẩu WiFi

// =========================================================================
// 2. CẤU HÌNH MÁY CHỦ FLASK SERVER (MÁY TÍNH WINDOWS)
// =========================================================================
#define DEFAULT_SERVER_URL          "http://192.168.1.182:5000/upload"
#define DEFAULT_SERVER_REGISTER_URL "http://192.168.1.182:5000/api/register_camera"
#define HTTP_TIMEOUT_MS             5000                // Thời gian chờ phản hồi tối đa (ms)

// =========================================================================
// 3. THÔNG SỐ VẬN HÀNH STREAMING ON-DEMAND & mDNS (NODE 1)
// =========================================================================
#define MDNS_HOSTNAME          "esp32cam"          // Tên miền mạng cục bộ: http://esp32cam.local:81/stream
#define STREAM_SERVER_PORT     81                  // Cổng phát luồng video MJPEG
#define INDICATOR_LED_PIN      33                  // Đèn LED đỏ nhỏ sau lưng bo (Active LOW: LOW=Sáng, HIGH=Tắt)
#define FLASH_LED_PIN          4                   // Đèn Flash công suất cao (Active HIGH)

// =========================================================================
// 4. CẤU HÌNH AP WEB PORTAL DỰ PHÒNG KHI ĐỔI MẠNG
// =========================================================================
// Nếu sau 15s không kết nối được WiFi mặc định, ESP32 sẽ tự phát WiFi này
// Người dùng dùng điện thoại/laptop kết nối vào và mở http://192.168.4.1 để nhập WiFi mới
#define AP_SSID                "ESP32-CAM-CONFIG"
#define AP_PASS                ""                  // Để trống để kết nối nhanh

#endif // CONFIG_H
