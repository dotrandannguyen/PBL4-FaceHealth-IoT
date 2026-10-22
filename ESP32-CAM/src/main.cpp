#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include "esp_camera.h"
#include "config.h"
#include "stream_server.h"

// Biến lưu cấu hình
Preferences prefs;
String wifi_ssid;
String wifi_pass;
String server_url;

// Trạng thái hệ thống
bool isConfigPortal = false;
WebServer server(80);
unsigned long lastCaptureTime = 0;

// =========================================================================
// 1. KHỞI TẠO CAMERA OV2640 (AI-THINKER ESP32-CAM)
// =========================================================================
bool initCamera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;
    config.pin_d0       = Y2_GPIO_NUM;
    config.pin_d1       = Y3_GPIO_NUM;
    config.pin_d2       = Y4_GPIO_NUM;
    config.pin_d3       = Y5_GPIO_NUM;
    config.pin_d4       = Y6_GPIO_NUM;
    config.pin_d5       = Y7_GPIO_NUM;
    config.pin_d6       = Y8_GPIO_NUM;
    config.pin_d7       = Y9_GPIO_NUM;
    config.pin_xclk     = XCLK_GPIO_NUM;
    config.pin_pclk     = PCLK_GPIO_NUM;
    config.pin_vsync    = VSYNC_GPIO_NUM;
    config.pin_href     = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn     = PWDN_GPIO_NUM;
    config.pin_reset    = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;

    // Tối ưu độ phân giải cho chu kỳ gửi 3s
    if (psramFound()) {
        config.frame_size   = FRAMESIZE_VGA;  // 640x480 (chất lượng tốt, truyền cực nhanh)
        config.jpeg_quality = 12;             // 10-14 là tối ưu (chỉ số càng thấp ảnh càng nét)
        config.fb_count     = 2;
    } else {
        config.frame_size   = FRAMESIZE_CIF;  // 400x296 nếu không có PSRAM
        config.jpeg_quality = 15;
        config.fb_count     = 1;
    }

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[CAM] Khoi tao camera that bai! Ma loi: 0x%x\n", err);
        return false;
    }

    // Tối ưu cảm biến ảnh OV2640
    sensor_t *s = esp_camera_sensor_get();
    if (s != NULL) {
        s->set_brightness(s, 1);    // Tăng sáng nhẹ
        s->set_contrast(s, 1);      // Tăng tương phản
        s->set_saturation(s, 0);
    }

    Serial.println("[CAM] Khoi tao Camera OV2640 thanh cong!");
    return true;
}

