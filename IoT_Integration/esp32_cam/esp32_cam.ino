#include <Preferences.h>
#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "wifi_config.h"

// ===========================
// Select camera model in board_config.h
// ===========================
#include "board_config.h"

// ===========================
// Enter your WiFi credentials
// ===========================
const char* ssid = PBL4_WIFI_SSID;
const char* password = PBL4_WIFI_PASSWORD;

// Thay bang IPv4 cua may tinh
const char* serverUrl = PBL4_UPLOAD_URL;

void startCameraServer();
void setupLedFlash();
static bool cameraReady = false;
static bool cameraServerStarted = false;
static unsigned long lastReconnectAttempt = 0;


void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;  // for streaming
  //config.pixel_format = PIXFORMAT_RGB565; // for face detection/recognition
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  // if PSRAM IC present, init with UXGA resolution and higher JPEG quality
  //                      for larger pre-allocated frame buffer.
  if (config.pixel_format == PIXFORMAT_JPEG) {
    if (psramFound()) {
      config.jpeg_quality = 10;
      config.fb_count = 2;
      config.grab_mode = CAMERA_GRAB_LATEST;
    } else {
      // Limit the frame size when PSRAM is not available
      config.frame_size = FRAMESIZE_SVGA;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }
  } else {
    // Best option for face detection/recognition
    config.frame_size = FRAMESIZE_240X240;
#if CONFIG_IDF_TARGET_ESP32S3
    config.fb_count = 2;
#endif
  }

#if defined(CAMERA_MODEL_ESP_EYE)
  pinMode(13, INPUT_PULLUP);
  pinMode(14, INPUT_PULLUP);
#endif

  // camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  cameraReady = true;
  sensor_t *s = esp_camera_sensor_get();
  // initial sensors are flipped vertically and colors are a bit saturated
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);        // flip it back
    s->set_brightness(s, 1);   // up the brightness just a bit
    s->set_saturation(s, -2);  // lower the saturation
  }
  // drop down frame size for higher initial frame rate
  if (config.pixel_format == PIXFORMAT_JPEG) {
    Preferences prefs;

    prefs.begin("camera", true);
    int savedFrameSize = prefs.getInt("framesize", FRAMESIZE_VGA);
    prefs.end();

    s->set_framesize(s, (framesize_t)savedFrameSize);
  }

#if defined(CAMERA_MODEL_M5STACK_WIDE) || defined(CAMERA_MODEL_M5STACK_ESP32CAM)
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
#endif

#if defined(CAMERA_MODEL_ESP32S3_EYE)
  s->set_vflip(s, 1);
#endif

// Setup LED FLash if LED pin is defined in camera_pins.h
#if defined(LED_GPIO_NUM)
  setupLedFlash();
#endif

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  Serial.print("WiFi connecting");
  unsigned long connectStarted = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - connectStarted < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not ready; reconnect will be retried.");
    return;
  }
  Serial.println("WiFi connected");
  startCameraServer();
  cameraServerStarted = true;

  Serial.print("Camera Ready! Use 'http://");
  Serial.print(WiFi.localIP());
  Serial.println("' to connect");
}


void guiAnhLenServer() {
  if (!cameraReady || WiFi.status() != WL_CONNECTED) return;
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb == nullptr) {
    Serial.println("Camera capture failed");
    return;
  }
  struct FrameGuard {
    camera_fb_t *frame;
    ~FrameGuard() { esp_camera_fb_return(frame); }
  } frameGuard{fb};
  if (fb->format != PIXFORMAT_JPEG || fb->len == 0 || fb->len > 5U * 1024U * 1024U) {
    Serial.println("Invalid JPEG frame size/format");
    return;
  }
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(5000);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  if (!http.begin(client, serverUrl)) {
    Serial.println("Upload connection failed");
    return;
  }
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("Authorization", String("Bearer ") + PBL4_UPLOAD_TOKEN);
  int code = http.POST(fb->buf, fb->len);
  Serial.printf("JPEG upload HTTP status: %d\n", code);
  http.end();
}

void loop() {
  if (!cameraReady) {
    delay(1000);
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastReconnectAttempt >= 10000) {
      lastReconnectAttempt = millis();
      WiFi.reconnect();
    }
    delay(100);
    return;
  }
  if (!cameraServerStarted) {
    startCameraServer();
    cameraServerStarted = true;
  }
  guiAnhLenServer();
  delay(10000);
}
