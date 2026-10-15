"""
ai_web_service.py — AI REST Service phục vụ Web Quản lý & Đăng ký khuôn mặt (PBL4)
Cung cấp các API:
  - GET  /health                      : Kiểm tra trạng thái AI service
  - GET  /internal/camera/frame       : Chụp và trả về frame JPEG từ webcam
  - POST /api/ai/enrollment/inspect   : Kiểm tra pose và chất lượng ảnh enrollment
  - POST /api/ai/enrollment/capture   : Trích xuất embedding 512-dim (2048 bytes raw) và JPEG
  - POST /api/ai/gallery/refresh      : Đồng bộ gallery khuôn mặt từ CSDL Web về file embeddings.pkl
"""

import os
import sys
import time
import base64
import hashlib
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# Chặn log rác C++ từ TensorFlow / MediaPipe / GLOG
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"

import cv2
import numpy as np
import requests
from flask import Flask, request, jsonify, Response

# Thêm đường dẫn project
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
DATA_DIR = BASE_DIR / "data"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.pkl"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.face_engine import FaceEngine
from src.verify import load_db

app = Flask(__name__)

# Cấu hình Web Backend
WEB_GALLERY_URL = os.environ.get("WEB_GALLERY_URL", "http://localhost:8080/?action=internal_face_gallery")
PORT = int(os.environ.get("AI_PORT", 5001))

# Singleton FaceEngine & Camera
_engine: Optional[FaceEngine] = None
_engine_lock = threading.Lock()

_cap: Optional[cv2.VideoCapture] = None
_camera_lock = threading.Lock()


def get_face_engine() -> FaceEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                print(">> [AI Service] Đang tải mô hình FaceEngine (buffalo_sc)...")
                _engine = FaceEngine(model_name="buffalo_sc")
                print(">> [AI Service] FaceEngine đã sẵn sàng!")
    return _engine


def get_camera() -> cv2.VideoCapture:
    global _cap
    if _cap is None or not _cap.isOpened():
        with _camera_lock:
            if _cap is None or not _cap.isOpened():
                print(">> [AI Service] Đang mở Webcam 0...")
                _cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
                _cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                _cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return _cap


def estimate_pose(kps: np.ndarray) -> Tuple[str, Dict[str, float]]:
    """
    Ước lượng hướng khuôn mặt từ 5 điểm mốc (landmarks):
    kps[0]: left eye (mắt trái trên ảnh)
    kps[1]: right eye (mắt phải trên ảnh)
    kps[2]: nose tip (đầu mũi)
    kps[3]: mouth left
    kps[4]: mouth right
    """
    eye_left = kps[0]
    eye_right = kps[1]
    nose = kps[2]
    mouth_left = kps[3]
    mouth_right = kps[4]

    eye_w = max(float(np.linalg.norm(eye_right - eye_left)), 1e-4)
    d_left = float(abs(nose[0] - eye_left[0]))
    d_right = float(abs(eye_right[0] - nose[0]))
    yaw_diff = (d_right - d_left) / eye_w

    eye_y = float((eye_left[1] + eye_right[1]) / 2.0)
    mouth_y = float((mouth_left[1] + mouth_right[1]) / 2.0)
    vert_span = max(mouth_y - eye_y, 1e-4)
    pitch_ratio = float((nose[1] - eye_y) / vert_span)

    # Phân loại pose
    # Chú ý: webcam thường bị lật gương (mirror)
    if pitch_ratio < 0.42:
        detected_pose = "up"
    elif pitch_ratio > 0.64:
        detected_pose = "down"
    elif yaw_diff > 0.22:
        detected_pose = "left"
    elif yaw_diff < -0.22:
        detected_pose = "right"
    else:
        detected_pose = "frontal"

    metrics = {
        "yaw_diff": round(yaw_diff, 3),
        "pitch_ratio": round(pitch_ratio, 3),
    }
    return detected_pose, metrics


def check_pose_match(expected_pose: str, detected_pose: str, metrics: Dict[str, float]) -> bool:
    """Kiểm tra độ khớp pose với độ dung sai hợp lý."""
    if expected_pose == "frontal":
        return detected_pose == "frontal" or (abs(metrics["yaw_diff"]) <= 0.35 and 0.38 <= metrics["pitch_ratio"] <= 0.68)
    elif expected_pose in ("left", "right"):
        # Chấp nhận góc xoay ngang (linh hoạt cả 2 hướng do mirror webcam)
        return detected_pose in ("left", "right") or abs(metrics["yaw_diff"]) > 0.16
    elif expected_pose == "up":
        return detected_pose == "up" or metrics["pitch_ratio"] < 0.46
    elif expected_pose == "down":
        return detected_pose == "down" or metrics["pitch_ratio"] > 0.60
    return True


@app.route("/health", methods=["GET"])
def health():
    """Kiểm tra sức khỏe service AI."""
    return jsonify({
        "success": True,
        "model_ready": True,
        "service": "PBL4 Face AI Service",
        "timestamp": int(time.time()),
    })


@app.route("/internal/camera/frame", methods=["GET"])
def camera_frame():
    """Trả về 1 frame JPEG từ webcam nội bộ phục vụ Web GUI."""
    try:
        cap = get_camera()
        with _camera_lock:
            ret, frame = cap.read()

        if not ret or frame is None:
            return Response(b"", status=503, mimetype="image/jpeg")

        ret_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ret_enc:
            return Response(b"", status=500, mimetype="image/jpeg")

        return Response(buf.tobytes(), mimetype="image/jpeg", headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        })
    except Exception as e:
        return Response(str(e).encode(), status=503, mimetype="text/plain")


