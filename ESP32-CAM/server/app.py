from flask import Flask, request, jsonify, send_from_directory, render_template_string, Response
from pathlib import Path
from datetime import datetime
import os
import socket
import time
import threading

app = Flask(__name__)

# Thư mục lưu ảnh nhận từ ESP32-CAM
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "received_images"
UPLOAD_FOLDER.mkdir(exist_ok=True)
LATEST_IMAGE_PATH = BASE_DIR / "latest.jpg"

# Bộ đệm RAM lưu ảnh mới nhất
_frame_lock = threading.Lock()
latest_jpeg_bytes = None
latest_timestamp = 0.0
latest_client_ip = ""
latest_filename = ""

# Thông tin On-Demand Stream Server của ESP32-CAM
esp32_cam_ip = "192.168.1.14"
esp32_stream_port = 81
esp32_stream_url = f"http://{esp32_cam_ip}:{esp32_stream_port}/stream"

# Lấy địa chỉ IP LAN của máy tính
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.182"

LOCAL_IP = get_local_ip()

# Khởi tạo latest.jpg từ ảnh cũ nhất nếu có
if not latest_jpeg_bytes and LATEST_IMAGE_PATH.exists():
    try:
        latest_jpeg_bytes = LATEST_IMAGE_PATH.read_bytes()
        latest_timestamp = LATEST_IMAGE_PATH.stat().st_mtime
    except Exception:
        pass


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32-CAM Node 1 — Live Server Dashboard</title>
    <style>
        :root {
            --primary: #2563eb;
            --success: #16a34a;
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --border: #334155;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
        .container { max-width: 1100px; margin: 0 auto; }
        
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
        .badge { background: #064e3b; color: #34d399; padding: 6px 12px; border-radius: 999px; font-size: 0.85rem; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }
        .badge-dot { width: 8px; height: 8px; border-radius: 50%; background: #34d399; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 18px; }
        .card-title { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); margin-bottom: 8px; }
        .card-value { font-size: 1.25rem; font-weight: 700; color: #fff; word-break: break-all; }
        .code-box { background: #090d16; padding: 6px 10px; border-radius: 6px; font-family: Consolas, monospace; color: #38bdf8; font-size: 0.95rem; }

        .viewer-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
        @media (max-width: 800px) { .viewer-grid { grid-template-columns: 1fr; } }

        .main-viewer { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; align-items: center; }
        .image-container { width: 100%; aspect-ratio: 4/3; max-height: 480px; background: #000; border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; margin-top: 12px; position: relative; }
        .image-container img { width: 100%; height: 100%; object-fit: contain; }
        .no-image { color: var(--text-dim); text-align: center; }

        .recent-list { max-height: 480px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
        .recent-item { background: #0b1322; border: 1px solid var(--border); border-radius: 8px; padding: 10px; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: 0.2s; }
        .recent-item:hover { border-color: var(--primary); }
        .recent-item img { width: 60px; height: 45px; object-fit: cover; border-radius: 4px; background: #000; }
        .recent-info { flex: 1; font-size: 0.85rem; }
        .recent-time { color: var(--text-dim); font-size: 0.75rem; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1 style="font-size: 1.5rem; font-weight: 700;">📡 ESP32-CAM Node 1 — Live Server</h1>
                <p style="color: var(--text-dim); font-size: 0.9rem; margin-top: 4px;">PBL4: Hệ thống Nhận diện & Điểm danh IoT</p>
            </div>
            <div class="badge">
                <span class="badge-dot"></span> Server Online
            </div>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-title">Mạng WiFi Chung</div>
                <div class="card-value" style="color: #60a5fa;">📶 Phuong Thao</div>
                <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 4px;">Băng tần: 2.4 GHz</div>
            </div>
            <div class="card">
                <div class="card-title">Upload Endpoint (Cổng 5000)</div>
                <div class="code-box">http://{{ local_ip }}:5000/upload</div>
                <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 4px;">ESP32-CAM POST trực tiếp vào đây</div>
            </div>
            <div class="card">
                <div class="card-title">Chu kỳ chụp (Node 1)</div>
                <div class="card-value" style="color: #f59e0b;">⏱️ 3 giây / lần</div>
                <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 4px;">LED đỏ nhỏ báo hiệu (GPIO 33)</div>
            </div>
            <div class="card">
                <div class="card-title">Tổng số ảnh đã nhận</div>
                <div class="card-value" id="photoCount">0</div>
                <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 4px;" id="lastUpdate">Chờ ảnh đầu tiên...</div>
            </div>
        </div>

        <div class="viewer-grid">
            <div class="main-viewer">
                <div style="width: 100%; display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="font-size: 1.1rem; font-weight: 600;">📷 Ảnh mới nhất nhận được</h2>
                    <span id="currentFilename" style="font-size: 0.85rem; color: var(--text-dim); font-family: monospace;">---</span>
                </div>
                <div class="image-container">
                    <img id="liveImage" src="" alt="Live Stream" style="display: none;">
                    <div id="noImagePlaceholder" class="no-image">
                        <p style="font-size: 2rem; margin-bottom: 8px;">⏳</p>
                        <p>Đang chờ ESP32-CAM gửi ảnh...</p>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title" style="margin-bottom: 12px;">🕒 Lịch sử ảnh gần đây</div>
                <div class="recent-list" id="recentList">
                    <!-- Danh sách ảnh gần đây được chèn tự động -->
                </div>
            </div>
        </div>
    </div>

    <script>
        let lastFilename = "";

        async function fetchLatest() {
            try {
                const res = await fetch('/api/latest_image');
                const data = await res.json();
                
                document.getElementById('photoCount').innerText = data.total_count;
                
                if (data.latest) {
                    document.getElementById('lastUpdate').innerText = "Vừa nhận: " + data.latest.time;
                    if (data.latest.filename !== lastFilename) {
                        lastFilename = data.latest.filename;
                        const img = document.getElementById('liveImage');
                        img.src = '/images/' + data.latest.filename + '?t=' + new Date().getTime();
                        img.style.display = 'block';
                        document.getElementById('noImagePlaceholder').style.display = 'none';
                        document.getElementById('currentFilename').innerText = data.latest.filename + ' (' + data.latest.size_kb + ' KB)';
                        updateRecentList(data.recent);
                    }
                }
            } catch (err) {
                console.error("Lỗi cập nhật ảnh:", err);
            }
        }

        function updateRecentList(items) {
            const list = document.getElementById('recentList');
            if (!items || items.length === 0) return;
            list.innerHTML = items.map(item => `
                <div class="recent-item" onclick="viewPhoto('${item.filename}')">
                    <img src="/images/${item.filename}" alt="${item.filename}">
                    <div class="recent-info">
                        <div style="font-weight: 600;">${item.filename}</div>
                        <div class="recent-time">${item.time} • ${item.size_kb} KB</div>
                    </div>
                </div>
            `).join('');
        }

        function viewPhoto(filename) {
            lastFilename = filename;
            const img = document.getElementById('liveImage');
            img.src = '/images/' + filename;
            document.getElementById('currentFilename').innerText = filename;
        }

        // Tự động kiểm tra ảnh mới mỗi 1.5 giây
        setInterval(fetchLatest, 1500);
        fetchLatest();
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_TEMPLATE, local_ip=LOCAL_IP)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "ESP32-CAM Image Receiver",
        "has_frame": latest_jpeg_bytes is not None,
        "timestamp": int(time.time()),
    })

@app.route("/upload", methods=["POST"])
def upload_image():
    global latest_jpeg_bytes, latest_timestamp, latest_client_ip, latest_filename
    # Nhận dữ liệu ảnh JPEG thô từ ESP32-CAM
    image_data = request.get_data()

    if not image_data or len(image_data) < 100:
        return jsonify({
            "success": False,
            "message": "Không nhận được dữ liệu ảnh hợp lệ"
        }), 400

    filename = datetime.now().strftime("photo_%Y%m%d_%H%M%S_%f.jpg")
    file_path = UPLOAD_FOLDER / filename
    file_path.write_bytes(image_data)

    # Ghi đè file latest.jpg (atomic write)
    try:
        temp_latest = BASE_DIR / "latest.tmp"
        temp_latest.write_bytes(image_data)
        if temp_latest.exists():
            temp_latest.replace(LATEST_IMAGE_PATH)
    except Exception as e:
        try:
            LATEST_IMAGE_PATH.write_bytes(image_data)
        except Exception:
            pass

    # Cập nhật bộ đệm RAM thread-safe
    now_ts = time.time()
    with _frame_lock:
        latest_jpeg_bytes = image_data
        latest_timestamp = now_ts
        latest_client_ip = request.remote_addr or ""
        latest_filename = filename

    size_kb = round(len(image_data) / 1024, 1)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Đã nhận ảnh từ ESP32-CAM ({latest_client_ip}): {filename} ({size_kb} KB)")

    return jsonify({
        "success": True,
        "message": "Đã nhận ảnh thành công",
        "filename": filename,
        "size_bytes": len(image_data),
        "size_kb": size_kb
    }), 200

@app.route("/api/register_camera", methods=["POST"])
def register_camera():
    """Nhận báo danh IP và Port Stream Server từ ESP32-CAM khi kết nối WiFi."""
    global esp32_cam_ip, esp32_stream_port, esp32_stream_url, latest_timestamp, latest_client_ip
    data = request.get_json(silent=True) or {}
    ip = data.get("ip") or request.remote_addr or ""
    port = data.get("port", 81)
    stream_url = data.get("stream_url") or f"http://{ip}:{port}/stream"
    if ip:
        esp32_cam_ip = ip
        esp32_stream_port = port
        esp32_stream_url = stream_url
        latest_client_ip = ip
        latest_timestamp = time.time()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 Đã nhận báo danh ESP32-CAM: {ip}:{port} (Stream: {stream_url})")
    return jsonify({"success": True, "stream_url": esp32_stream_url})

@app.route("/api/camera_ip", methods=["GET"])
def api_camera_ip():
    """Cung cấp URL kết nối stream trực tiếp cho OpenCV Client và AI Dashboard."""
    return jsonify({
        "ip": esp32_cam_ip,
        "port": esp32_stream_port,
        "stream_url": esp32_stream_url,
        "capture_url": f"http://{esp32_cam_ip}:{esp32_stream_port}/capture",
        "status_url": f"http://{esp32_cam_ip}:{esp32_stream_port}/status",
    })

@app.route("/api/latest_frame.jpg", methods=["GET"])
def api_latest_frame_binary():
    """Trả về ảnh frame mới nhất: thử chụp trực tiếp từ ESP32 /capture trước, nếu không được fallback cache."""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://{esp32_cam_ip}:{esp32_stream_port}/capture", headers={"User-Agent": "Flask-Client"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = resp.read()
                if len(data) > 100:
                    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-cache"})
    except Exception:
        pass

    with _frame_lock:
        data = latest_jpeg_bytes

    if not data and LATEST_IMAGE_PATH.exists():
        try:
            data = LATEST_IMAGE_PATH.read_bytes()
        except Exception:
            data = None

    if not data:
        return Response(b"", status=404, mimetype="image/jpeg")

    return Response(data, mimetype="image/jpeg", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Timestamp": str(latest_timestamp),
    })

def gen_mjpeg_stream():
    """Tạo luồng video MJPEG fallback khi chưa kết nối được ESP32."""
    last_sent = 0.0
    while True:
        with _frame_lock:
            data = latest_jpeg_bytes
            ts = latest_timestamp

        if data is not None and ts != last_sent:
            last_sent = ts
            yield (
                b"--123456789000000000000987654321\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" +
                data + b"\r\n"
            )
        time.sleep(0.04)

@app.route("/video_feed", methods=["GET"])
def video_feed():
    """Proxy luồng MJPEG thời gian thực từ ESP32-CAM sang Browser."""
    import urllib.request
    def proxy_stream():
        try:
            req = urllib.request.Request(esp32_stream_url, headers={"User-Agent": "Flask-Proxy"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    yield chunk
        except Exception:
            yield from gen_mjpeg_stream()

    return Response(
        proxy_stream(),
        mimetype="multipart/x-mixed-replace; boundary=123456789000000000000987654321"
    )

@app.route("/api/camera_status", methods=["GET"])
def api_camera_status():
    """Kiểm tra trạng thái kết nối của ESP32-CAM."""
    now = time.time()
    diff = now - latest_timestamp if latest_timestamp > 0 else 999999.0
    is_online = (diff < 45.0)  # Heartbeat định kỳ 30s

    return jsonify({
        "online": is_online,
        "last_seen_sec": round(diff, 1) if latest_timestamp > 0 else None,
        "client_ip": esp32_cam_ip,
        "stream_url": esp32_stream_url,
        "timestamp": latest_timestamp,
    })

@app.route("/api/latest_image", methods=["GET"])
def api_latest_image():
    # Lấy danh sách ảnh trong thư mục sắp xếp mới nhất
    files = sorted(UPLOAD_FOLDER.glob("*.jpg"), key=lambda f: f.stat().st_mtime, reverse=True)
    total_count = len(files)
    
    latest_info = None
    recent_info = []

    if files:
        f_top = files[0]
        mtime = datetime.fromtimestamp(f_top.stat().st_mtime).strftime("%H:%M:%S %d/%m/%Y")
        latest_info = {
            "filename": f_top.name,
            "size_kb": round(f_top.stat().st_size / 1024, 1),
            "time": mtime
        }
        for f in files[:8]:
            recent_info.append({
                "filename": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%H:%M:%S")
            })

    return jsonify({
        "total_count": total_count,
        "latest": latest_info,
        "recent": recent_info
    })

@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    print(f"============================================================")
    print(f"🚀 ESP32-CAM Image Server đang chạy!")
    print(f"🔗 Truy cập Web Dashboard : http://localhost:5000")
    print(f"📡 Endpoint cho ESP32-CAM : http://{LOCAL_IP}:5000/upload")
    print(f"🎥 Luồng MJPEG Video Feed : http://localhost:5000/video_feed")
    print(f"🖼️ Ảnh JPEG mới nhất      : http://localhost:5000/api/latest_frame.jpg")
    print(f"📁 Thư mục lưu ảnh       : {UPLOAD_FOLDER}")
    print(f"============================================================")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

