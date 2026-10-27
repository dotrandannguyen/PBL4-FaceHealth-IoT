#include <Wire.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"

MAX30105 sensor;

const char* ssid = "Bao Khanh";
const char* password = "dua500kdi";

const char* serverUrl =
  "http://192.168.100.176/DoAn_ChamCong_AI/api/device/health-test";

const int MA_NV = 1;

const int DATA_BUFFER_SIZE = 100;
const int SAMPLE_COUNT = 3;

const uint32_t FINGER_THRESHOLD = 30000;

const int BPM_MIN = 40;
const int BPM_MAX = 180;

const int SPO2_MIN = 85;
const int SPO2_MAX = 100;

uint32_t irBuffer[DATA_BUFFER_SIZE];
uint32_t redBuffer[DATA_BUFFER_SIZE];

int32_t heartRate = 0;
int8_t validHeartRate = 0;

int32_t spo2 = 0;
int8_t validSpO2 = 0;

int bpmSamples[SAMPLE_COUNT];
int spo2Samples[SAMPLE_COUNT];

int sampleIndex = 0;
int invalidCount = 0;

bool fingerActive = false;
bool sent = false;


// Kết nối WiFi
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED)
    return;

  Serial.print("Dang ket noi WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int retry = 0;

  while (WiFi.status() != WL_CONNECTED && retry < 30) {
    delay(500);
    Serial.print(".");
    retry++;
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WIFI CONNECTED");

    Serial.print("ESP8266 IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WIFI FAILED");
  }
}


// Gửi dữ liệu lên PHP
bool sendHealth(int bpm, int oxygen) {
  connectWiFi();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("KHONG CO WIFI");
    return false;
  }

  WiFiClient client;
  HTTPClient http;

  http.begin(client, serverUrl);
  http.addHeader("Content-Type", "application/json");

  String json =
    "{\"ma_nv\":" + String(MA_NV) +
    ",\"nhip_tim\":" + String(bpm) +
    ",\"spo2\":" + String(oxygen) +
    "}";

  Serial.println();
  Serial.println("GUI LEN SERVER");
  Serial.println(json);

  int httpCode = http.POST(json);

  Serial.print("HTTP CODE: ");
  Serial.println(httpCode);

  if (httpCode > 0) {
    Serial.print("SERVER: ");
    Serial.println(http.getString());
  }

  http.end();

  if (httpCode == 200) {
    Serial.println(">>> DA LUU VAO MARIADB");
    return true;
  }

  Serial.println(">>> GUI THAT BAI");
  return false;
}


void readSample(uint32_t &red, uint32_t &ir) {
  while (!sensor.available()) {
    sensor.check();
    yield();
  }

  red = sensor.getRed();
  ir = sensor.getIR();

  sensor.nextSample();
}


void fillBuffer() {
  Serial.println("Dang lay mau...");

  for (int i = 0; i < DATA_BUFFER_SIZE; i++) {
    readSample(redBuffer[i], irBuffer[i]);
  }
}


void resetMeasurement() {
  sampleIndex = 0;
  invalidCount = 0;
  fingerActive = false;
  sent = false;
}


// Lấy trung vị 3 số
int median3(int a, int b, int c) {
  if (a > b) {
    int t = a;
    a = b;
    b = t;
  }

  if (b > c) {
    int t = b;
    b = c;
    c = t;
  }

  if (a > b) {
    int t = a;
    a = b;
    b = t;
  }

  return b;
}


void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("MAX30102 FAST MODE");

  // SDA=D2, SCL=D1
  Wire.begin(D2, D1);

  if (!sensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("KHONG TIM THAY MAX30102");

    while (1) {
      delay(1000);
    }
  }

  Serial.println("MAX30102 OK");

  sensor.setup(
    60,
    4,
    2,
    100,
    411,
    4096
  );

  connectWiFi();

  resetMeasurement();
  fillBuffer();

  Serial.println("DAT NGON TAY LEN CAM BIEN");
}


void loop() {
  for (int i = 25; i < DATA_BUFFER_SIZE; i++) {
    redBuffer[i - 25] = redBuffer[i];
    irBuffer[i - 25] = irBuffer[i];
  }

  for (int i = 75; i < DATA_BUFFER_SIZE; i++) {
    readSample(redBuffer[i], irBuffer[i]);
  }

  uint32_t currentIR =
    irBuffer[DATA_BUFFER_SIZE - 1];

  Serial.println("----------------------");

  Serial.print("IR: ");
  Serial.println(currentIR);


  if (currentIR < FINGER_THRESHOLD) {
    Serial.println("CHUA DAT NGON TAY");

    if (fingerActive || sent || sampleIndex > 0) {
      resetMeasurement();
      Serial.println("SAN SANG DO LAN MOI");
    }

    delay(200);
    return;
  }


  if (!fingerActive) {
    fingerActive = true;

    Serial.println("DA PHAT HIEN NGON TAY");
    Serial.println("GIU YEN NGON TAY");

    fillBuffer();

    delay(200);
    return;
  }


  if (sent) {
    Serial.println("DA LUU - NHAC NGON TAY RA");

    delay(400);
    return;
  }


  maxim_heart_rate_and_oxygen_saturation(
    irBuffer,
    DATA_BUFFER_SIZE,
    redBuffer,
    &spo2,
    &validSpO2,
    &heartRate,
    &validHeartRate
  );


  Serial.print("BPM: ");
  Serial.print(heartRate);

  Serial.print(" | SpO2: ");
  Serial.print(spo2);

  Serial.println("%");


  bool bpmOK =
    heartRate >= BPM_MIN &&
    heartRate <= BPM_MAX;

  bool spo2OK =
    spo2 >= SPO2_MIN &&
    spo2 <= SPO2_MAX;


  if (!bpmOK || !spo2OK) {
    invalidCount++;

    Serial.print("THU LAI: ");
    Serial.println(invalidCount);

    if (invalidCount >= 6) {
      Serial.println("LAM MOI DU LIEU");

      fillBuffer();

      invalidCount = 0;
      sampleIndex = 0;
    }

    delay(200);
    return;
  }


  invalidCount = 0;

  bpmSamples[sampleIndex] = heartRate;
  spo2Samples[sampleIndex] = spo2;

  sampleIndex++;

  Serial.print("MAU TOT: ");
  Serial.print(sampleIndex);
  Serial.print("/");
  Serial.println(SAMPLE_COUNT);


  if (sampleIndex >= SAMPLE_COUNT) {
    int finalBpm = median3(
      bpmSamples[0],
      bpmSamples[1],
      bpmSamples[2]
    );

    int finalSpO2 = median3(
      spo2Samples[0],
      spo2Samples[1],
      spo2Samples[2]
    );

    Serial.println();
    Serial.println("***** KET QUA *****");

    Serial.print("Nhip tim: ");
    Serial.print(finalBpm);
    Serial.println(" BPM");

    Serial.print("SpO2: ");
    Serial.print(finalSpO2);
    Serial.println("%");


    if (sendHealth(finalBpm, finalSpO2)) {
      sent = true;
    } else {
      sampleIndex = 0;
    }
  }

  delay(200);
}