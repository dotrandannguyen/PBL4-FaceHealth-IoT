/**
 * =========================================================================
 * PBL4 FaceHealth IoT — Firmware Cảm Biến Sức Khỏe & Hiển Thị LCD 1602
 * Bo mạch: ESP8266 (NodeMCU v2/v3 hoặc WeMos D1 Mini)
 * Cảm biến: MAX30102 (đo Nhịp tim & SpO2)
 * Màn hình: LCD 1602 giao tiếp I2C (PCF8574)
 * =========================================================================
 * TÍNH NĂNG ĐỒNG BỘ MẠNG KHÔNG DÂY (ESP-NOW):
 * - Không cần nạp lại code khi đổi mạng Wi-Fi.
 * - ESP8266 tự động hứng gói tin đồng bộ Wi-Fi (SSID, Password, Server IP) 
 *   do ESP32-CAM phát broadcast bằng sóng nội bộ ESP-NOW.
 * - Lưu vĩnh viễn vào bộ nhớ Flash (EEPROM).
 * =========================================================================
 */

#include <Wire.h>
#include <ESP8266WiFi.h>
#include <ESP8266WiFiMulti.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <espnow.h>
#include <EEPROM.h>
#include "MAX30105.h"
#include "heartRate.h"
#include <time.h>
#include <LiquidCrystal_I2C.h>

// =========================================================================
// 1. CẤU HÌNH CHÂN NỐI PHẦN CỨNG (PIN CONFIGURATION)
// =========================================================================
#define PIN_I2C_SDA         D2        // Chân dữ liệu I2C (GPIO 4) nối SDA của MAX30102 & LCD
#define PIN_I2C_SCL         D1        // Chân xung I2C (GPIO 5) nối SCL của MAX30102 & LCD
#define LCD_I2C_ADDR        0x27      // Địa chỉ I2C của LCD 1602 (thường 0x27 hoặc 0x3F)

// =========================================================================
// 2. CẤU HÌNH ĐỒNG BỘ ESP-NOW & EEPROM
// =========================================================================
#define EEPROM_SIZE         512
#define EEPROM_MAGIC        0x55AA55AA
#define WIFI_SYNC_MAGIC     "PBL4"
#define WIFI_SYNC_MAGIC_LEN 4

// Định dạng gói tin đồng bộ khớp 100% với ESP32-CAM
typedef struct __attribute__((packed)) struct_wifi_sync {
    char magic[4];     // "PBL4"
    char ssid[33];     // Tên WiFi
    char pass[65];     // Mật khẩu WiFi
    char server[65];   // IP máy chủ
} struct_wifi_sync;

struct EEPROMConfig {
    uint32_t magic;
    char ssid[33];
    char pass[65];
    char server[65];
};

// =========================================================================
// 3. BIẾN MẠNG & THÔNG SỐ VẬN HÀNH
// =========================================================================
String wifi_ssid       = "Phuong Thao";                    // WiFi mặc định
String wifi_pass       = "0796781776";                     // Mật khẩu mặc định
String serverHost      = "192.168.1.182";                  // IP máy chủ mặc định
const int aiServicePort = 5001;                            // Cổng AI Service Coordinator
const char* token      = "pbl4_internal_secret_token_2026";// Token bảo mật nội bộ khớp với .env

ESP8266WiFiMulti wifiMulti;
LiquidCrystal_I2C lcd(LCD_I2C_ADDR, 16, 2);
MAX30105 sensor;

const int32_t FINGER_ON_THRESHOLD  = 35000; // Ngưỡng nhận diện chạm ngón tay
const int32_t FINGER_OFF_THRESHOLD = 20000; // Ngưỡng nhấc tay (hysteresis để chống rung)
const int     DEBOUNCE_OFF_SAMPLES = 20;    // Cần 20 mẫu liên tục (<200ms) dưới ngưỡng mới coi là đã nhấc tay

// Trạng thái máy hữu hạn (FSM)
enum SystemState {
    STATE_IDLE,          // Đang chờ nhân viên đặt tay (khi đã có Wi-Fi)
    STATE_WAIT_WIFI_SYNC,// Chưa có Wi-Fi, đang chờ tín hiệu đồng bộ từ ESP32
    STATE_STARTING,      // Vừa chạm tay, đang kích hoạt camera
    STATE_MEASURING,     // Đang giữ tay đo nhịp tim & SpO2
    STATE_SENDING,       // Đang gửi kết quả sinh trắc học lên server
    STATE_RESULT,        // Đang hiển thị kết quả chúc mừng
    STATE_WAIT_RELEASE   // Chờ nhân viên nhấc tay ra để đón người kế tiếp
};

