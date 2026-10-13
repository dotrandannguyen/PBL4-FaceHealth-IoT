"""
app.py — Flask Controller (Tầng Presentation)
==============================================
- Singleton camera VideoCapture (tránh xung đột tài nguyên)
- Dùng ai_engine.detector để phân tích frame
- RESTful API endpoints cho Dashboard
- Login / Logout + phân quyền theo VaiTro
"""

import base64
import binascii
import functools
import os
import re
import secrets
import threading
import time

import cv2
from flask import (
    Flask, render_template, request, jsonify,
    Response, session, redirect, url_for
)
import services
import ai_engine
import database as _db

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

_ENROLLMENT_POSES = ("frontal", "left", "right", "up", "down")
_POSE_LABELS = {
    "frontal": "Nhìn thẳng",
    "left": "Quay trái",
    "right": "Quay phải",
    "up": "Ngẩng lên",
    "down": "Cúi xuống",
}
_ENROLLMENT_SESSION_TTL = 600


# ============================================================
# Auth Middleware
# ============================================================

def login_required(f):
    """Decorator: yêu cầu đăng nhập."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'MaNV' not in session:
            # API request → trả JSON 401
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Chưa đăng nhập"}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: yêu cầu đăng nhập + Quản trị viên (MaVaiTro=1)."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'MaNV' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Chưa đăng nhập"}), 401
            return redirect(url_for('login_page'))
        if session.get('MaVaiTro') != 1:
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Không có quyền truy cập"}), 403
            return redirect(url_for('me_page'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# Camera Singleton — tránh xung đột tài nguyên giữa các request
# ============================================================

_camera = None
_camera_lock = threading.Lock()


def get_camera():
    """Trả về instance camera toàn cục, khởi tạo nếu chưa có."""
    global _camera

    with _camera_lock:
        if _camera is None or not _camera.isOpened():
            _camera = cv2.VideoCapture(0)
            _camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            _camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            _camera.set(cv2.CAP_PROP_FPS, 30)

        return _camera


# ============================================================
# Video Stream Generator
# ============================================================

def generate_frames():
    """
    Generator cho MJPEG stream.
    Dùng singleton camera + ai_engine.detector để phân tích frame.
    """
    camera = get_camera()

    while True:
        with _camera_lock:
            success, frame = camera.read()

        if not success:
            break

        # Phân tích frame với AI engine
        annotated_frame, alert = ai_engine.detector.analyze_frame(frame)

        # Encode sang JPEG
        ret, buffer = cv2.imencode(
            '.jpg',
            annotated_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 85]
        )

        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n'
            + frame_bytes
            + b'\r\n'
        )


# ============================================================
# Routes — Login / Logout
# ============================================================

@app.route('/login')
def login_page():
    """GET /login — Trang đăng nhập."""
    # Đã login rồi thì redirect
    if 'MaNV' in session:
        if session.get('MaVaiTro') == 1:
            return redirect(url_for('index'))
        return redirect(url_for('me_page'))
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    """
    POST /api/login
    Body: {"TenDangNhap": "admin", "MatKhau": "admin123"}
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    username = data.get('TenDangNhap', '')
    password = data.get('MatKhau', '')

    result = services.authenticate(username, password)

    if result.get("status") != "success":
        return jsonify(result), 401

    user = result["user"]

    # Lưu session
    session['MaTK']      = user['MaTK']
    session['MaNV']      = user['MaNV']
    session['HoTen']     = user['HoTen']
    session['MaVaiTro']  = user['MaVaiTro']
    session['TenVaiTro'] = user['TenVaiTro']

    # Xác định URL redirect theo role
    if user['MaVaiTro'] == 1:
        redirect_url = '/'
    else:
        redirect_url = '/me'

    return jsonify({
        "status":      "success",
        "message":     "Đăng nhập thành công",
        "redirect":    redirect_url,
        "user": {
            "MaNV":      user['MaNV'],
            "HoTen":     user['HoTen'],
            "MaVaiTro":  user['MaVaiTro'],
            "TenVaiTro": user['TenVaiTro'],
        },
    }), 200


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """POST /api/logout — Đăng xuất."""
    session.clear()
    return jsonify({"status": "success", "message": "Đã đăng xuất"}), 200


@app.route('/logout')
def logout_page():
    """GET /logout — Đăng xuất và redirect về login."""
    session.clear()
    return redirect(url_for('login_page'))


# ============================================================
# Routes — Pages (có phân quyền)
# ============================================================

@app.route('/')
@admin_required
def index():
    return render_template('index.html')