// =========================================================================
// 2. GIAO DIỆN WEB CẤU HÌNH DỰ PHÒNG (AP WEB PORTAL 192.168.4.1)
// =========================================================================
const char PORTAL_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cài Đặt WiFi ESP32-CAM</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #0f172a; color: #fff; padding: 20px; display: flex; justify-content: center; }
        .box { background: #1e293b; padding: 24px; border-radius: 12px; width: 100%; max-width: 380px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        h2 { font-size: 1.25rem; margin-bottom: 8px; color: #38bdf8; text-align: center; }
        p { font-size: 0.85rem; color: #94a3b8; text-align: center; margin-bottom: 20px; }
        label { font-size: 0.85rem; font-weight: 600; display: block; margin-top: 14px; margin-bottom: 4px; }
        input { width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #090d16; color: #fff; font-size: 0.95rem; box-sizing: border-box; }
        button { width: 100%; padding: 12px; background: #2563eb; color: #fff; border: none; border-radius: 6px; font-size: 1rem; font-weight: 600; margin-top: 24px; cursor: pointer; }
        button:hover { background: #1d4ed8; }
    </style>
</head>
<body>
    <div class="box">
        <h2>⚙️ Cài Đặt Mạng ESP32-CAM</h2>
        <p>Nhập thông tin WiFi và Server để kết nối</p>
        <form action="/save" method="POST">
            <label>Tên WiFi (SSID):</label>
            <input type="text" name="ssid" value="{SSID}" required>
            
            <label>Mật khẩu WiFi:</label>
            <input type="password" name="pass" value="{PASS}" required>
            
            <label>Đường dẫn Server Upload:</label>
            <input type="text" name="server" value="{SERVER}" required>
            
            <button type="submit">💾 Lưu & Khởi Động Lại</button>
        </form>
    </div>
</body>
</html>
)rawliteral";

void handleRoot() {
    String html = FPSTR(PORTAL_HTML);
    html.replace("{SSID}", wifi_ssid);
    html.replace("{PASS}", wifi_pass);
    html.replace("{SERVER}", server_url);
    server.send(200, "text/html", html);
}

void handleSave() {
    if (server.hasArg("ssid") && server.hasArg("pass") && server.hasArg("server")) {
        wifi_ssid  = server.arg("ssid");
        wifi_pass  = server.arg("pass");
        server_url = server.arg("server");

        prefs.begin("wifi_cfg", false);
        prefs.putString("ssid", wifi_ssid);
        prefs.putString("pass", wifi_pass);
        prefs.putString("server", server_url);
        prefs.end();

        server.send(200, "text/html; charset=utf-8", 
            "<h2 style='font-family: sans-serif; text-align: center; margin-top: 50px; color: #16a34a;'>"
            "✅ Đã lưu cấu hình!<br>ESP32-CAM đang khởi động lại và kết nối...</h2>");
        
        delay(1500);
        ESP.restart();
    } else {
        server.send(400, "text/plain", "Thieu tham so!");
    }
}

void startConfigPortal() {
    isConfigPortal = true;
    WiFi.disconnect(true);
    delay(500);

    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASS);

    Serial.println("\n[PORTAL] ===================================================");
    Serial.println("[PORTAL] Khong the ket noi WiFi! Da bat Web Portal cai dat.");
    Serial.printf("[PORTAL] 1. Ket noi WiFi: %s\n", AP_SSID);
    Serial.printf("[PORTAL] 2. Mo trinh duyet: http://%s/\n", WiFi.softAPIP().toString().c_str());
    Serial.println("[PORTAL] ===================================================");

    server.on("/", HTTP_GET, handleRoot);
    server.on("/save", HTTP_POST, handleSave);
    server.begin();
}

// =========================================================================
// 3. KẾT NỐI WIFI
// =========================================================================
bool connectWiFi() {
    Serial.printf("\n[WIFI] Dang ket noi den WiFi: '%s'...\n", wifi_ssid.c_str());
    WiFi.mode(WIFI_STA);
    WiFi.begin(wifi_ssid.c_str(), wifi_pass.c_str());

    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 25) { // Thử trong ~12.5 giây
        delay(500);
        Serial.print(".");
        
        // Nháy LED đỏ nhỏ báo đang kết nối
        digitalWrite(INDICATOR_LED_PIN, !digitalRead(INDICATOR_LED_PIN));
        retries++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        digitalWrite(INDICATOR_LED_PIN, HIGH); // Tắt LED (Active LOW)
        Serial.println("\n[WIFI] ✅ Ket noi WiFi thanh cong!");
        Serial.printf("[WIFI] Dia chi IP ESP32: %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("[WIFI] Cuong do tin hieu (RSSI): %d dBm\n", WiFi.RSSI());
        Serial.printf("[SERVER] Server muc tieu: %s\n", server_url.c_str());
        return true;
    } else {
        Serial.println("\n[WIFI] ❌ Ket noi WiFi that bai!");
        return false;
    }
}

// =========================================================================
// 4. CHỤP ẢNH & GỬI LÊN SERVER FLASK QUA HTTP POST (CHU KỲ 3 GIÂY)
// =========================================================================
// BÁO DANH IP LÊN MÁY CHỦ FLASK SERVER (MÁY TÍNH WINDOWS)
// =========================================================================
void baoDanhLenServer() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[NODE 1] Mat ket noi WiFi! Dang thu ket noi lai...");
        WiFi.reconnect();
        return;
    }

    WiFiClient client;
    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);

    String register_url = DEFAULT_SERVER_REGISTER_URL;
    if (http.begin(client, register_url)) {
        http.addHeader("Content-Type", "application/json");

        String jsonPayload = String("{\"node\":\"node1\",\"ip\":\"") + WiFi.localIP().toString() + 
                             String("\",\"port\":") + String(STREAM_SERVER_PORT) + 
                             String(",\"stream_url\":\"http://") + WiFi.localIP().toString() + String(":") + String(STREAM_SERVER_PORT) + String("/stream\"}");

        int httpCode = http.POST(jsonPayload);
        if (httpCode > 0) {
            Serial.printf("[NODE 1] Da bao danh len Flask Server: HTTP %d (IP: %s, Port: %d)\n", 
                          httpCode, WiFi.localIP().toString().c_str(), STREAM_SERVER_PORT);
        } else {
            Serial.printf("[NODE 1] Khong the bao danh len Server (%d)\n", httpCode);
        }
        http.end();
    }
}

