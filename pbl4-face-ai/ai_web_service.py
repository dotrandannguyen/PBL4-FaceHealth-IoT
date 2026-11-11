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
import re
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from flask import Flask, request, jsonify, Response, has_request_context
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

_cap: Optional[Any] = None
_camera_lock = threading.RLock()
_camera_last_used = 0.0
_camera_idle_timer = None
_active_camera_source: Optional[str] = None
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


def get_camera(source_override: Optional[str] = None):
    """Khởi tạo Camera: Hỗ trợ chuyển đổi linh hoạt giữa ESP32-CAM và Webcam."""
    global _cap, _camera_last_used, _active_camera_source
    with _camera_lock:
        req_arg = request.args.get("source") if has_request_context() else None
        requested = source_override or req_arg or os.environ.get("CAMERA_SOURCE", os.environ.get("PBL4_CAMERA_MODE", "esp32"))
        if requested is None:
            requested = "esp32"
        requested = str(requested).strip().lower()
        if requested not in ("esp32", "local"):
            requested = "esp32"

        # Nếu đang mở nguồn khác, giải phóng và khởi tạo lại theo nguồn mới
        if _cap is not None and _active_camera_source != requested:
            try:
                _cap.release()
            except Exception:
                pass
            _cap = None

        if _cap is None or not _cap.isOpened():
            if _cap is not None:
                try:
                    _cap.release()
                except Exception:
                    pass
                _cap = None
            _active_camera_source = requested
            if requested == "esp32":
                print(">> [AI Service] Đang mở Camera ESP32...")
                esp32_url = os.environ.get("ESP32_STREAM_URL", "http://192.168.1.14:81/stream")
                _cap = CameraSource(source="esp32", stream_url=esp32_url, width=640, height=480)
            else:
                print(">> [AI Service] Đang mở webcam nội bộ theo cấu hình...")
                index = int(os.environ.get("PBL4_CAMERA_ID", "0"))
                backend = os.environ.get("PBL4_CAMERA_BACKEND", "dshow" if sys.platform == "win32" else "auto")
                api = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "auto": cv2.CAP_ANY}.get(backend)
                if api is None:
                    api = cv2.CAP_ANY
                _cap = cv2.VideoCapture(index, api)
                _cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                _cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        _camera_last_used = time.monotonic()
        _arm_camera_idle_timer()
        return _cap


@app.route("/api/register_camera", methods=["POST"])
def register_camera():
    """ESP32-CAM tự động báo danh IP và stream URL khi kết nối mạng."""
    global _active_camera_source, _cap
    data = request.get_json(silent=True) or {}
    stream_url = data.get("stream_url")
    node_ip = data.get("ip")
    if node_ip and not stream_url:
        stream_url = f"http://{node_ip}:81/stream"
    if stream_url:
        os.environ["ESP32_STREAM_URL"] = stream_url
        os.environ["CAMERA_SOURCE"] = "esp32"
        with _camera_lock:
            if _cap is not None:
                try:
                    _cap.release()
                except Exception:
                    pass
                _cap = None
        print(f">> [AI Service] ESP32-CAM đã báo danh! Cập nhật Stream URL: {stream_url}")
        return jsonify({"success": True, "stream_url": stream_url}), 200
    return jsonify({"success": False, "message": "Thieu stream_url hoặc ip"}), 400


@app.before_request
def authorize_internal_request():
    if request.path in ("/health", "/internal/camera/stream", "/stream", "/api/register_camera", "/api/iot/status"):
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

    use_live = data.get("use_live", False)
    encoded = data.get("image")

    if (encoded is None or encoded == "") and use_live:
        with _camera_lock:
            cap = get_camera()
            ret, frame = cap.read()
            if not ret or frame is None:
                raise ValueError("Camera frame unavailable")
            return frame, pose

    if not isinstance(encoded, str) or not encoded or len(encoded) > 7 * 1024 * 1024:
        raise ValueError("Invalid image size")

    if encoded.startswith("data:image"):
        comma = encoded.find(",")
        if comma != -1:
            encoded = encoded[comma + 1:]

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
    global _cap, _camera_idle_timer, _active_camera_source
    with _camera_lock:
        if _camera_idle_timer is not None:
            _camera_idle_timer.cancel()
            _camera_idle_timer = None
        if _cap is not None:
            try:
                _cap.release()
            finally:
                _cap = None
        _active_camera_source = None


@app.route("/health", methods=["GET"])
def health():
    """Kiểm tra sức khỏe service AI."""
    with _camera_lock:
        camera_open = _cap is not None and _cap.isOpened()
        active_source = _active_camera_source or os.environ.get("CAMERA_SOURCE", os.environ.get("PBL4_CAMERA_MODE", "local"))
    return jsonify({
        "success": True,
        "model_ready": _engine is not None,
        "camera_open": camera_open,
        "camera_source": active_source,
        "service": "PBL4 Face AI Service",
        "timestamp": int(time.time()),
    })


