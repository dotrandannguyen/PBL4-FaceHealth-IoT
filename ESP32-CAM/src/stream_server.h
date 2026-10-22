#ifndef STREAM_SERVER_H
#define STREAM_SERVER_H

#include <Arduino.h>
#include "esp_http_server.h"
#include "esp_camera.h"
#include "config.h"

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static httpd_handle_t stream_httpd = NULL;
static bool is_streaming_active = false;

// -------------------------------------------------------------------------
// 1. HANDLER PHÁT LUỒNG VIDEO MJPEG (ON-DEMAND)
// -------------------------------------------------------------------------
static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t *_jpg_buf = NULL;
    char part_buf[64];

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        return res;
    }
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    is_streaming_active = true;
    digitalWrite(INDICATOR_LED_PIN, LOW); // BẬT ĐÈN LED ĐỎ BÁO ĐANG STREAM
    Serial.printf("[STREAM] >>> Client da ket noi! Bat camera stream (Core %d)...\n", xPortGetCoreID());

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[STREAM] Loi: fb null tu camera!");
            res = ESP_FAIL;
            break;
        }

        _jpg_buf_len = fb->len;
        _jpg_buf = fb->buf;

        if (res == ESP_OK) {
            size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
            res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
        }

        esp_camera_fb_return(fb);
        fb = NULL;

        // Nếu client ngắt kết nối (tắt cửa sổ), res sẽ khác ESP_OK -> THOÁT NGAY!
        if (res != ESP_OK) {
            break;
        }

        // Nhường CPU 15ms (~25 FPS mượt mà)
        vTaskDelay(pdMS_TO_TICKS(15));
    }

    is_streaming_active = false;
    digitalWrite(INDICATOR_LED_PIN, HIGH); // TẮT ĐÈN LED ĐỎ BÁO CAMERA NGHỈ
    Serial.println("[STREAM] <<< Client da ngat ket noi! Tat stream, camera tro ve nghi (Standby).");
    return res;
}

// -------------------------------------------------------------------------
// 2. HANDLER CHỤP ẢNH SNAPSHOT ĐƠN LẺ
// -------------------------------------------------------------------------
static esp_err_t capture_handler(httpd_req_t *req) {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;

    digitalWrite(INDICATOR_LED_PIN, LOW);
    fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("[CAM] Loi chup anh (fb null)!");
        digitalWrite(INDICATOR_LED_PIN, HIGH);
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    res = httpd_resp_send(req, (const char *)fb->buf, fb->len);

    esp_camera_fb_return(fb);
    digitalWrite(INDICATOR_LED_PIN, HIGH);
    Serial.printf("[CAM] Da phuc vu anh Snapshot: %u bytes\n", fb ? fb->len : 0);
    return res;
}

// -------------------------------------------------------------------------
// 3. HANDLER TRẠNG THÁI CAMERA
// -------------------------------------------------------------------------
static esp_err_t status_handler(httpd_req_t *req) {
    char json_response[160];
    snprintf(
        json_response,
        sizeof(json_response),
        "{\"status\":\"online\",\"streaming\":%s,\"psram\":%s,\"uptime_sec\":%lu}",
        is_streaming_active ? "true" : "false",
        psramFound() ? "true" : "false",
        millis() / 1000
    );
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    return httpd_resp_send(req, json_response, strlen(json_response));
}

// -------------------------------------------------------------------------
// 4. KHỞI TẠO HTTP SERVER CỔNG 81
// -------------------------------------------------------------------------
inline bool startCameraServer(uint16_t port = STREAM_SERVER_PORT) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = port;
    config.ctrl_port = port + 10;
    config.max_open_sockets = 4;
    config.lru_purge_enable = true;

    httpd_uri_t stream_uri = {
        .uri       = "/stream",
        .method    = HTTP_GET,
        .handler   = stream_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t capture_uri = {
        .uri       = "/capture",
        .method    = HTTP_GET,
        .handler   = capture_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t status_uri = {
        .uri       = "/status",
        .method    = HTTP_GET,
        .handler   = status_handler,
        .user_ctx  = NULL
    };

    Serial.printf("[SERVER] Dang khoi tao Camera Stream Server tren cong %d...\n", port);
    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        httpd_register_uri_handler(stream_httpd, &capture_uri);
        httpd_register_uri_handler(stream_httpd, &status_uri);
        Serial.printf("[SERVER] ✅ Stream Server san sang! Endpoint: http://<IP>:%d/stream\n", port);
        return true;
    }

    Serial.println("[SERVER] ❌ Khoi dong Stream Server that bai!");
    return false;
}

#endif // STREAM_SERVER_H
