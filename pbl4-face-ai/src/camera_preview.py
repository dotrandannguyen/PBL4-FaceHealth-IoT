"""
camera_preview.py — Xem Trực Tiếp Video Stream Camera On-Demand (ESP32-CAM / Webcam).
"""

import sys
import os
import time
import argparse
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import cv2
from src.camera_source import CameraSource


def main():
    parser = argparse.ArgumentParser(description="Xem Truc Tiep Camera")
    parser.add_argument("--camera", type=str, default="esp32", help="Camera source ('0', '1', hoac 'esp32')")
    args = parser.parse_args()

    source_label = "ESP32-CAM (WiFi Node 1)" if args.camera == "esp32" else f"Webcam (Index {args.camera})"
    print(f"\n========================================================")
    print(f"🎥 XEM TRỰC TIẾP CAMERA: {source_label}")
    print(f"👉 Bấm [Q] hoặc [ESC] để Đóng cửa sổ và Dừng Stream")
    print(f"========================================================\n")

    cap = CameraSource(source=args.camera, width=640, height=480)
    prev_time = time.time()
    fps = 0.0

    window_name = f"PBL4 - Xem Truc Tiep [{source_label}] - Bam Q de Thoat"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.02)
                continue

            curr_time = time.time()
            fps = 0.85 * fps + 0.15 * (1.0 / max(curr_time - prev_time, 1e-5))
            prev_time = curr_time

            h, w = frame.shape[:2]
            vis = frame.copy()

            # Thanh thông tin trên đầu
            cv2.rectangle(vis, (0, 0), (w, 38), (15, 20, 28), -1)
            cv2.putText(
                vis,
                f"{source_label} | {w}x{h} | FPS: {fps:.1f}",
                (12, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 230, 120),
                2,
            )

            # Hướng dẫn góc dưới
            cv2.rectangle(vis, (0, h - 28), (w, h), (15, 20, 28), -1)
            cv2.putText(
                vis,
                "Bam [Q] hoac [ESC] de Tat camera & ve che do Standby",
                (12, h - 9),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (180, 180, 180),
                1,
            )

            cv2.imshow(window_name, vis)
            key = cv2.waitKey(1) & 0xFF
            if key in [ord("q"), ord("Q"), 27]:
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("[Preview] Đã đóng cửa sổ xem trực tiếp. Camera đã tắt và về trạng thái nghỉ.")


if __name__ == "__main__":
    main()