@app.route("/internal/camera/frame", methods=["GET"])
def camera_frame():
    """Trả về 1 frame JPEG từ Camera (ESP32-CAM hoặc Webcam) phục vụ Web GUI."""
    global _camera_last_used
    source = request.args.get("source")
    try:
        with _camera_lock:
            cap = get_camera(source_override=source)
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


def _gen_mjpeg_stream(source: Optional[str] = None):
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    while True:
        try:
            with _camera_lock:
                cap = get_camera(source_override=source)
                if hasattr(cap, "read_jpeg"):
                    ret, frame_bytes = cap.read_jpeg()
                    if not ret or not frame_bytes:
                        time.sleep(0.04)
                        continue
                    jpg_data = frame_bytes
                else:
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        time.sleep(0.04)
                        continue
                    ret_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if not ret_enc:
                        time.sleep(0.04)
                        continue
                    jpg_data = buf.tobytes()
            yield boundary + jpg_data + b"\r\n"
            time.sleep(0.03)
        except GeneratorExit:
            break
        except Exception:
            time.sleep(0.05)


@app.route("/internal/camera/stream", methods=["GET"])
@app.route("/stream", methods=["GET"])
def camera_stream():
    """Luồng video MJPEG thời gian thực (~25-30 FPS) từ Camera."""
    source = request.args.get("source")
    return Response(
        _gen_mjpeg_stream(source=source),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0",
            "Pragma": "no-cache",
            "Connection": "close",
        },
    )


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

# =========================================================================
# IOT COORDINATOR: ĐỒNG BỘ ESP8266 + ESP32-CAM CHO CHẤM CÔNG DƯỚI 10S
# =========================================================================
_iot_sessions: Dict[str, Dict[str, Any]] = {}
_iot_lock = threading.Lock()
IOT_SESSION_TTL_SECONDS = 12.0


def _clean_expired_iot_sessions():
    now = time.monotonic()
    with _iot_lock:
        expired = [sid for sid, s in _iot_sessions.items() if now - s["created_at"] > IOT_SESSION_TTL_SECONDS]
        for sid in expired:
            del _iot_sessions[sid]


@app.route("/api/iot/status", methods=["GET"])
def iot_session_status():
    """Kiểm tra trạng thái phiên chấm công đang diễn ra để web tự động bật/tắt camera on-demand."""
    _clean_expired_iot_sessions()
    with _iot_lock:
        active = len(_iot_sessions) > 0
        latest_session = None
        if active:
            latest_sid = list(_iot_sessions.keys())[-1]
            s = _iot_sessions[latest_sid]
            latest_session = {
                "session_id": s["session_id"],
                "MaNV": s.get("MaNV"),
                "name": s.get("name"),
                "matched": s.get("matched", False),
                "image_b64": s.get("image_b64"),
                "age_seconds": round(time.monotonic() - s["created_at"], 1),
            }
    return jsonify({
        "success": True,
        "active": active,
        "session": latest_session,
    })


@app.route("/api/iot/start", methods=["POST"])
def iot_session_start():
    """
    Kích hoạt khi nhân viên đặt ngón tay lên MAX30102.
    Lấy frame từ luồng camera (ESP32-CAM hoặc Webcam), nhận diện danh tính ngay lập tức.
    """
    _clean_expired_iot_sessions()

    # 1. Bắt khung hình từ camera (ưu tiên chụp trực tiếp từ ESP32-CAM nếu có)
    frame = None
    jpeg_bytes = None
    esp32_url = os.environ.get("ESP32_STREAM_URL", "http://192.168.1.14:81/stream")
    capture_url = esp32_url.replace("/stream", "/capture")
    try:
        import urllib.request
        req = urllib.request.Request(capture_url, headers={"User-Agent": "PBL4-FaceAI-Client"})
        with urllib.request.urlopen(req, timeout=1.8) as res:
            if res.status == 200:
                jpeg_bytes = res.read()
                frame = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception as e:
        app.logger.warning(f"Could not read from /capture: {e}, falling back to get_camera().read()")

    if frame is None or frame.size == 0:
        with _camera_lock:
            cap = get_camera()
            ret, frame = cap.read()
        if frame is not None and frame.size > 0:
            encoded_ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            jpeg_bytes = buf.tobytes() if encoded_ok else b""

    if frame is None or frame.size == 0:
        return jsonify({
            "success": False,
            "message": "Camera khong kha dung",
            "name": "Khong co Camera",
        }), 503

    # 2. Nhận diện khuôn mặt với InsightFace
    engine = get_face_engine()
    with _engine_lock:
        faces = engine.detect(frame)

    from src.verify import identify
    identity = identify(engine, frame, threshold=0.45)
    matched = bool(identity.get("match", False))
    student_id = str(identity.get("student_id") or "")
    student_name = str(identity.get("name") or "Chưa xác định")

    match_num = re.search(r"(\d+)", student_id)
    ma_nv = int(match_num.group(1)) if match_num else None

    # Tùy chọn test phần cứng tại bàn nếu chưa có người đứng trước camera
    if not matched and os.environ.get("PBL4_ALLOW_TEST_FALLBACK", "0") == "1":
        ma_nv = int(os.environ.get("PBL4_TEST_MANV", "1"))
        student_name = "Nguyen Van A"
        matched = True

    # 3. Mã hóa ảnh JPEG base64
    if jpeg_bytes is None:
        encoded_ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        jpeg_bytes = buf.tobytes() if encoded_ok else b""
    image_b64 = base64.b64encode(jpeg_bytes).decode("ascii") if jpeg_bytes else None

    # 4. Phân tích nét mặt mệt mỏi AI 2 (nếu có thể)
    status_label = "Normal"
    try:
        from src.predict_status import StatusPredictor
        predictor = StatusPredictor()
        st_res = predictor.predict_status_detailed([frame])
        if isinstance(st_res, dict) and st_res.get("status") in ("Normal", "Fatigue", "Exhausted"):
            status_label = st_res["status"]
    except Exception:
        status_label = "Normal"

    # 5. Lưu phiên vào RAM
    session_id = str(uuid4())
    occurred_at = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="milliseconds")

    with _iot_lock:
        _iot_sessions[session_id] = {
            "session_id": session_id,
            "created_at": time.monotonic(),
            "occurred_at": occurred_at,
            "matched": matched,
            "MaNV": ma_nv,
            "name": student_name,
            "similarity": float(identity.get("similarity", 0.0)),
            "image_b64": image_b64,
            "status": status_label,
        }

    return jsonify({
        "success": True,
        "session_id": session_id,
        "matched": matched,
        "MaNV": ma_nv,
        "name": student_name if matched else "Chua nhan ra",
        "message": f"Chao {student_name}" if matched else "Nhin thang camera",
    })


@app.route("/api/iot/biometrics", methods=["POST"])
def iot_session_biometrics():
    """
    Nhận số đo nhịp tim và SpO2 từ ESP8266 sau 3-5 giây.
    Gộp với ảnh mặt đã nhận diện và gửi 1 gói chuẩn duy nhất sang Web PHP /api/chamcong.
    """
    _clean_expired_iot_sessions()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "JSON object required"}), 400

    session_id = str(data.get("session_id") or "").strip()
    bpm = data.get("bpm") or data.get("NhipTim")
    spo2 = data.get("spo2") or data.get("SpO2")

    if not session_id:
        return jsonify({"success": False, "message": "Thieu session_id"}), 400

    with _iot_lock:
        session = _iot_sessions.pop(session_id, None)

    if session is None:
        return jsonify({"success": False, "message": "Phien cham cong da het han hoac khong ton tai"}), 410

    if not session.get("matched") or session.get("MaNV") is None:
        return jsonify({
            "success": False,
            "message": "Chua xac dinh duoc khuon mat",
            "name": "Chua nhan ra",
        }), 422

    # Đóng gói payload gửi sang Web Backend PHP
    event_payload = {
        "event_id": session["session_id"],
        "occurred_at": session["occurred_at"],
        "MaNV": session["MaNV"],
        "MaTB": int(os.environ.get("PBL4_DEVICE_ID", "1")),
        "TrangThai": session.get("status", "Normal"),
        "NhipTim": int(bpm) if bpm and float(bpm) > 0 else None,
        "SpO2": round(float(spo2), 1) if spo2 and float(spo2) > 0 else None,
        "image": session.get("image_b64"),
    }

    web_api_url = os.environ.get("PBL4_WEB_API", "http://localhost:8080/api/chamcong")
    token = os.environ.get("PBL4_INTERNAL_TOKEN", "")

    try:
        resp = requests.post(
            web_api_url,
            json=event_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=4.0,
            allow_redirects=False,
        )
        web_res = resp.json() if resp.status_code == 200 else {}
    except Exception as exc:
        app.logger.exception("Chuyen tiep cham cong len Web PHP that bai")
        return jsonify({
            "success": False,
            "message": "Loi ket noi Web Server",
            "name": session["name"],
        }), 503

    action = web_res.get("action", "checkin")
    msg = web_res.get("message", "Chấm công thành công")

    return jsonify({
        "success": True,
        "action": action,
        "status": web_res.get("status", "success"),
        "MaNV": session["MaNV"],
        "name": session["name"],
        "bpm": bpm,
        "spo2": spo2,
        "message": msg,
    })


@app.route("/api/iot/abort", methods=["POST"])
def iot_session_abort():
    """Hủy phiên đo khi nhân viên rút tay ra sớm."""
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id") or "").strip()
    if session_id:
        with _iot_lock:
            _iot_sessions.pop(session_id, None)
    return jsonify({"success": True, "message": "Da huy phien do"})


if __name__ == "__main__":
    print(f"🚀 [AI Service] Khởi động AI REST Service trên cổng {PORT}...")
    # Tải trước engine
    get_face_engine()
    app.run(host=os.environ.get("AI_BIND_HOST", "127.0.0.1"), port=PORT, threaded=True)