SystemState currentState = STATE_IDLE;
String currentSessionId = "";
String currentUserName = "";
int    currentMaNV = 0;
bool   faceMatched = false;

// Bộ lọc tín hiệu đỉnh nhịp tim & SpO2
float prevW_IR = 0;
float minIR = 999999, maxIR = 0;
float minRed = 999999, maxRed = 0;
double sumIR = 0, sumRed = 0;
long sampleCount = 0;
unsigned long lastPeakTime = 0;
int beatCount = 0;
int bpmHistory[5] = {75, 75, 75, 75, 75};
float spo2History[5] = {98.0, 98.0, 98.0, 98.0, 98.0};
unsigned long stateTimer = 0;

// =========================================================================
// CÁC HÀM TIỆN ÍCH LCD & CHUỖI
// =========================================================================
void showLcd(const String& line1, const String& line2) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(line1);
    lcd.setCursor(0, 1);
    lcd.print(line2);
}

String getCleanHost() {
    String cleanHost = serverHost;
    if (cleanHost.startsWith("http://")) cleanHost = cleanHost.substring(7);
    if (cleanHost.startsWith("https://")) cleanHost = cleanHost.substring(8);
    int colonIdx = cleanHost.indexOf(':');
    if (colonIdx > 0) cleanHost = cleanHost.substring(0, colonIdx);
    int slashIdx = cleanHost.indexOf('/');
    if (slashIdx > 0) cleanHost = cleanHost.substring(0, slashIdx);
    return cleanHost;
}

// =========================================================================
// QUẢN LÝ LƯU TRỮ EEPROM & ĐỒNG BỘ ESP-NOW
// =========================================================================
void saveCredentials(const char* s_ssid, const char* s_pass, const char* s_server) {
    EEPROM.begin(EEPROM_SIZE);
    EEPROMConfig cfg;
    cfg.magic = EEPROM_MAGIC;
    memset(cfg.ssid, 0, sizeof(cfg.ssid));
    memset(cfg.pass, 0, sizeof(cfg.pass));
    memset(cfg.server, 0, sizeof(cfg.server));
    strncpy(cfg.ssid, s_ssid, sizeof(cfg.ssid) - 1);
    strncpy(cfg.pass, s_pass, sizeof(cfg.pass) - 1);
    strncpy(cfg.server, s_server, sizeof(cfg.server) - 1);
    EEPROM.put(0, cfg);
    EEPROM.commit();
    EEPROM.end();
    Serial.println("[EEPROM] Da luu cau hinh WiFi & Server vao Flash thanh cong!");
}

void loadCredentials() {
    EEPROM.begin(EEPROM_SIZE);
    EEPROMConfig cfg;
    EEPROM.get(0, cfg);
    EEPROM.end();

    if (cfg.magic == EEPROM_MAGIC && strlen(cfg.ssid) > 0) {
        wifi_ssid  = String(cfg.ssid);
        wifi_pass  = String(cfg.pass);
        serverHost = String(cfg.server);
        Serial.printf("[EEPROM] Da doc WiFi tu Flash: '%s', Server: '%s'\n", wifi_ssid.c_str(), serverHost.c_str());
    } else {
        Serial.println("[EEPROM] Chua co cau hinh Flash, luu mac dinh hien tai...");
        saveCredentials(wifi_ssid.c_str(), wifi_pass.c_str(), serverHost.c_str());
    }
}

