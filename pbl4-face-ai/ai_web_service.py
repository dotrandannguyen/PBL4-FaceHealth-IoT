"""
ai_web_service.py - AI REST Service phục vụ Web Quản lý & Đăng ký khuôn mặt (PBL4)
Cung cấp các API:
  - GET  /health                      : Kiểm tra trạng thái AI service
  - GET  /internal/camera/frame       : Chụp và trả về frame JPEG từ Camera (ESP32-CAM hoặc Webcam)
  - POST /api/ai/enrollment/inspect   : Kiểm tra pose và chất lượng ảnh enrollment
  - POST /api/ai/enrollment/capture   : Trích xuất embedding 512-dim (2048 bytes raw) và JPEG
  - POST /api/ai/gallery/refresh      : Đồng bộ gallery khuôn mặt từ CSDL Web về file embeddings.pkl
"""

from __future__ import annotations

import os
from src.runtime_config import load_environment

load_environment()
import sys
import time
import base64
import hashlib
import hmac
import atexit
import io
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from flask import Flask, request, jsonify, Response
from werkzeug.exceptions import RequestEntityTooLarge
import cv2
import numpy as np
import requests

# Đảm bảo đường dẫn import
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.face_engine import FaceEngine
from src.verify import load_db
from src.camera_source import CameraSource
from src.enrollment_pose import estimate_pose, check_pose_match
from src.gallery_store import replace_from_loader
from src.gallery_payload import build_gallery

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

# Cấu hình Web Backend
WEB_GALLERY_URL = os.environ.get("WEB_GALLERY_URL", "http://localhost:8080/?action=internal_face_gallery")
EMBEDDINGS_PATH = BASE_DIR / "data" / "embeddings.pkl"
PORT = int(os.environ.get("AI_PORT", 5001))

# Quản lý Singleton Engine & Camera
_engine: Optional[FaceEngine] = None
_engine_lock = threading.Lock()

_cap: Optional[CameraSource] = None
_camera_lock = threading.RLock()
_camera_last_used = 0.0
_camera_idle_timer = None
CAMERA_IDLE_SECONDS = 3.0


def _arm_camera_idle_timer(delay: float = CAMERA_IDLE_SECONDS):
    """Hẹn giờ tự động nhả camera khi không có request trong khoảng delay."""
    global _camera_idle_timer
    if _camera_idle_timer is None:
        timer = threading.Timer(delay, lambda: _release_idle_camera(timer))
        _camera_idle_timer = timer
        timer.daemon = True
        timer.start()


def _release_idle_camera(expected_timer):
    global _camera_idle_timer
    with _camera_lock:
        if expected_timer is not _camera_idle_timer:
            return
        _camera_idle_timer = None
        if _cap is None:
            return
        remaining = _camera_last_used + CAMERA_IDLE_SECONDS - time.monotonic()
        if remaining > 0:
            _arm_camera_idle_timer(remaining)
        else:
            release_camera()


def get_face_engine() -> FaceEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                print(">> [AI Service] Đang nạp InsightFace Model...")
                _engine = FaceEngine()
                print(">> [AI Service] Nạp Model thành công!")
    return _engine


def get_camera() -> CameraSource:
    """Khởi tạo Camera: Hỗ trợ cả ESP32-CAM On-Demand Stream và Webcam."""
    global _cap, _camera_last_used
    with _camera_lock:
        if _cap is None or not _cap.isOpened():
            if _cap is not None:
                _cap.release()
            cam_source = os.environ.get("CAMERA_SOURCE", os.environ.get("PBL4_CAMERA_MODE", "esp32"))
            print(f">> [AI Service] Đang mở Camera ({cam_source})...")
            if cam_source == "esp32":
                _cap = CameraSource(source="esp32", width=640, height=480)
            else:
                idx = int(os.environ.get("PBL4_CAMERA_ID", "0"))
                _cap = CameraSource(source=idx, width=640, height=480)
        _camera_last_used = time.monotonic()
        _arm_camera_idle_timer()
        return _cap


@app.before_request
def authorize_internal_request():
    if request.path == "/health":
        return None
    token = os.environ.get("PBL4_INTERNAL_TOKEN", "")
    if not token:
        return jsonify({"success": False, "message": "Internal API is not configured"}), 503
    supplied = request.headers.get("Authorization", "")
    if not hmac.compare_digest(supplied.encode("utf-8"), ("Bearer " + token).encode("utf-8")):
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    return None


