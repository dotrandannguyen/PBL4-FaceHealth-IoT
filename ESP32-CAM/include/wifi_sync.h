#ifndef WIFI_SYNC_H
#define WIFI_SYNC_H

#include <Arduino.h>

#define WIFI_SYNC_MAGIC "PBL4"
#define WIFI_SYNC_MAGIC_LEN 4

// Định dạng gói tin đồng bộ Wi-Fi qua sóng ESP-NOW (đóng gói chặt byte __attribute__((packed)))
typedef struct __attribute__((packed)) struct_wifi_sync {
    char magic[4];     // "PBL4"
    char ssid[33];     // Tên WiFi (tối đa 32 ký tự + null)
    char pass[65];     // Mật khẩu WiFi (tối đa 64 ký tự + null)
    char server[65];   // IP máy chủ Flask/Backend (tối đa 64 ký tự + null)
} struct_wifi_sync;

#endif // WIFI_SYNC_H