@app.route('/employees')
@admin_required
def employees_page():
    """GET /employees — Trang quản lý nhân viên."""
    return render_template('employees.html')


@app.route('/me')
@login_required
def me_page():
    """GET /me — Trang cá nhân nhân viên."""
    if session.get('MaVaiTro') == 1:
        return redirect(url_for('index'))
    return render_template('me.html')


# ============================================================
# Routes — Video (public cho MJPEG stream)
# ============================================================

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


# ============================================================
# Routes — ESP32 Sensor (PUBLIC — không yêu cầu login)
# ============================================================

@app.route('/api/sensor', methods=['POST'])
def receive_sensor_data():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    success = services.save_sensor_data(data)

    if success:
        return jsonify({"status": "success"}), 200

    return jsonify({"status": "error", "message": "Missing fields"}), 400


@app.route('/api/chamcong', methods=['POST'])
def receive_cham_cong():
    """
    POST /api/chamcong
    Body: {"MaNV": int, "MaTB": int (optional)}
    PUBLIC — ESP32 gọi trực tiếp.

    Nếu camera singleton đang mở, capture 1 frame và encode JPG
    để lưu làm bằng chứng. Không tạo camera mới.
    Nếu camera chưa mở hoặc có lỗi, image_bytes = None —
    chấm công vẫn hoạt động bình thường.
    """
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    ma_nv = data.get('MaNV')
    ma_tb = data.get('MaTB', 1)

    if ma_nv is None:
        return jsonify({"status": "error", "message": "Thiếu MaNV"}), 400

    # --- Capture frame từ singleton camera ---
    # Dùng get_camera() thay vì check _camera is not None trực tiếp,
    # để camera được khởi tạo ngay cả khi /video_feed chưa được gọi trước.
    image_bytes = None
    try:
        cam = get_camera()
        with _camera_lock:
            if cam is not None and cam.isOpened():
                ok, frame = cam.read()
                if ok and frame is not None:
                    image_bytes = services.encode_frame_to_jpg(frame)
    except Exception as _cap_err:
        # Không được để lỗi camera block chấm công
        print(f"[app] Canh bao: khong the capture frame: {_cap_err}")

    result = services.process_attendance(ma_nv, ma_tb, image_bytes)

    # Đồng bộ AI Engine
    if result.get("action") == "checkin" and result.get("status") == "success":
        ai_engine.detector.set_active_employee(ma_nv)

    elif result.get("action") == "checkout" and result.get("status") == "success":
        if ai_engine.detector.active_ma_nv == ma_nv:
            ai_engine.detector.clear_active_employee()

    http_code = 200 if result.get("status") == "success" else 400
    return jsonify(result), http_code



# ============================================================
# Routes — Ảnh bằng chứng chấm công (admin only)
# ============================================================


@app.route('/api/attendance/<int:ma_cc>/image/in')
@admin_required
def attendance_image_in(ma_cc):
    """
    GET /api/attendance/<ma_cc>/image/in
    Trả AnhVao của bản ghi MaCC dưới dạng image/jpeg.
    """
    img = _db.get_attendance_image(ma_cc, "in")
    if img is None:
        return jsonify({
            "status":  "error",
            "message": "Không có ảnh bằng chứng",
        }), 404
    return Response(img, mimetype="image/jpeg")


@app.route('/api/attendance/<int:ma_cc>/image/out')
@admin_required
def attendance_image_out(ma_cc):
    """
    GET /api/attendance/<ma_cc>/image/out
    Trả AnhRa của bản ghi MaCC dưới dạng image/jpeg.
    """
    img = _db.get_attendance_image(ma_cc, "out")
    if img is None:
        return jsonify({
            "status":  "error",
            "message": "Không có ảnh bằng chứng",
        }), 404
    return Response(img, mimetype="image/jpeg")


# ============================================================
# Routes — Dashboard API (admin required)
# ============================================================

@app.route('/api/get_health')
@admin_required
def get_health():
    return jsonify(services.fetch_health_data())


@app.route('/api/chart/health')
@admin_required
def chart_health():
    return jsonify(services.fetch_health_chart_data())


@app.route('/api/get_chamcong')
@admin_required
def get_chamcong():
    return jsonify(services.fetch_attendance_history())


@app.route('/api/get_chamcong_today')
@admin_required
def get_chamcong_today():
    return jsonify(services.fetch_today_attendance_summary())


@app.route('/api/get_chamcong_weekly')
@admin_required
def get_chamcong_weekly():
    return jsonify(services.fetch_attendance_weekly())


