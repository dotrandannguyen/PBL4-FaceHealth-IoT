#ifndef HTTP_HELPER_H
#define HTTP_HELPER_H

#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"

class HttpHelper {
public:
    static bool sendMultipart(
        const char* host,
        uint16_t port,
        const char* path,
        camera_fb_t* fb,
        const String& extraFieldsJson,
        String& responseBody,
        uint32_t timeoutMs = 8000
    ) {
        WiFiClient client;
        client.setTimeout(timeoutMs / 1000);

        if (!client.connect(host, port)) {
            Serial.printf("[HTTP] Khong the ket noi den Server: %s:%d\n", host, port);
            return false;
        }

        String boundary = "----ESP32CamBoundary" + String(millis());
        String head = "--" + boundary + "\r\n";
        
        // Thêm trường dữ liệu cảm biến / metadata nếu có
        if (extraFieldsJson.length() > 0) {
            head += "Content-Disposition: form-data; name=\"metadata\"\r\n";
            head += "Content-Type: application/json\r\n\r\n";
            head += extraFieldsJson + "\r\n";
            head += "--" + boundary + "\r\n";
        }

        // Trường file ảnh JPEG
        head += "Content-Disposition: form-data; name=\"image\"; filename=\"capture.jpg\"\r\n";
        head += "Content-Type: image/jpeg\r\n\r\n";

        String tail = "\r\n--" + boundary + "--\r\n";

        size_t totalLen = head.length() + fb->len + tail.length();

        // Gửi HTTP Request Header
        client.printf("POST %s HTTP/1.1\r\n", path);
        client.printf("Host: %s:%d\r\n", host, port);
        client.println("Connection: close");
        client.println("Content-Type: multipart/form-data; boundary=" + boundary);
        client.printf("Content-Length: %u\r\n\r\n", totalLen);

        // Gửi phần đầu Multipart
        client.print(head);

        // Gửi từng chunk ảnh trực tiếp từ bộ đệm PSRAM
        uint8_t *fbBuf = fb->buf;
        size_t fbLen = fb->len;
        const size_t chunkSize = 1024;
        for (size_t n = 0; n < fbLen; n += chunkSize) {
            size_t toWrite = (fbLen - n < chunkSize) ? (fbLen - n) : chunkSize;
            client.write(fbBuf + n, toWrite);
        }

        // Gửi phần kết Multipart
        client.print(tail);

        // Đọc phản hồi từ Server
        uint32_t startWait = millis();
        while (client.connected() && millis() - startWait < timeoutMs) {
            if (client.available()) {
                String line = client.readStringUntil('\n');
                if (line == "\r") {
                    // Đã đọc hết Header, phần sau là Body (JSON)
                    break;
                }
            }
            delay(5);
        }

        responseBody = "";
        while (client.available()) {
            responseBody += (char)client.read();
        }

        client.stop();
        return (responseBody.length() > 0);
    }
};

#endif // HTTP_HELPER_H
