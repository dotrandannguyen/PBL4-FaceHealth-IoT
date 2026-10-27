"""
camera_source.py — Universal Camera Source Adapter cho PBL4 FaceHealth IoT.
Hỗ trợ cả Webcam máy tính (Index 0, 1) và ESP32-CAM không dây (qua Flask Server Cổng 5000).

Cung cấp interface tương thích hoàn toàn với cv2.VideoCapture:
  - isOpened() -> bool
  - read() -> (ret, frame)
  - release()
Bổ sung các thuộc tính tiện ích:
  - is_esp32 (bool)
  - is_new_frame (bool)
  - last_frame_time (float)
"""

import sys
import os
import time
import threading
from pathlib import Path
from typing import Optional, Tuple, Union

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import cv2
import numpy as np


# Đường dẫn mặc định tới thư mục server ESP32
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
ESP32_SERVER_DIR = PROJECT_DIR / "ESP32-CAM" / "server"
LATEST_IMAGE_FILE = ESP32_SERVER_DIR / "latest.jpg"
DEFAULT_ESP32_URL = "http://127.0.0.1:5000/api/latest_frame.jpg"
DEFAULT_ESP32_STREAM_URL = "http://esp32cam.local:81/stream"


class CameraSource:
    """
    Adapter tương thích cv2.VideoCapture cho cả Webcam và ESP32-CAM.
    Hỗ trợ On-Demand MJPEG Stream (15-25 FPS) siêu mượt không độ trễ.
    """

    def __init__(
        self,
        source: Union[int, str] = 0,
        server_url: str = DEFAULT_ESP32_URL,
        fallback_file: Optional[Path] = LATEST_IMAGE_FILE,
        width: int = 1280,
        height: int = 720,
    ):
        self.source = source
        self.server_url = server_url
        self.stream_url = DEFAULT_ESP32_STREAM_URL
        self.fallback_file = fallback_file
        self.target_width = width
        self.target_height = height

        # Xác định chế độ ESP32
        source_str = str(source).strip().lower()
        self.is_esp32 = (
            source_str in ("esp32", "esp32-cam", "esp", "wifi", "network")
            or source_str.startswith("http://")
            or source_str.startswith("https://")
        )

        self._running = True
        self._cap: Optional[cv2.VideoCapture] = None
        self._http_stream = None
        
        # Biến trạng thái ESP32
        self._current_frame: Optional[np.ndarray] = None
        self._last_frame_mtime: float = 0.0
        self._last_read_ts: float = 0.0
        self._frame_count: int = 0
        self._last_read_frame_count: int = -1
        self._last_read_was_new: bool = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        if not self.is_esp32:
            # Chế độ Webcam tiêu chuẩn
            cam_idx = 0
            try:
                cam_idx = int(source)
            except Exception:
                cam_idx = 0
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            self._cap = cv2.VideoCapture(cam_idx, backend)
            if self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            print(f"[CameraSource] 📷 Đã mở Webcam Index {cam_idx} ({width}x{height})")
        else:
            # Tự động lấy URL stream mới nhất từ Server nếu có
            if source_str.startswith("http"):
                if "/stream" in source_str:
                    self.stream_url = source_str
                else:
                    self.server_url = source_str
            else:
                self._discover_stream_url()

            print(f"[CameraSource] 📡 Khởi động ESP32-CAM Reader (Stream: {self.stream_url})")
            self._thread = threading.Thread(target=self._esp32_worker, daemon=True)
            self._thread.start()

    def _discover_stream_url(self) -> None:
        """Tự động tìm kiếm ESP32-CAM qua tên miền mDNS (esp32cam.local) hoặc Flask Server."""
        import socket
        import urllib.request
        import json

        # 1. Thử phân giải tên miền mDNS: esp32cam.local
        try:
            resolved_ip = socket.gethostbyname("esp32cam.local")
            if resolved_ip:
                self.stream_url = f"http://esp32cam.local:81/stream"
                print(f"[CameraSource] 🎯 Đã tìm thấy ESP32-CAM qua mDNS (esp32cam.local -> {resolved_ip})")
                return
        except Exception:
            pass

        # 2. Nếu chưa thấy mDNS, hỏi Flask Server cổng 5000
        try:
            with urllib.request.urlopen("http://127.0.0.1:5000/api/camera_ip", timeout=0.8) as resp:
                if resp.status == 200:
                    info = json.loads(resp.read().decode())
                    if info.get("stream_url"):
                        self.stream_url = info["stream_url"]
                        return
        except Exception:
            pass

    def isOpened(self) -> bool:
        if not self.is_esp32:
            return self._cap is not None and self._cap.isOpened()
        return self._running

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.is_esp32:
            if self._cap is None:
                return False, None
            self._last_read_was_new = True
            return self._cap.read()

        # Đọc frame từ bộ đệm ESP32
        with self._lock:
            frame = self._current_frame
            is_new = (self._frame_count > 0 and self._frame_count != self._last_read_frame_count)
            if is_new:
                self._last_read_frame_count = self._frame_count
            self._last_read_was_new = is_new

        # Nếu đã quá 3.5 giây không có ảnh mới từ ESP32 -> xem như mất kết nối, hiển thị Standby
        if frame is not None and self.get_last_update_age() < 3.5:
            return True, frame.copy()

        # Nếu chưa nhận được frame nào từ ESP32 hoặc mất kết nối -> trả về ảnh chờ sinh động
        standby = self._create_standby_frame()
        return True, standby

    def is_new_frame(self) -> bool:
        """Kiểm tra xem frame vừa đọc từ lần gọi read() gần nhất có phải là frame mới nhận từ ESP32 hay không."""
        if not self.is_esp32:
            return True
        return self._last_read_was_new

    def get_last_update_age(self) -> float:
        """Thời gian trôi qua (giây) kể từ bức ảnh ESP32 gần nhất."""
        if self._last_frame_mtime <= 0:
            return 9999.0
        return max(0.0, time.time() - self._last_frame_mtime)

    def set(self, propId: int, value: float) -> bool:
        if self._cap is not None:
            return self._cap.set(propId, value)
        return True

    def get(self, propId: int) -> float:
        if self._cap is not None:
            return self._cap.get(propId)
        return 0.0

    def release(self) -> None:
        self._running = False
        if self._http_stream is not None:
            try:
                self._http_stream.close()
            except Exception:
                pass
            self._http_stream = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        print("[CameraSource] Đã giải phóng Camera Source (Đã gửi tín hiệu ngắt kết nối tới ESP32).")

    # -------------------------------------------------------------------------
    # LUỒNG NỀN ĐỌC MJPEG STREAM HOẶC POLLING TỪ ESP32
    # -------------------------------------------------------------------------
    def _esp32_worker(self) -> None:
        """Đọc luồng video MJPEG thời gian thực từ ESP32-CAM với độ trễ 0ms."""
        import urllib.request

        while self._running:
            # Thử làm mới địa chỉ mDNS nếu đang ở URL mặc định
            if "esp32cam.local" in self.stream_url:
                self._discover_stream_url()

            # 1. Thử kết nối trực tiếp vào luồng MJPEG Server của ESP32 (Port 81)
            try:
                req = urllib.request.Request(self.stream_url, headers={"User-Agent": "OpenCV-Client"})
                self._http_stream = urllib.request.urlopen(req, timeout=3.0)
                stream_bytes = b""
                print(f"[CameraSource] 🟢 Đã kết nối luồng Video Stream: {self.stream_url} (15-25 FPS)")

                while self._running:
                    chunk = self._http_stream.read(4096)
                    if not chunk:
                        break
                    stream_bytes += chunk
                    
                    a = stream_bytes.find(b"\xff\xd8")  # JPEG Start of Image
                    if a != -1:
                        b = stream_bytes.find(b"\xff\xd9", a + 2)  # JPEG End of Image (sau SOI)
                        if b != -1:
                            jpg_bytes = stream_bytes[a : b + 2]
                            stream_bytes = stream_bytes[b + 2 :]
                            
                            img = cv2.imdecode(np.frombuffer(jpg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if img is not None and img.size > 0:
                                with self._lock:
                                    self._current_frame = img
                                    self._frame_count += 1
                                    self._last_frame_mtime = time.time()
                        elif len(stream_bytes) > 200000:
                            # Tránh phình to bộ nhớ nếu mất gói EOI
                            stream_bytes = stream_bytes[a:]
                    elif len(stream_bytes) > 50000:
                        stream_bytes = b""
                
                if self._http_stream is not None:
                    try:
                        self._http_stream.close()
                    except Exception:
                        pass
                    self._http_stream = None

            except Exception:
                # 2. Nếu luồng stream chưa sẵn sàng, fallback đọc qua Flask Server (Port 5000)
                pass

            if not self._running:
                break

            # Fallback polling nếu stream chưa online (chỉ chấp nhận ảnh mới trong 3 giây)
            try:
                raw_bytes = None
                now = time.time()
                if self.fallback_file and self.fallback_file.exists():
                    mtime = self.fallback_file.stat().st_mtime
                    if mtime != self._last_frame_mtime and (now - mtime < 4.0):
                        raw_bytes = self.fallback_file.read_bytes()
                        self._last_frame_mtime = mtime
                if raw_bytes is None:
                    req2 = urllib.request.Request(self.server_url, headers={"User-Agent": "PBL4-Fallback"})
                    with urllib.request.urlopen(req2, timeout=0.8) as resp:
                        if resp.status == 200:
                            content = resp.read()
                            if len(content) > 100:
                                raw_bytes = content
                                self._last_frame_mtime = time.time()

                if raw_bytes and len(raw_bytes) > 100:
                    img = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
                    if img is not None and img.size > 0:
                        with self._lock:
                            self._current_frame = img
                            self._frame_count += 1
            except Exception:
                pass

            time.sleep(0.5)  # Thử kết nối lại stream sau 0.5s

    def _create_standby_frame(self) -> np.ndarray:
        """Tạo khung hình chờ khi chưa có tín hiệu ESP32."""
        h, w = 480, 640
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        canvas[:] = (20, 24, 30)  # Nền xám đen sang trọng

        # Vẽ viền xanh
        cv2.rectangle(canvas, (10, 10), (w - 10, h - 10), (50, 60, 75), 2)

        # Tiêu đề
        title = "DANG CHO TIN HIEU ESP32-CAM..."
        cv2.putText(canvas, title, (80, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 215, 255), 2)

        # Hướng dẫn
        sub1 = "1. Kiem tra ESP32-CAM da bat nguon & ket noi WiFi"
        sub2 = "2. Dam bao Server dang chay tren Cong 5000"
        sub3 = f"Server Endpoint: {self.server_url}"
        cv2.putText(canvas, sub1, (70, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        cv2.putText(canvas, sub2, (70, 275), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        cv2.putText(canvas, sub3, (70, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 180, 255), 1)

        # Chấm nhấp nháy báo hiệu đang kết nối
        blink = int(time.time() * 2) % 2 == 0
        dot_color = (0, 255, 100) if blink else (80, 80, 80)
        cv2.circle(canvas, (w // 2, 380), 8, dot_color, -1)

        return canvas


def get_camera_source(source: Union[int, str] = 0, width: int = 1280, height: int = 720) -> CameraSource:
    """Factory helper khởi tạo CameraSource thuận tiện."""
    return CameraSource(source=source, width=width, height=height)