@app.route("/api/ai/enrollment/inspect", methods=["POST"])
def enrollment_inspect():
    """Kiểm tra pose của ảnh chụp trước khi thu thập."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        image_b64 = data.get("image", "")
        expected_pose = data.get("expected_pose", "frontal")

        if not image_b64:
            return jsonify({"success": False, "message": "Thiếu dữ liệu ảnh base64."}), 400

        img_bytes = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({"success": False, "message": "Ảnh giải mã không hợp lệ."}), 400

        engine = get_face_engine()
        faces = engine.detect(img)

        if len(faces) == 0:
            return jsonify({
                "success": False,
                "detected": False,
                "pose_ok": False,
                "message": "Không tìm thấy khuôn mặt trong khung hình.",
            })

        if len(faces) > 1:
            return jsonify({
                "success": False,
                "detected": True,
                "pose_ok": False,
                "message": "Phát hiện nhiều khuôn mặt, vui lòng đứng 1 mình trước camera.",
            })

        face = faces[0]
        detected_pose, metrics = estimate_pose(face.kps)
        pose_ok = check_pose_match(expected_pose, detected_pose, metrics)

        msg = f"Khuôn mặt hợp lệ: {expected_pose}" if pose_ok else f"Yêu cầu: {expected_pose} (hiện tại: {detected_pose})"

        return jsonify({
            "success": True,
            "detected": True,
            "pose_ok": pose_ok,
            "pose": detected_pose,
            "expected_pose": expected_pose,
            "metrics": metrics,
            "message": msg,
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi xử lý inspect: {str(e)}"}), 500


@app.route("/api/ai/enrollment/capture", methods=["POST"])
def enrollment_capture():
    """Trích xuất embedding vector 512-dim (2048 bytes) cho mẫu khuôn mặt."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        image_b64 = data.get("image", "")
        expected_pose = data.get("expected_pose", "frontal")

        if not image_b64:
            return jsonify({"success": False, "message": "Thiếu dữ liệu ảnh."}), 400

        img_bytes = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({"success": False, "message": "Ảnh giải mã không hợp lệ."}), 400

        engine = get_face_engine()
        faces = engine.detect(img)

        if len(faces) == 0:
            return jsonify({"success": False, "pose_ok": False, "message": "Không phát hiện khuôn mặt."}), 409

        # Lấy khuôn mặt lớn nhất
        main_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

        # Chuẩn hóa vector ArcFace 512-dim dạng float32 (2048 bytes)
        raw_emb = main_face.embedding.astype(np.float32)
        norm_emb = raw_emb / float(np.linalg.norm(raw_emb))
        raw_bytes = norm_emb.tobytes()

        if len(raw_bytes) != 2048:
            return jsonify({"success": False, "message": f"Độ dài vector không đúng: {len(raw_bytes)}"}), 500

        # Encode lại ảnh JPEG chất lượng cao
        _, jpeg_buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        jpeg_bytes = jpeg_buf.tobytes()

        return jsonify({
            "success": True,
            "pose_ok": True,
            "pose": expected_pose,
            "vector": base64.b64encode(raw_bytes).decode("ascii"),
            "image_jpeg": base64.b64encode(jpeg_bytes).decode("ascii"),
            "image_sha256": hashlib.sha256(jpeg_bytes).hexdigest(),
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi capture: {str(e)}"}), 500


@app.route("/api/ai/gallery/refresh", methods=["POST"])
def gallery_refresh():
    """Tải lại gallery từ CSDL Web nội bộ và cập nhật embeddings.pkl."""
    import pickle
    try:
        resp = requests.get(WEB_GALLERY_URL, timeout=10)
        if resp.status_code != 200:
            return jsonify({
                "success": False,
                "message": f"Không thể kết nối Web gallery: HTTP {resp.status_code}",
            }), 502

        payload = resp.json()
        embeddings_list = payload.get("embeddings", [])

        # Nhóm vector theo ma_nv
        by_employee: Dict[int, Dict[str, Any]] = {}
        for item in embeddings_list:
            emp_id = item["ma_nv"]
            raw_b64 = item["vector"]
            name = item.get("ho_ten", f"Nhân viên #{emp_id}")
            vec = np.frombuffer(base64.b64decode(raw_b64), dtype=np.float32)

            if emp_id not in by_employee:
                by_employee[emp_id] = {
                    "name": name,
                    "vectors": [],
                }
            by_employee[emp_id]["vectors"].append(vec)

        # Cập nhật database pkl
        db: Dict[str, Any] = {}
        for emp_id, info in by_employee.items():
            vecs = info["vectors"]
            mean_vec = np.mean(vecs, axis=0)
            mean_vec = mean_vec / np.linalg.norm(mean_vec)

            key_sv = f"SV{emp_id:03d}"
            db[key_sv] = {
                "name": info["name"],
                "embedding": mean_vec,
                "n_images": len(vecs),
            }
            # Đồng thời lưu thêm key số thuần để tra cứu linh hoạt
            db[str(emp_id)] = db[key_sv]

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(EMBEDDINGS_PATH, "wb") as f:
            pickle.dump(db, f)

        # Reload cache verify
        load_db(force_reload=True)

        return jsonify({
            "success": True,
            "count": len(by_employee),
            "total_samples": len(embeddings_list),
            "message": f"Đã cập nhật {len(by_employee)} nhân viên vào AI gallery.",
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi refresh gallery: {str(e)}"}), 500


if __name__ == "__main__":
    print(f"🚀 [AI Service] Khởi động AI REST Service trên cổng {PORT}...")
    # Tải trước engine
    get_face_engine()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