@app.route('/api/dashboard/attendance')
@admin_required
def dashboard_attendance():
    from datetime import datetime as _dt
    date_str = request.args.get('date')
    if date_str:
        try:
            _dt.strptime(date_str.strip(), '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': 'Ngày không hợp lệ. Định dạng yêu cầu: YYYY-MM-DD'
            }), 400
    return jsonify(services.fetch_attendance_dashboard(date_str))


@app.route('/api/attendance/today')
@admin_required
def attendance_today():
    data = services.fetch_attendance_dashboard()
    return jsonify(data.get("Records", []))


@app.route('/api/attendance/history')
@admin_required
def attendance_history_filtered():
    tu_ngay = request.args.get('tu_ngay')
    den_ngay = request.args.get('den_ngay')
    keyword = request.args.get('keyword')
    
    # validate date format if provided
    from datetime import datetime as _dt
    for date_str in [tu_ngay, den_ngay]:
        if date_str:
            try:
                _dt.strptime(date_str.strip(), '%Y-%m-%d')
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': 'Ngày không hợp lệ. Định dạng yêu cầu: YYYY-MM-DD'
                }), 400
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
                
    data = services.fetch_attendance_history_filtered(tu_ngay, den_ngay, keyword, page, limit)
    return jsonify(data)


# ============================================================
# Routes — Ca làm việc (admin)
# ============================================================

@app.route('/api/shifts')
@admin_required
def get_shifts():
    return jsonify(services.fetch_all_shifts())


@app.route('/api/assign_shift', methods=['POST'])
@admin_required
def post_assign_shift():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    ok, msg = services.assign_shift(data)

    if ok:
        return jsonify({"status": "success", "message": msg}), 200

    return jsonify({"status": "error", "message": msg}), 400


# ============================================================
# Routes — AI Alerts & Status
# ============================================================

@app.route('/api/get_alerts')
@admin_required
def get_alerts():
    limit = request.args.get('limit', 10, type=int)
    return jsonify(services.fetch_alert_history(limit=limit))


@app.route('/api/ai_status')
@login_required
def ai_status():
    return jsonify(ai_engine.detector.get_current_status())


# ============================================================
# Routes — Vai trò (admin)
# ============================================================

@app.route('/api/roles')
@admin_required
def get_roles():
    return jsonify(services.fetch_all_roles())


# ============================================================
# Routes — Nhân viên CRUD (admin)
# ============================================================

@app.route('/api/employees')
@admin_required
def list_employees():
    return jsonify(services.fetch_employees())


@app.route('/api/employees/<int:ma_nv>')
@admin_required
def get_employee(ma_nv):
    emp = services.fetch_employee(ma_nv)
    if emp is None:
        return jsonify({"status": "error", "message": "Không tìm thấy nhân viên"}), 404
    return jsonify(emp)


@app.route('/api/employees', methods=['POST'])
@admin_required
def create_employee():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    data.pop("AnhKhuonMat", None)

    result = services.create_employee(data)

    if result.get("status") == "success":
        return jsonify(result), 201

    return jsonify(result), 400


@app.route('/api/employees/<int:ma_nv>', methods=['PUT'])
@admin_required
def update_employee(ma_nv):
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    data.pop("AnhKhuonMat", None)

    try:
        result = services.edit_employee(ma_nv, data)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi server: {e}"}), 500

    if result.get("status") == "success":
        return jsonify(result), 200

    if result.get("status") == "not_found":
        return jsonify({"status": "error", "message": "Không tìm thấy nhân viên"}), 404

    return jsonify(result), 400


# ============================================================
# Routes — Face Enrollment (admin)
# ============================================================

_enrollment_sessions = {}
_enrollment_sessions_lock = threading.Lock()


def _classify_head_pose(yaw, pitch):
    if abs(yaw) <= 12 and abs(pitch) <= 12:
        return "frontal"
    if 15 <= yaw <= 40 and abs(pitch) <= 18:
        return "left"
    if -40 <= yaw <= -15 and abs(pitch) <= 18:
        return "right"
    if 12 <= pitch <= 35 and abs(yaw) <= 15:
        return "up"
    if -35 <= pitch <= -12 and abs(yaw) <= 15:
        return "down"
    return "between"