// =========================================================================
// SETUP & LOOP
// =========================================================================
void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n========================================================");
    Serial.println("🤖 ESP32-CAM Node 1 — PBL4 FaceHealth IoT");
    Serial.println("🎥 ON-DEMAND STREAMING SERVER (PORT 81)");
    Serial.println("========================================================");

    // Cài đặt chân LED báo hiệu (GPIO 33 - Active LOW)
    pinMode(INDICATOR_LED_PIN, OUTPUT);
    digitalWrite(INDICATOR_LED_PIN, HIGH); // Tắt LED ban đầu (chế độ nghỉ)

    // 1. Nạp cấu hình từ Flash
    prefs.begin("wifi_cfg", false);
    wifi_ssid  = prefs.getString("ssid", DEFAULT_WIFI_SSID);
    wifi_pass  = prefs.getString("pass", DEFAULT_WIFI_PASS);
    server_url = prefs.getString("server", DEFAULT_SERVER_URL);
    prefs.end();

    // 2. Khởi tạo Camera
    if (!initCamera()) {
        Serial.println("[FATAL] Dung chuong trinh vi camera khong hoat dong!");
        while (true) {
            digitalWrite(INDICATOR_LED_PIN, LOW); delay(200);
            digitalWrite(INDICATOR_LED_PIN, HIGH); delay(200);
        }
    }

    // 3. Kết nối WiFi. Nếu thất bại -> mở AP Web Portal cấu hình
    if (connectWiFi()) {
        // Khởi động mDNS Responder (Tên miền cục bộ: esp32cam.local)
        if (MDNS.begin(MDNS_HOSTNAME)) {
            MDNS.addService("http", "tcp", STREAM_SERVER_PORT);
            Serial.printf("[mDNS] ✅ Da dang ky ten mien cuc bo: http://%s.local:%d/stream\n", MDNS_HOSTNAME, STREAM_SERVER_PORT);
        } else {
            Serial.println("[mDNS] ❌ Khoi tao mDNS that bai!");
        }

        // Khởi động Camera Stream Server On-Demand trên cổng 81
        startCameraServer(STREAM_SERVER_PORT);

        // Báo danh IP lên Flask Server máy tính
        baoDanhLenServer();
    } else {
        startConfigPortal();
    }
}

void loop() {
    if (isConfigPortal) {
        // Chế độ Web Portal: xử lý client web nhập WiFi
        server.handleClient();
        
        // Nháy LED chậm báo chế độ Portal
        static unsigned long lastBlink = 0;
        if (millis() - lastBlink > 800) {
            lastBlink = millis();
            digitalWrite(INDICATOR_LED_PIN, !digitalRead(INDICATOR_LED_PIN));
        }
        delay(10);
        return;
    }

    // Định kỳ 30 giây gửi 1 gói tin Heartbeat báo danh nhẹ (vài byte, không quay camera)
    static unsigned long lastHeartbeatTime = 0;
    unsigned long now = millis();
    if (now - lastHeartbeatTime >= 30000) {
        lastHeartbeatTime = now;
        baoDanhLenServer();
    }

    delay(50);
}