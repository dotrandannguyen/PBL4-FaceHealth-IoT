"""
demo_webcam.py — Demo nhận diện khuôn mặt real-time qua webcam
Hiện bbox, landmarks, embedding info, FPS lên màn hình
"""

import sys
import os
import time

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import cv2
import numpy as np
from src.face_engine import FaceEngine


def main():
    print("Dang khoi tao InsightFace...")
    engine = FaceEngine()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Khong mo duoc webcam!")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("=== WEBCAM DEMO ===")
    print("Nhan Q de thoat")

    prev_time = time.time()
    fps = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Tính FPS
        curr_time = time.time()
        fps = 1.0 / max(curr_time - prev_time, 0.001)
        prev_time = curr_time

        # Detect faces
        faces = engine.detect(frame)

        # Vẽ kết quả
        vis = frame.copy()

        for i, face in enumerate(faces):
            x1, y1, x2, y2 = [int(v) for v in face.bbox]
            score = face.det_score

            # Màu gradient theo confidence
            green = int(score * 255)
            color = (0, green, 255 - green)

            # Bbox
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

            # Landmarks (5 điểm)
            if face.kps is not None:
                for j, kp in enumerate(face.kps):
                    colors_kp = [(0, 255, 0), (0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)]
                    cv2.circle(vis, (int(kp[0]), int(kp[1])), 3, colors_kp[j], -1)

            # Info text
            emb_text = ""
            if face.embedding is not None:
                norm = np.linalg.norm(face.embedding)
                emb_text = f" | Emb: 512d, norm={norm:.1f}"

            label = f"Face {i+1}: {score:.2f}{emb_text}"

            # Background cho text
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(vis, (x1, y1 - th - 10), (x1 + tw + 4, y1), color, -1)
            cv2.putText(vis, label, (x1 + 2, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Kích thước mặt
            w_face = x2 - x1
            h_face = y2 - y1
            size_text = f"{w_face}x{h_face}px"
            cv2.putText(vis, size_text, (x1, y2 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        # HUD - thông tin góc trên
        hud_bg = vis.copy()
        cv2.rectangle(hud_bg, (0, 0), (380, 80), (0, 0, 0), -1)
        vis = cv2.addWeighted(hud_bg, 0.5, vis, 1.0, 0)

        cv2.putText(vis, f"PBL4 Face Detection | FPS: {fps:.1f}",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
        cv2.putText(vis, f"Model: buffalo_sc | Faces: {len(faces)}",
                    (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(vis, "Q = Thoat",
                    (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 255), 1)

        cv2.imshow("PBL4 - Face Detection Demo", vis)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Da dong webcam.")


if __name__ == "__main__":
    main()