def _pose_result(pose, expected_pose):
    current_pose = pose.get("current_pose", "unknown")
    yaw, pitch = pose.get("yaw"), pose.get("pitch")
    if yaw is not None and pitch is not None:
        current_pose = _classify_head_pose(yaw, pitch)

    pose_ok = current_pose == expected_pose
    if current_pose == "no_face":
        instruction = "Đưa khuôn mặt vào giữa khung hình."
    elif current_pose == "multiple_faces":
        instruction = "Chỉ để một người trong khung hình."
    elif current_pose == "unknown":
        instruction = "Không ước lượng được hướng đầu; nhìn rõ camera."
    elif pose_ok:
        instruction = "Đúng hướng, giữ yên."
    elif expected_pose == "frontal":
        instruction = "Nhìn thẳng camera và giữ đầu cân bằng."
    elif current_pose == "frontal":
        instruction = f"{_POSE_LABELS[expected_pose]} thêm."
    else:
        instruction = f"Đang hướng {_POSE_LABELS.get(current_pose, 'chưa đúng')}; {_POSE_LABELS[expected_pose].lower()} thêm."

    return {
        "current_pose": current_pose,
        "expected_pose": expected_pose,
        "pose_ok": pose_ok,
        "instruction": instruction,
        "yaw": yaw,
        "pitch": pitch,
    }


def _read_camera_frame():
    cam = get_camera()
    with _camera_lock:
        return cam.read() if cam is not None and cam.isOpened() else (False, None)


def _decode_face_image(data):
    if not isinstance(data, str):
        raise ValueError("Thiếu ảnh base64.")
    data = re.sub(r"^data:image/[^;]+;base64,", "", data)
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Ảnh base64 không hợp lệ.") from exc
    import numpy as np
    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Không giải mã được ảnh.")
    return frame

@app.route('/api/employees/<int:ma_nv>/face/register', methods=['POST'])
@admin_required
def register_face(ma_nv):
    """
    POST /api/employees/<ma_nv>/face/register

    Dang ky khuon mat cho nhan vien qua InsightFace.
    Thu 5 frame tu camera singleton (khong tao camera moi).
    Moi frame phai co dung 1 khuon mat.
    Luu 5 embedding 512D vao FaceEmbedding.

    Neu da co embedding: tra loi 409, KHONG ghi de am tham.
    """
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ("start", "pose", "capture", "complete", "cancel"):
        return jsonify({"status": "error", "message": "Enrollment yêu cầu quy trình pose-guided 5 góc."}), 400

    if action == "start":
        emp = services.fetch_employee(ma_nv)
        if emp is None:
            return jsonify({
                "status":  "error",
                "message": "Khong tim thay nhan vien",
            }), 404

        existing = _db.count_face_embeddings(ma_nv)
        if existing > 0:
            return jsonify({
                "status":  "error",
                "message": f"Nhan vien da dang ky khuon mat ({existing} embedding). "
                           f"Dung endpoint re-register de dang ky lai.",
            }), 409

    if action == "start":
        try:
            import face_engine as _fe
            _fe.face_engine.initialize()
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 503
        session_id = secrets.token_urlsafe(24)
        with _enrollment_sessions_lock:
            _enrollment_sessions[session_id] = {"MaNV": ma_nv, "embeddings": [], "created": time.time()}
        return jsonify({"status": "success", "session_id": session_id,
                        "poses": list(_ENROLLMENT_POSES), "captured": 0}), 200

    if action in ("pose", "capture", "complete", "cancel"):
        session_id = data.get("session_id", "")
        with _enrollment_sessions_lock:
            state = _enrollment_sessions.get(session_id)
            if state and time.time() - state["created"] > _ENROLLMENT_SESSION_TTL:
                _enrollment_sessions.pop(session_id, None)
                state = None
            if state is None or state["MaNV"] != ma_nv:
                return jsonify({"status": "error", "message": "Session đăng ký không hợp lệ hoặc đã hết hạn."}), 400
            if action == "cancel":
                _enrollment_sessions.pop(session_id, None)
                return jsonify({"status": "success"}), 200
            expected_pose = _ENROLLMENT_POSES[len(state["embeddings"])] if len(state["embeddings"]) < len(_ENROLLMENT_POSES) else None
            if action == "pose":
                if expected_pose is None:
                    return jsonify({"status": "error", "message": "Đã chụp đủ 5 góc."}), 400
                ok, frame = _read_camera_frame()
                if not ok or frame is None:
                    return jsonify({"status": "error", **_pose_result({"current_pose": "no_frame"}, expected_pose),
                                    "instruction": "Không đọc được hình từ camera."}), 503
                try:
                    import face_engine as _fe
                    pose = _fe.face_engine.inspect_pose(frame)
                except Exception as exc:
                    return jsonify({"status": "error", "message": str(exc),
                                    **_pose_result({"current_pose": "unknown"}, expected_pose)}), 503
                return jsonify({"status": "success", **_pose_result(pose, expected_pose)}), 200
            if action == "capture":
                index = len(state["embeddings"])
                if index >= len(_ENROLLMENT_POSES):
                    return jsonify({"status": "error", "message": "Đã chụp đủ 5 góc."}), 400
                try:
                    if data.get("image"):
                        frame = _decode_face_image(data["image"])
                    else:
                        ok, frame = _read_camera_frame()
                        if not ok or frame is None:
                            return jsonify({"status": "error", "message": "Camera không khả dụng."}), 503
                    import face_engine as _fe
                    faces = _fe.face_engine.detect_embeddings(frame)
                    if not faces:
                        pose_result = _pose_result({"current_pose": "no_face"}, expected_pose)
                        return jsonify({"status": "error", "message": pose_result["instruction"], **pose_result}), 409
                    if len(faces) != 1:
                        pose_result = _pose_result({"current_pose": "multiple_faces"}, expected_pose)
                        return jsonify({"status": "error", "message": pose_result["instruction"], **pose_result}), 409
                    detected_pose = faces[0].get("head_pose")
                    if not detected_pose:
                        pose_result = _pose_result({"current_pose": "unknown"}, expected_pose)
                        return jsonify({"status": "error", "message": pose_result["instruction"], **pose_result}), 409
                    pose_result = _pose_result(detected_pose, expected_pose)
                    if not pose_result["pose_ok"]:
                        return jsonify({"status": "error", "message": pose_result["instruction"], **pose_result}), 409
                    vector_bytes = faces[0]["vector_bytes"]
                except Exception as exc:
                    return jsonify({"status": "error", "message": str(exc)}), 400
                state["embeddings"].append(vector_bytes)
                return jsonify({"status": "success", "captured": len(state["embeddings"]),
                                **pose_result,
                                "next_pose": _ENROLLMENT_POSES[len(state["embeddings"])]
                                if len(state["embeddings"]) < len(_ENROLLMENT_POSES) else None}), 200
            if len(state["embeddings"]) != len(_ENROLLMENT_POSES):
                return jsonify({"status": "error", "message": "Cần chụp đủ 5 góc trước khi lưu."}), 400
            embeddings = list(state["embeddings"])
        result = services.save_face_embeddings(ma_nv, embeddings)
        if result.get("success"):
            with _enrollment_sessions_lock:
                _enrollment_sessions.pop(session_id, None)
        code = 200 if result.get("success") else (409 if result.get("conflict") else 500)
        return jsonify({"status": "success" if result.get("success") else "error", **result}), code