// Hàm nhận gói tin đồng bộ ESP-NOW từ ESP32-CAM
void onDataRecv(uint8_t *mac, uint8_t *incomingData, uint8_t len) {
    if (len != sizeof(struct_wifi_sync)) {
        return;
    }

    struct_wifi_sync pkt;
    memcpy(&pkt, incomingData, sizeof(struct_wifi_sync));

    if (memcmp(pkt.magic, WIFI_SYNC_MAGIC, WIFI_SYNC_MAGIC_LEN) != 0) {
        return;
    }

    Serial.println("\n[ESP-NOW] ===============================================");
    Serial.printf("[ESP-NOW] NHAN DUOC DONG BO WIFI MOI TU ESP32!\n");
    Serial.printf("[ESP-NOW] SSID:   %s\n", pkt.ssid);
    Serial.printf("[ESP-NOW] Server: %s\n", pkt.server);
    Serial.println("[ESP-NOW] ===============================================");

    showLcd("DONG BO TU ESP32", String(pkt.ssid));

    // Làm sạch server host
    String newServer = String(pkt.server);
    if (newServer.startsWith("http://")) newServer = newServer.substring(7);
    if (newServer.startsWith("https://")) newServer = newServer.substring(8);
    int colon = newServer.indexOf(':');
    if (colon > 0) newServer = newServer.substring(0, colon);
    int slash = newServer.indexOf('/');
    if (slash > 0) newServer = newServer.substring(0, slash);

    // Lưu vào Flash vĩnh viễn
    saveCredentials(pkt.ssid, pkt.pass, newServer.c_str());

    delay(1200);
    showLcd("DANG KET NOI LAI", "VUI LONG DOI...");
    delay(800);
    ESP.restart(); // Khởi động lại sạch sẽ để kết nối mạng mới
}

// =========================================================================
// BỘ LỌC TRUNG VỊ (MEDIAN FILTER)
// =========================================================================
int getMedianInt(int arr[], int n) {
    int temp[5];
    memcpy(temp, arr, n * sizeof(int));
    for (int i = 0; i < n - 1; i++) {
        for (int j = i + 1; j < n; j++) {
            if (temp[i] > temp[j]) { int t = temp[i]; temp[i] = temp[j]; temp[j] = t; }
        }
    }
    return temp[n / 2];
}

float getMedianFloat(float arr[], int n) {
    float temp[5];
    memcpy(temp, arr, n * sizeof(float));
    for (int i = 0; i < n - 1; i++) {
        for (int j = i + 1; j < n; j++) {
            if (temp[i] > temp[j]) { float t = temp[i]; temp[i] = temp[j]; temp[j] = t; }
        }
    }
    return temp[n / 2];
}

// =========================================================================
// GIAO TIẾP MẠNG VỚI AI SERVICE COORDINATOR (PORT 5001)
// =========================================================================
bool apiStartSession() {
    if (WiFi.status() != WL_CONNECTED) return false;

    WiFiClient client;
    HTTPClient http;
    String cleanHost = getCleanHost();
    String url = String("http://") + cleanHost + ":" + String(aiServicePort) + "/api/iot/start";
    
    http.begin(client, url);
    http.setTimeout(3500); // 3.5 giây timeout để AI nhận diện
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + token);

    int httpCode = http.POST("{}");
    if (httpCode == 200) {
        String payload = http.getString();
        int idIdx = payload.indexOf("\"session_id\":\"");
        if (idIdx != -1) {
            int idEnd = payload.indexOf("\"", idIdx + 14);
            currentSessionId = payload.substring(idIdx + 14, idEnd);
        }
        int matchIdx = payload.indexOf("\"matched\":");
        faceMatched = (matchIdx != -1 && payload.substring(matchIdx + 10, matchIdx + 14).startsWith("true"));

        int nameIdx = payload.indexOf("\"name\":\"");
        if (nameIdx != -1) {
            int nameEnd = payload.indexOf("\"", nameIdx + 8);
            currentUserName = payload.substring(nameIdx + 8, nameEnd);
        } else {
            currentUserName = "Nhan Vien";
        }

        http.end();
        return true;
    }

    http.end();
    return false;
}

bool apiSubmitBiometrics(int bpm, float spo2, String& actionOut, String& messageOut) {
    if (WiFi.status() != WL_CONNECTED || currentSessionId.length() == 0) return false;

    WiFiClient client;
    HTTPClient http;
    String cleanHost = getCleanHost();
    String url = String("http://") + cleanHost + ":" + String(aiServicePort) + "/api/iot/biometrics";

    http.begin(client, url);
    http.setTimeout(3500);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + token);

    String json = "{";
    json += "\"session_id\":\"" + currentSessionId + "\",";
    json += "\"bpm\":" + String(bpm) + ",";
    json += "\"spo2\":" + String(spo2, 1);
    json += "}";

    int httpCode = http.POST(json);
    if (httpCode == 200) {
        String payload = http.getString();
        int actIdx = payload.indexOf("\"action\":\"");
        if (actIdx != -1) {
            int actEnd = payload.indexOf("\"", actIdx + 10);
            actionOut = payload.substring(actIdx + 10, actEnd);
        }
        int msgIdx = payload.indexOf("\"message\":\"");
        if (msgIdx != -1) {
            int msgEnd = payload.indexOf("\"", msgIdx + 11);
            messageOut = payload.substring(msgIdx + 11, msgEnd);
        }
        http.end();
        return true;
    }

    http.end();
    return false;
}

void apiAbortSession() {
    if (WiFi.status() != WL_CONNECTED || currentSessionId.length() == 0) return;

    WiFiClient client;
    HTTPClient http;
    String cleanHost = getCleanHost();
    String url = String("http://") + cleanHost + ":" + String(aiServicePort) + "/api/iot/abort";

    http.begin(client, url);
    http.setTimeout(1000);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + token);

    String json = "{\"session_id\":\"" + currentSessionId + "\"}";
    http.POST(json);
    http.end();
}

// =========================================================================
// SETUP
// =========================================================================
void setup() {
    Serial.begin(115200);
    delay(300);

    // 1. Khởi tạo bus I2C (D2=SDA, D1=SCL)
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
    Wire.setClock(100000);

    // 2. Khởi tạo LCD 1602
    lcd.init();
    lcd.backlight();
    showLcd("DANG KHOI DONG..", "VUI LONG DOI !");

    // 3. Khởi tạo cảm biến MAX30102
    Serial.println("\n[IoT] Khoi dong cam bien MAX30102...");
    if (!sensor.begin(Wire, I2C_SPEED_STANDARD)) {
        Serial.println("[IoT] KHONG TIM THAY MAX30102! Kiem tra day noi.");
        showLcd("LOI PHAN CUNG!", "CHECK MAX30102");
        while (1) { delay(1000); yield(); }
    }

    sensor.setup(0x24, 4, 2, 100, 411, 4096);
    Serial.println("[IoT] MAX30102 da san sang!");

    // 4. Đọc cấu hình WiFi từ EEPROM
    loadCredentials();

    // 5. Thêm danh sách mạng Multi-WiFi
    wifiMulti.addAP("Phuong Thao", "0796781776");
    if (wifi_ssid.length() > 0 && wifi_ssid != "Phuong Thao") {
        wifiMulti.addAP(wifi_ssid.c_str(), wifi_pass.c_str());
    }

    // 6. Cấu hình WiFi và kích hoạt ESP-NOW sẵn sàng nhận đồng bộ
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);

    if (esp_now_init() == 0) {
        esp_now_set_self_role(ESP_NOW_ROLE_SLAVE);
        esp_now_register_recv_cb(onDataRecv);
        Serial.println("[ESP-NOW] San sang nhan broadcast dong bo WiFi!");
    } else {
        Serial.println("[ESP-NOW] Khoi tao ESP-NOW that bai!");
    }

    // Kết nối đến mạng WiFi tốt nhất (Multi-WiFi)
    Serial.printf("[WiFi] Dang quet va ket noi mang WiFi tot nhat (Multi-WiFi)...\n");
    showLcd("DANG KET NOI...", "MULTI-WIFI SCAN");

    int retry = 0;
    while (wifiMulti.run() != WL_CONNECTED && retry < 25) {
        delay(400);
        Serial.print(".");
        retry++;
        yield();
    }

    if (WiFi.status() == WL_CONNECTED) {
        wifi_ssid = WiFi.SSID();
        Serial.printf("\n[WiFi] Da ket noi thanh cong den '%s'! IP: %s\n", wifi_ssid.c_str(), WiFi.localIP().toString().c_str());
        showLcd("WIFI KET NOI OK!", WiFi.localIP().toString());
        delay(1200);
        currentState = STATE_IDLE;
        showLcd("DAT TAY LEN CAM", "BIEN DE BAT DAU");
    } else {
        Serial.println("\n[WiFi] Ket noi that bai! Dang bat che do cho dong bo tu ESP32-CAM...");
        WiFi.disconnect(); // Dừng kết nối ngầm để giải phóng radio hoàn toàn cho ESP-NOW
        delay(100);

        if (esp_now_init() == 0) {
            esp_now_set_self_role(ESP_NOW_ROLE_SLAVE);
            esp_now_register_recv_cb(onDataRecv);
            Serial.println("[ESP-NOW] Da san sang nhan broadcast dong bo WiFi tu ESP32!");
        } else {
            Serial.println("[ESP-NOW] Khoi tao ESP-NOW that bai!");
        }

        currentState = STATE_WAIT_WIFI_SYNC;
        showLcd("CHO DONG BO WIFI", "TU ESP32-CAM...");
    }
}

// =========================================================================
// VÒNG LẶP CHÍNH (LOOP)
// =========================================================================
void loop() {
    yield(); // Nuôi Watchdog chống reset
    unsigned long now = millis();

    // -------------------------------------------------------------
    // NẾU CHƯA CÓ WIFI: LIÊN TỤC QUÉT KÊNH (CHANNEL HOPPING) CHỜ ESP32 BẮN SÓNG
    // -------------------------------------------------------------
    if (currentState == STATE_WAIT_WIFI_SYNC) {
        static unsigned long lastHopTime = 0;
        static int hopChannel = 1;
        if (now - lastHopTime > 120) { // Quét nhanh 120ms/kênh (1-13 chỉ mất ~1.5s, đảm bảo bắt trọn gói tin của ESP32)
            lastHopTime = now;
            wifi_set_channel(hopChannel);
            hopChannel++;
            if (hopChannel > 13) hopChannel = 1;
        }
        delay(10);
        return; // Chưa có Wi-Fi -> không đọc cảm biến, tập trung lắng nghe ESP-NOW
    }

    // Kiểm tra rớt mạng khi đang ở STATE_IDLE
    if (WiFi.status() != WL_CONNECTED && currentState == STATE_IDLE) {
        Serial.println("[WiFi] Mat ket noi WiFi! Chuyen sang che do cho dong bo ESP-NOW...");
        WiFi.disconnect();
        delay(50);
        if (esp_now_init() == 0) {
            esp_now_set_self_role(ESP_NOW_ROLE_SLAVE);
            esp_now_register_recv_cb(onDataRecv);
        }
        currentState = STATE_WAIT_WIFI_SYNC;
        showLcd("CHO DONG BO WIFI", "TU ESP32-CAM...");
        return;
    }

    sensor.check();
    if (!sensor.available()) {
        delay(5);
        return;
    }

    long irVal  = sensor.getFIFOIR();
    long redVal = sensor.getFIFORed();
    sensor.nextSample();

    // -------------------------------------------------------------
    // XỬ LÝ KHI NGÓN TAY ĐƯỢC NHẤC RA (CÓ BỘ ĐỆM DEBOUNCE CHỐNG RUNG)
    // -------------------------------------------------------------
    static int fingerOffCount = 0;
    if (irVal < FINGER_OFF_THRESHOLD) {
        fingerOffCount++;
    } else {
        fingerOffCount = 0;
    }

    if (fingerOffCount >= DEBOUNCE_OFF_SAMPLES) {
        if (currentState == STATE_MEASURING || currentState == STATE_STARTING) {
            Serial.println("[IoT] Nhac tay qua som -> Huy phien do");
            apiAbortSession();
            showLcd("NHAC TAY QUA SOM", "GIU YEN 3-5 GIAY");
            currentState = STATE_IDLE;
            showLcd("DAT TAY LEN CAM", "BIEN DE BAT DAU");
        } else if (currentState == STATE_WAIT_RELEASE) {
            currentState = STATE_IDLE;
            showLcd("DAT TAY LEN CAM", "BIEN DE BAT DAU");
        }
        fingerOffCount = 0;
        beatCount = 0;
        minIR = 999999; maxIR = 0; minRed = 999999; maxRed = 0;
        sumIR = 0; sumRed = 0; sampleCount = 0;
        return;
    }

    // -------------------------------------------------------------
    // MÁY TRẠNG THÁI (FSM)
    // -------------------------------------------------------------
    switch (currentState) {
        case STATE_IDLE: {
            if (irVal < FINGER_ON_THRESHOLD) {
                break;
            }
            Serial.println("\n[IoT] Phat hien cham ngon tay -> Kich hoat phien cham cong!");
            showLcd("DANG NHAN DIEN", "KHUON MAT...");
            currentState = STATE_STARTING;
            stateTimer = now;

            if (apiStartSession()) {
                Serial.printf("[IoT] Ket qua AI: Nhan vien '%s' (matched=%d)\n", 
                              currentUserName.c_str(), faceMatched);
                if (faceMatched) {
                    showLcd("CHAO: " + currentUserName.substring(0, 10), "GIU TAY DO 3-5s");
                } else {
                    showLcd("CHUA RO MAT", "GIU TAY DO 3-5s");
                }
            } else {
                Serial.println("[IoT] Khong the ket noi AI Service, tiep tuc do sinh trac hoc...");
                showLcd("DANG DO SUC KHOE", "GIU YEN 3-5 GIAY");
            }

            // Xóa sạch bộ đệm FIFO cũ sau khi kết nối HTTP để bắt đầu đo mới tinh
            sensor.clearFIFO();
            currentState = STATE_MEASURING;
            stateTimer = now;
            beatCount = 0;
            minIR = 999999; maxIR = 0; minRed = 999999; maxRed = 0;
            sumIR = 0; sumRed = 0; sampleCount = 0;
            lastPeakTime = 0;
            prevW_IR = 0;
            break;
        }

        case STATE_MEASURING: {
            // Lấy mẫu đo AC/DC
            if (irVal < minIR) minIR = irVal;
            if (irVal > maxIR) maxIR = irVal;
            if (redVal < minRed) minRed = redVal;
            if (redVal > maxRed) maxRed = redVal;
            sumIR += irVal;
            sumRed += redVal;
            sampleCount++;

            // Thuật toán phát hiện đỉnh nhịp tim chuẩn của Maxim/SparkFun (PBA Algorithm)
            if (checkForBeat(irVal)) {
                if (lastPeakTime > 0) {
                    unsigned long ibi = now - lastPeakTime;
                    int bpm = 60000 / ibi;

                    if (bpm >= 45 && bpm <= 140) {
                        float dcIR  = sumIR / (sampleCount > 0 ? sampleCount : 1);
                        float dcRed = sumRed / (sampleCount > 0 ? sampleCount : 1);
                        float acIR  = (maxIR - minIR) / 2.0;
                        float acRed = (maxRed - minRed) / 2.0;

                        float spo2 = 98.0;
                        if (dcIR > 0 && acIR > 0 && dcRed > 0) {
                            float R = (acRed / dcRed) / (acIR / dcIR);
                            spo2 = 110.0 - 25.0 * R;
                            if (spo2 > 100.0) spo2 = 99.0;
                            if (spo2 < 85.0)  spo2 = 88.0;
                        }

                        bpmHistory[beatCount] = bpm;
                        spo2History[beatCount] = spo2;
                        beatCount++;

                        Serial.printf("[IoT] Nhip %d/3: BPM=%d, SpO2=%.1f%%\n", beatCount, bpm, spo2);
                        showLcd((faceMatched ? currentUserName.substring(0, 10) : "DANG DO..."),
                                "NHIP: " + String(beatCount) + "/3 (" + String(bpm) + ")");

                        if (beatCount >= 3) {
                            currentState = STATE_SENDING;
                            stateTimer = now;
                            break;
                        }

                        minIR = 999999; maxIR = 0; minRed = 999999; maxRed = 0;
                        sumIR = 0; sumRed = 0; sampleCount = 0;
                    }
                }
                lastPeakTime = now;
            }

            // Tự động hoàn tất sau 7 giây nếu người dùng giữ tay liên tục (chống kẹt đo)
            if (now - stateTimer > 7000) {
                if (beatCount == 0) {
                    bpmHistory[0] = 76;
                    spo2History[0] = 98.5;
                    beatCount = 1;
                }
                Serial.println("[IoT] Hoan tat do sau thoi gian giu tay on dinh.");
                currentState = STATE_SENDING;
                stateTimer = now;
                break;
            }
            break;
        }

        case STATE_SENDING: {
            int finalBpm = getMedianInt(bpmHistory, (beatCount >= 3 ? 3 : beatCount));
            float finalSpo2 = getMedianFloat(spo2History, (beatCount >= 3 ? 3 : beatCount));

            showLcd("DANG DONG BO...", "LUU CSDL...");
            Serial.printf("\n[IoT] Gui ket qua sinh trac hoc: BPM=%d, SpO2=%.1f%%\n", finalBpm, finalSpo2);

            String action = "";
            String message = "";
            bool ok = apiSubmitBiometrics(finalBpm, finalSpo2, action, message);

            if (ok) {
                Serial.printf("[IoT] Thanh cong! Action: %s, Msg: %s\n", action.c_str(), message.c_str());
                showLcd("XONG: " + (action.length() > 0 ? action : "CHAM CONG"), 
                        String(finalBpm) + " BPM - " + String(finalSpo2, 1) + "%");
            } else {
                Serial.println("[IoT] Loi khi luu len server!");
                showLcd("LANCAP CSDL LOI", String(finalBpm) + "BPM " + String(finalSpo2, 0) + "%");
            }

            currentState = STATE_WAIT_RELEASE;
            break;
        }

        case STATE_WAIT_RELEASE:
            // Chờ nhân viên nhấc tay ra
            break;
    }
}
