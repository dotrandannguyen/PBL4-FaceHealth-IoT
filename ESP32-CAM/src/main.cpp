#include <Arduino.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <esp_camera.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "config.h"
#include "stream_server.h"
#include "wifi_sync.h"

// Biến lưu cấu hình
Preferences prefs;
String wifi_ssid;
String wifi_pass;
String server_url;
WiFiMulti wifiMulti;
bool isCameraServerStarted = false;

// Cấu trúc lưu trữ đa mạng Wi-Fi (WiFi Vault)
struct WifiProfile {
    String ssid;
    String pass;
};
#define MAX_SAVED_WIFI 8
WifiProfile savedWifis[MAX_SAVED_WIFI];
int savedWifiCount = 0;

void loadSavedWifis() {
    prefs.begin("wifi_vault", false);
    savedWifiCount = prefs.getInt("count", 0);
    if (savedWifiCount <= 0) {
        savedWifiCount = 1;
        savedWifis[0].ssid = DEFAULT_WIFI_SSID;
        savedWifis[0].pass = DEFAULT_WIFI_PASS;
        prefs.putInt("count", 1);
        prefs.putString("s_0", DEFAULT_WIFI_SSID);
        prefs.putString("p_0", DEFAULT_WIFI_PASS);
    } else {
        if (savedWifiCount > MAX_SAVED_WIFI) savedWifiCount = MAX_SAVED_WIFI;
        for (int i = 0; i < savedWifiCount; i++) {
            savedWifis[i].ssid = prefs.getString(String("s_" + String(i)).c_str(), "");
            savedWifis[i].pass = prefs.getString(String("p_" + String(i)).c_str(), "");
        }
    }
    prefs.end();
}

void saveWifiToVault(const String& new_ssid, const String& new_pass) {
    if (new_ssid.length() == 0) return;
    loadSavedWifis();

    int foundIdx = -1;
    for (int i = 0; i < savedWifiCount; i++) {
        if (savedWifis[i].ssid == new_ssid) {
            foundIdx = i;
            break;
        }
    }

    prefs.begin("wifi_vault", false);
    if (foundIdx != -1) {
        savedWifis[foundIdx].pass = new_pass;
        prefs.putString(String("p_" + String(foundIdx)).c_str(), new_pass);
    } else {
        int insertIdx = savedWifiCount;
        if (insertIdx >= MAX_SAVED_WIFI) {
            insertIdx = MAX_SAVED_WIFI - 1;
        } else {
            savedWifiCount++;
            prefs.putInt("count", savedWifiCount);
        }
        savedWifis[insertIdx].ssid = new_ssid;
        savedWifis[insertIdx].pass = new_pass;
        prefs.putString(String("s_" + String(insertIdx)).c_str(), new_ssid);
        prefs.putString(String("p_" + String(insertIdx)).c_str(), new_pass);
    }
    prefs.end();
}

// Khai báo trước hàm báo danh
void baoDanhLenServer();

// Trạng thái hệ thống
bool isConfigPortal = true; // Luôn luôn duy trì Web Portal
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
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #fff; padding: 20px; display: flex; justify-content: center; }
        .box { background: #1e293b; padding: 24px; border-radius: 12px; width: 100%; max-width: 380px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        h2 { font-size: 1.25rem; margin-bottom: 6px; color: #38bdf8; text-align: center; }
        p { font-size: 0.85rem; color: #94a3b8; text-align: center; margin-bottom: 18px; }
        label { font-size: 0.85rem; font-weight: 600; display: block; margin-top: 14px; margin-bottom: 4px; }
        input, select { width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #090d16; color: #fff; font-size: 0.95rem; box-sizing: border-box; }
        select { cursor: pointer; border-color: #38bdf8; background: #131c2e; font-weight: 500; }
        button { width: 100%; padding: 12px; background: #2563eb; color: #fff; border: none; border-radius: 6px; font-size: 1rem; font-weight: 600; margin-top: 22px; cursor: pointer; transition: 0.2s; }
        button:hover { background: #1d4ed8; }
        .tag { display: inline-block; background: #0369a1; color: #e0f2fe; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; margin-bottom: 8px; }
    </style>
</head>
<body>
    <div class="box">
        <div style="text-align: center;"><span class="tag">📡 PBL4 Smart Config</span></div>
        <h2>⚙️ Cài Đặt WiFi Trạm Chấm Công</h2>
        <p>Chọn mạng quen thuộc hoặc nhập mạng mới</p>
        
        <label>📂 Danh sách Wi-Fi đã lưu:</label>
        <select id="knownWifi" onchange="onSelectWifi(this)">
            {WIFI_OPTIONS}
        </select>
        
        <form action="/save" method="POST">
            <label>Tên WiFi (SSID):</label>
            <input type="text" id="ssid" name="ssid" value="{SSID}" placeholder="Nhập tên WiFi" required>
            
            <label>Mật khẩu WiFi:</label>
            <input type="password" id="pass" name="pass" value="{PASS}" placeholder="Nhập mật khẩu (nếu có)">
            
            <label>IP Máy chủ AI Server (Port 5001):</label>
            <input type="text" id="server" name="server" value="{SERVER}" placeholder="Ví dụ: 192.168.1.182:5001">
            <div style="font-size: 0.75rem; color: #f59e0b; margin-top: 4px;">⚠️ Lưu ý: Chỉ hỗ trợ Wi-Fi 2.4 GHz. Với iPhone, hãy bật "Tối đa hóa khả năng tương thích".</div>
            
            <button type="submit">💾 Lưu & Tự Động Kết Nối</button>
        </form>
        <div style="margin-top: 15px; text-align: center;">
            <button type="button" style="background:#059669; padding: 10px; font-size: 0.9rem;" onclick="syncNow()">⚡ Bắn Sóng Sang ESP8266 Ngay</button>
            <div id="syncMsg" style="font-size: 0.8rem; color: #34d399; margin-top: 6px;"></div>
        </div>
    </div>
    <script>
    function syncNow() {
        var msg = document.getElementById('syncMsg');
        msg.textContent = 'Đang phát sóng đồng bộ sang ESP8266...';
        fetch('/sync_now').then(function(r){ return r.json(); }).then(function(d){
            msg.textContent = d.message || 'Đã phát sóng đồng bộ!';
        }).catch(function(e){
            msg.textContent = 'Lỗi gửi lệnh!';
        });
    }
    function onSelectWifi(sel) {
        if (sel.value === "new") {
            document.getElementById('ssid').value = "";
            document.getElementById('pass').value = "";
            document.getElementById('ssid').placeholder = "Nhập tên WiFi mới...";
            document.getElementById('ssid').focus();
        } else if (sel.value !== "") {
            var opt = sel.options[sel.selectedIndex];
            document.getElementById('ssid').value = opt.getAttribute('data-ssid') || "";
            document.getElementById('pass').value = opt.getAttribute('data-pass') || "";
        }
    }
    </script>
</body>
</html>
)rawliteral";

void handleRoot() {
    loadSavedWifis();

    String optionsHtml = "<option value=''>-- Chọn mạng đã lưu (" + String(savedWifiCount) + " mạng) --</option>";
    for (int i = 0; i < savedWifiCount; i++) {
        if (savedWifis[i].ssid.length() == 0) continue;
        String isCurrent = (savedWifis[i].ssid == WiFi.SSID()) ? " (Đang kết nối)" : "";
        optionsHtml += "<option value='" + String(i) + "' data-ssid='" + savedWifis[i].ssid + "' data-pass='" + savedWifis[i].pass + "'>" 
                       + savedWifis[i].ssid + isCurrent + "</option>";
    }
    optionsHtml += "<option value='new'>➕ [Nhập mạng mới...]</option>";

    String html = FPSTR(PORTAL_HTML);
    html.replace("{WIFI_OPTIONS}", optionsHtml);
    html.replace("{SSID}", wifi_ssid);
    html.replace("{PASS}", wifi_pass);
    html.replace("{SERVER}", server_url);
    server.send(200, "text/html; charset=utf-8", html);
}

// =========================================================================
// ĐỒNG BỘ CẤU HÌNH WIFI SANG ESP8266 QUA SÓNG ESP-NOW NỘI BỘ (KHÔNG CẦN DÂY)
// =========================================================================
void broadcastWifiCredentials(const String& target_ssid, const String& target_pass, const String& target_server, int bursts = 25) {
    if (target_ssid.length() == 0) return;

    Serial.println("\n[ESP-NOW] ===============================================");
    Serial.printf("[ESP-NOW] Dang phat song dong bo WiFi sang ESP8266: '%s' (%d goi)...\n", target_ssid.c_str(), bursts);

    wifi_mode_t currentMode = WiFi.getMode();
    if (currentMode != WIFI_AP_STA && currentMode != WIFI_STA && currentMode != WIFI_AP) {
        WiFi.mode(WIFI_AP_STA);
        currentMode = WIFI_AP_STA;
    }

    if (esp_now_init() != ESP_OK) {
        Serial.println("[ESP-NOW] ESP-NOW da san sang.");
    }

    esp_now_peer_info_t peerInfo = {};
    memset(&peerInfo, 0, sizeof(peerInfo));
    for (int i = 0; i < 6; i++) {
        peerInfo.peer_addr[i] = 0xFF; // Địa chỉ MAC Broadcast
    }
    peerInfo.channel = 0; // 0 = Kênh hiện tại của card Wi-Fi
    peerInfo.encrypt = false;
    peerInfo.ifidx = (WiFi.getMode() == WIFI_STA) ? WIFI_IF_STA : WIFI_IF_AP;

    if (esp_now_is_peer_exist(peerInfo.peer_addr)) {
        esp_now_del_peer(peerInfo.peer_addr);
    }
    esp_err_t addRes = esp_now_add_peer(&peerInfo);
    if (addRes != ESP_OK && peerInfo.ifidx == WIFI_IF_AP) {
        Serial.printf("[ESP-NOW] Add peer tren AP that bai (%d), fallback WIFI_IF_STA...\n", addRes);
        peerInfo.ifidx = WIFI_IF_STA;
        esp_now_add_peer(&peerInfo);
    }

    struct_wifi_sync pkt;
    memset(&pkt, 0, sizeof(pkt));
    memcpy(pkt.magic, WIFI_SYNC_MAGIC, WIFI_SYNC_MAGIC_LEN);
    strncpy(pkt.ssid, target_ssid.c_str(), sizeof(pkt.ssid) - 1);
    strncpy(pkt.pass, target_pass.c_str(), sizeof(pkt.pass) - 1);
    strncpy(pkt.server, target_server.c_str(), sizeof(pkt.server) - 1);

    int successCount = 0;
    int packetDelay = (bursts > 5) ? 80 : 25;
    for (int i = 0; i < bursts; i++) {
        esp_err_t result = esp_now_send(peerInfo.peer_addr, (uint8_t*)&pkt, sizeof(pkt));
        if (result == ESP_OK) {
            successCount++;
        }
        delay(packetDelay);
    }
    Serial.printf("[ESP-NOW] Hoan tat phat song! Thanh cong: %d/%d goi tin.\n", successCount, bursts);
    Serial.println("[ESP-NOW] ===============================================");
}

void handleSave() {
    if (server.hasArg("ssid")) {
        wifi_ssid  = server.arg("ssid");
        wifi_pass  = server.hasArg("pass") ? server.arg("pass") : "";
        if (server.hasArg("server") && server.arg("server").length() > 0) {
            server_url = server.arg("server");
        } else if (server_url.length() == 0) {
            server_url = DEFAULT_SERVER_URL;
        }

        prefs.begin("wifi_cfg", false);
        prefs.putString("ssid", wifi_ssid);
        prefs.putString("pass", wifi_pass);
        prefs.putString("server", server_url);
        prefs.end();

        // Lưu vào kho mạng đã lưu (WiFi Vault)
        saveWifiToVault(wifi_ssid, wifi_pass);

        server.send(200, "text/html; charset=utf-8", 
            "<h2 style='font-family: sans-serif; text-align: center; margin-top: 50px; color: #16a34a;'>"
            "✅ Đã lưu cấu hình & Đang đồng bộ sang ESP8266...<br>Hệ thống đang tự động kết nối...</h2>");
        
        delay(500);

        // Đồng bộ ngay lập tức sang ESP8266 qua sóng ESP-NOW (30 gói tin)
        broadcastWifiCredentials(wifi_ssid, wifi_pass, server_url, 30);

        delay(1000);
        ESP.restart();
    } else {
        server.send(400, "text/plain", "Thieu ten WiFi!");
    }
}

void startConfigPortal() {
    isConfigPortal = true;

    WiFi.mode(WIFI_AP_STA); // Kích hoạt cả AP và STA để luôn phát AP song song
    bool apOk = WiFi.softAP(AP_SSID, AP_PASS, 1); // Cố định Channel 1 cho AP (AP_PASS = NULL: hoàn toàn không mật khẩu)

    Serial.println("\n[PORTAL] ===================================================");
    if (apOk) {
        Serial.println("[PORTAL] ✅ AP 'ESP32-CAM-CONFIG' DANG PHAT LIEN TUC (MANG MO, KHONG PASS)!");
    } else {
        Serial.println("[PORTAL] ⚠️ Khong the bat tren Channel 1, thu phat tren Channel 6...");
        WiFi.softAP(AP_SSID, AP_PASS, 6);
    }
    Serial.printf("[PORTAL] 1. Ket noi WiFi: %s (Mạng mở, không có mật khẩu)\n", AP_SSID);
    Serial.printf("[PORTAL] 2. Mo trinh duyet: http://%s/\n", WiFi.softAPIP().toString().c_str());
    Serial.println("[PORTAL] ===================================================");

    server.on("/", HTTP_GET, handleRoot);
    server.on("/save", HTTP_POST, handleSave);
    server.on("/sync_now", HTTP_GET, []() {
        broadcastWifiCredentials(wifi_ssid, wifi_pass, server_url, 30);
        server.send(200, "application/json", "{\"success\":true,\"message\":\"Da phat 30 goi tin dong bo sang ESP8266!\"}");
    });
    server.begin();
}

// =========================================================================
// 3. KẾT NỐI WIFI (MULTI-WIFI TỰ ĐỘNG CHỌN MẠNG TỐT NHẤT)
// =========================================================================
bool connectWiFi() {
    Serial.println("\n[WIFI] 🔄 Dang quet va tu dong ket noi mang Wi-Fi tot nhat (Multi-WiFi)...");
    int retries = 0;
    while (wifiMulti.run() != WL_CONNECTED && retries < 25) {
        delay(400);
        Serial.print(".");
        server.handleClient(); // Vẫn phục vụ Web Portal nếu có kết nối
        digitalWrite(INDICATOR_LED_PIN, !digitalRead(INDICATOR_LED_PIN));
        retries++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        digitalWrite(INDICATOR_LED_PIN, HIGH); // Tắt LED (Active LOW)
        Serial.println("\n[WIFI] ✅ Ket noi WiFi thanh cong!");
        Serial.printf("[WIFI] SSID dang ket noi: '%s'\n", WiFi.SSID().c_str());
        Serial.printf("[WIFI] Dia chi IP STA:     %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("[WIFI] Dia chi IP AP:      %s\n", WiFi.softAPIP().toString().c_str());
        Serial.printf("[WIFI] Cuong do tin hieu:  %d dBm\n", WiFi.RSSI());

        // Khởi động mDNS Responder (Truy cập bằng tên miền esp32cam.local trên cùng mạng)
        if (MDNS.begin(MDNS_HOSTNAME)) {
            MDNS.addService("http", "tcp", 80);
            MDNS.addService("http", "tcp", STREAM_SERVER_PORT);
            Serial.printf("[mDNS] ✅ Mo trang cai dat tai: http://%s.local/\n", MDNS_HOSTNAME);
            Serial.printf("[mDNS] ✅ Luong stream camera tai: http://%s.local:%d/stream\n", MDNS_HOSTNAME, STREAM_SERVER_PORT);
        } else {
            Serial.println("[mDNS] ❌ Khoi tao mDNS that bai!");
        }

        // Khởi động Camera Stream Server On-Demand trên cổng 81
        if (!isCameraServerStarted) {
            startCameraServer(STREAM_SERVER_PORT);
            isCameraServerStarted = true;
        }

        // Báo danh IP lên Flask Server máy tính
        baoDanhLenServer();

        // Bắn broadcast đồng bộ sang ESP8266 khi kết nối thành công (30 gói tin)
        broadcastWifiCredentials(WiFi.SSID(), wifi_pass, server_url, 30);

        // Tối ưu nhiệt năng: Tắt phát sóng AP khi đã kết nối Wi-Fi router thành công
        // Giải phóng hoàn toàn băng thông radio và DMA bộ nhớ cho luồng video camera
        if (WiFi.getMode() != WIFI_STA) {
            WiFi.softAPdisconnect(true);
            WiFi.mode(WIFI_STA);
            Serial.println("[POWER-SAVE] ✅ Da tat AP phu vi da ket noi WiFi router. Bo mach se mat hon.");
        }
        WiFi.setSleep(true);
        esp_wifi_set_ps(WIFI_PS_MIN_MODEM);

        return true;
    } else {
        Serial.println("\n[WIFI] ⚠️ Chua tim thay Wi-Fi quen thuoc, AP van dang phat san sang cho cau hinh.");
        return false;
    }
}

// =========================================================================
// 4. CHỤP ẢNH & GỬI LÊN SERVER FLASK QUA HTTP POST
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

    // Xây dựng URL báo danh linh hoạt theo Server IP được cấu hình trong Web Portal
    String host = server_url;
    host.trim();
    if (host.length() == 0) host = DEFAULT_SERVER_URL;
    if (!host.startsWith("http://") && !host.startsWith("https://")) {
        host = "http://" + host;
    }
    // Nếu chưa có cổng thì bổ sung cổng mặc định :5001
    int protoEnd = host.indexOf("://") + 3;
    if (host.indexOf(':', protoEnd) == -1) {
        host += ":5001";
    }
    if (host.endsWith("/")) {
        host = host.substring(0, host.length() - 1);
    }
    String register_url = host + "/api/register_camera";

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
            Serial.printf("[NODE 1] Khong the bao danh len Server %s (%d)\n", register_url.c_str(), httpCode);
        }
        http.end();
    }
}

// =========================================================================
// SETUP & LOOP
// =========================================================================
void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Vô hiệu hóa Brownout Detector chống sập nguồn khi Wi-Fi phát công suất cao
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n========================================================");
    Serial.println("🤖 ESP32-CAM Node 1 — PBL4 FaceHealth IoT");
    Serial.println("🎥 DUAL-MODE SMART PORTAL & STREAMING SERVER");
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

    // 3. Bật Web Portal cấu hình AP (khởi tạo WiFi stack & LwIP)
    startConfigPortal();

    // 4. Khởi động Camera Stream Server On-Demand trên cổng 81 NGAY TỪ ĐẦU (Luôn mở 24/7)
    if (!isCameraServerStarted) {
        startCameraServer(STREAM_SERVER_PORT);
        isCameraServerStarted = true;
        Serial.printf("[STREAM] ✅ Camera Server da san sang tren cong %d (ho tro ca AP & STA)\n", STREAM_SERVER_PORT);
    }

    // 5. Thêm các mạng Wi-Fi từ kho lưu trữ (WiFi Vault) vào danh sách Multi-WiFi
    loadSavedWifis();
    for (int i = 0; i < savedWifiCount; i++) {
        if (savedWifis[i].ssid.length() > 0) {
            wifiMulti.addAP(savedWifis[i].ssid.c_str(), savedWifis[i].pass.c_str());
            Serial.printf("[WIFI-VAULT] Da them mang '%s' vao Multi-WiFi\n", savedWifis[i].ssid.c_str());
        }
    }
    if (wifi_ssid.length() > 0 && wifi_ssid != DEFAULT_WIFI_SSID) {
        wifiMulti.addAP(wifi_ssid.c_str(), wifi_pass.c_str());
    }

    // 6. Tự động kết nối Wi-Fi tốt nhất
    connectWiFi();
}

void loop() {
    // 1. Luôn phục vụ Web Portal nếu AP đang bật hoặc qua mDNS
    server.handleClient();

    unsigned long now = millis();
    static unsigned long lastCheck = 0;
    static unsigned long lastHeartbeat = 0;

    // 2. Tự động phục hồi kết nối nếu bị mất mạng Wi-Fi
    if (WiFi.status() != WL_CONNECTED) {
        // Tự động bật lại AP dự phòng nếu router bị mất kết nối để người dùng vẫn cấu hình được
        if (WiFi.getMode() != WIFI_AP_STA && WiFi.getMode() != WIFI_AP) {
            Serial.println("\n[POWER-SAVE] ⚠️ Mat WiFi router! Tu dong bat lai AP 'ESP32-CAM-CONFIG' de cuu ho...");
            WiFi.mode(WIFI_AP_STA);
            WiFi.softAP(AP_SSID, AP_PASS, 1);
        }

        // Nháy LED chậm báo hiệu đang chờ Wi-Fi
        static unsigned long lastBlink = 0;
        if (now - lastBlink > 800) {
            lastBlink = now;
            digitalWrite(INDICATOR_LED_PIN, !digitalRead(INDICATOR_LED_PIN));
        }

        if (now - lastCheck > 8000) {
            lastCheck = now;
            if (wifiMulti.run() == WL_CONNECTED) {
                connectWiFi();
            }
        }
    } else {
        digitalWrite(INDICATOR_LED_PIN, HIGH); // Tắt LED khi đã có Wi-Fi

        // Heartbeat báo danh định kỳ 30 giây
        if (now - lastHeartbeat >= 30000) {
            lastHeartbeat = now;
            baoDanhLenServer();
        }
    }

    delay(10);
}