@app.route('/api/face/identify', methods=['POST'])
@admin_required
def face_identify():
    data = request.get_json(silent=True) or {}
    try:
        frame = _decode_face_image(data.get("image"))
        result = services.identify_face_frame(frame, data.get("threshold"))
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503
    return jsonify(result), 200


@app.route('/api/face/verify', methods=['POST'])
@admin_required
def face_verify():
    data = request.get_json(silent=True) or {}
    if data.get("MaNV") is None:
        return jsonify({"status": "error", "message": "Thiếu MaNV."}), 400
    try:
        frame = _decode_face_image(data.get("image"))
        result = services.verify_face_frame(frame, data["MaNV"], data.get("threshold"))
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503
    return jsonify(result), 200


@app.route('/api/face/identify/camera', methods=['POST'])
@admin_required
def face_identify_camera():
    cam = get_camera()
    with _camera_lock:
        ok, frame = cam.read() if cam is not None and cam.isOpened() else (False, None)
    if not ok or frame is None:
        return jsonify({"status": "error", "message": "Camera không khả dụng."}), 503
    try:
        result = services.identify_face_frame(frame, (request.get_json(silent=True) or {}).get("threshold"))
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503
    return jsonify(result), 200


# ============================================================
# Routes — Trang cá nhân API
# ============================================================

@app.route('/api/me/attendance')
@login_required
def api_me_attendance():
    """GET /api/me/attendance — Chấm công cá nhân."""
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_my_attendance(ma_nv))


@app.route('/api/me/profile')
@login_required
def api_me_profile():
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_employee_profile(ma_nv))


@app.route('/api/me/today')
@login_required
def api_me_today():
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_my_today_status(ma_nv))


@app.route('/api/me/health')
@login_required
def api_me_health():
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_my_health(ma_nv))


@app.route('/api/me/alerts')
@login_required
def api_me_alerts():
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_my_alerts(ma_nv))


# ============================================================
# Entry point
# ============================================================

if __name__ == '__main__':
    # use_reloader=False để tránh khởi tạo camera 2 lần khi debug
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )
