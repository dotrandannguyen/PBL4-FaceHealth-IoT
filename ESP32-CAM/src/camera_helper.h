#ifndef CAMERA_HELPER_H
#define CAMERA_HELPER_H

#include <Arduino.h>
#include "esp_camera.h"
#include "camera_pins.h"

class CameraHelper {
public:
    static bool init(framesize_t frameSize = FRAMESIZE_VGA, int jpegQuality = 12) {
        camera_config_t config;
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
        config.pixel_format = PIXFORMAT_JPEG;
        config.frame_size = frameSize;
        config.jpeg_quality = jpegQuality;
        config.fb_count = 2;
        config.grab_mode = CAMERA_GRAB_LATEST;

        // Kiểm tra PSRAM
        if (psramFound()) {
            Serial.println("[CAM] Tim thay PSRAM. Su dung cau hinh chat luong cao.");
            config.fb_location = CAMERA_FB_IN_PSRAM;
        } else {
            Serial.println("[CAM] CANH BAO: Khong tim thay PSRAM, giam do phan giai xuong SVGA.");
            config.frame_size = FRAMESIZE_SVGA;
            config.fb_location = CAMERA_FB_IN_DRAM;
            config.fb_count = 1;
        }

        esp_err_t err = esp_camera_init(&config);
        if (err != ESP_OK) {
            Serial.printf("[CAM] Khoi tao Camera that bai! Ma loi: 0x%x\n", err);
            return false;
        }

        sensor_t *s = esp_camera_sensor_get();
        if (s != nullptr) {
            s->set_vflip(s, 1);       // Lat anh neu cam nguoc
            s->set_brightness(s, 1);   // Tang sang nhe
            s->set_saturation(s, 0);
        }

        Serial.println("[CAM] Khoi tao Camera OV2640 thanh cong!");
        return true;
    }

    static camera_fb_t* capture() {
        camera_fb_t *fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[CAM] Loi chup anh (fb null)!");
            return nullptr;
        }
        return fb;
    }

    static void release(camera_fb_t *fb) {
        if (fb) {
            esp_camera_fb_return(fb);
        }
    }
};

#endif // CAMERA_HELPER_H