@app.after_request
def prevent_response_caching(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def decode_enrollment_request():
    from PIL import Image

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    pose = data.get("expected_pose", "frontal")
    if pose not in ("frontal", "left", "right", "up", "down"):
        raise ValueError("Invalid pose")
    encoded = data.get("image")
    if not isinstance(encoded, str) or not encoded or len(encoded) > 7 * 1024 * 1024:
        raise ValueError("Invalid image size")
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Image too large")
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ("JPEG", "PNG") or source.width * source.height > 16000000:
                raise ValueError("Invalid image dimensions or format")
            source.verify()
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except Exception as exc:
        raise ValueError("Invalid JPEG/PNG image") from exc
    if image is None:
        raise ValueError("Invalid image")
    return image, pose


@atexit.register
def release_camera():
    global _cap, _camera_idle_timer
    with _camera_lock:
        if _camera_idle_timer is not None:
            _camera_idle_timer.cancel()
            _camera_idle_timer = None
        if _cap is not None:
            try:
                _cap.release()
            finally:
                _cap = None


@app.route("/health", methods=["GET"])
def health():
    """Kiểm tra sức khỏe service AI."""
    with _camera_lock:
        camera_open = _cap is not None and _cap.isOpened()
    return jsonify({
        "success": True,
        "model_ready": _engine is not None,
        "camera_open": camera_open,
        "service": "PBL4 Face AI Service",
        "timestamp": int(time.time()),
    })


@app.route("/internal/camera/frame", methods=["GET"])
def camera_frame():
    """Trả về 1 frame JPEG từ Camera (ESP32-CAM hoặc Webcam) phục vụ Web GUI."""
    global _camera_last_used
    try:
        with _camera_lock:
            cap = get_camera()
            try:
                ret, frame = cap.read()
            except Exception:
                release_camera()
                raise
            if not ret or frame is None:
                release_camera()
                return Response(b"", status=503, mimetype="image/jpeg")
            _camera_last_used = time.monotonic()

        ret_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ret_enc:
            return Response(b"", status=500, mimetype="image/jpeg")

        return Response(
            buf.tobytes(),
            mimetype="image/jpeg",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )
    except Exception as e:
        return Response(b"Camera unavailable", status=503, mimetype="text/plain")


@app.route("/api/ai/enrollment/inspect", methods=["POST"])
def enrollment_inspect():
    """Kiểm tra pose của ảnh chụp trước khi thu thập."""
    try:
        try:
            img, expected_pose = decode_enrollment_request()
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400

        engine = get_face_engine()
        with _engine_lock:
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
        try:
            detected_pose, metrics = estimate_pose(face.kps)
        except (ValueError, TypeError):
            return jsonify({"success": False, "pose_ok": False, "message": "Invalid face landmarks"}), 409
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
    except RequestEntityTooLarge:
        return jsonify({"success": False, "message": "Payload too large"}), 413
    except Exception as e:
        app.logger.exception("Enrollment inspect failed")
        return jsonify({"success": False, "message": "Enrollment inspect failed"}), 500


@app.route("/api/ai/enrollment/capture", methods=["POST"])
def enrollment_capture():
    """Trích xuất embedding vector 512-dim (2048 bytes) cho mẫu khuôn mặt."""
    try:
        try:
            img, expected_pose = decode_enrollment_request()
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400

        engine = get_face_engine()
        with _engine_lock:
            faces = engine.detect(img)

        if len(faces) == 0:
            return jsonify({"success": False, "pose_ok": False, "message": "Không phát hiện khuôn mặt."}), 409

        if len(faces) != 1:
            return jsonify({"success": False, "pose_ok": False, "message": "Only one face is allowed"}), 409
        main_face = faces[0]
        try:
            detected_pose, metrics = estimate_pose(main_face.kps)
        except (ValueError, TypeError):
            return jsonify({"success": False, "pose_ok": False, "message": "Invalid face landmarks"}), 409
        if not check_pose_match(expected_pose, detected_pose, metrics):
            return jsonify({"success": False, "pose_ok": False, "message": "Pose changed before capture"}), 409

        # Chuẩn hóa vector ArcFace 512-dim dạng float32 (2048 bytes)
        raw_emb = main_face.embedding.astype(np.float32)
        norm = float(np.linalg.norm(raw_emb))
        if raw_emb.shape != (512,) or not np.isfinite(raw_emb).all() or not np.isfinite(norm) or norm <= 0:
            raise ValueError("Invalid face embedding")
        norm_emb = raw_emb / norm
        raw_bytes = norm_emb.astype("<f4").tobytes()

        if len(raw_bytes) != 2048:
            return jsonify({"success": False, "message": f"Độ dài vector không đúng: {len(raw_bytes)}"}), 500

        # Encode lại ảnh JPEG chất lượng cao
        encoded_ok, jpeg_buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not encoded_ok:
            raise ValueError("JPEG encoding failed")
        jpeg_bytes = jpeg_buf.tobytes()

        return jsonify({
            "success": True,
            "pose_ok": True,
            "pose": expected_pose,
            "vector": base64.b64encode(raw_bytes).decode("ascii"),
            "image_jpeg": base64.b64encode(jpeg_bytes).decode("ascii"),
            "image_sha256": hashlib.sha256(jpeg_bytes).hexdigest(),
        })
    except RequestEntityTooLarge:
        return jsonify({"success": False, "message": "Payload too large"}), 413
    except Exception as e:
        app.logger.exception("Enrollment capture failed")
        return jsonify({"success": False, "message": "Enrollment capture failed"}), 500


@app.route("/api/ai/gallery/refresh", methods=["POST"])
def gallery_refresh():
    """Serialize fetching and replacement, preserving the old file on any error."""
    try:
        def fetch():
            response = requests.get(
                WEB_GALLERY_URL,
                headers={"Authorization": "Bearer " + os.environ.get("PBL4_INTERNAL_TOKEN", "")},
                timeout=10,
                allow_redirects=False,
            )
            if response.status_code != 200:
                raise ValueError("Web gallery is unavailable")
            return build_gallery(response.json())

        gallery = replace_from_loader(EMBEDDINGS_PATH, fetch)
        return jsonify({
            "success": True,
            "count": len(gallery),
            "total_samples": sum(person["n_images"] for person in gallery.values()),
            "message": "Gallery refreshed",
        })
    except Exception:
        app.logger.exception("Gallery refresh failed")
        return jsonify({"success": False, "message": "Gallery refresh failed; previous gallery preserved"}), 503


if __name__ == "__main__":
    print(f"🚀 [AI Service] Khởi động AI REST Service trên cổng {PORT}...")
    # Tải trước engine
    get_face_engine()
    app.run(host=os.environ.get("AI_BIND_HOST", "127.0.0.1"), port=PORT, threaded=True)
