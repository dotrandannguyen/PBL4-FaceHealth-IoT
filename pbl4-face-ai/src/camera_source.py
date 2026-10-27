"""
camera_source.py — Universal Camera Source Adapter cho PBL4 FaceHealth IoT.
Hỗ trợ cả ESP32-CAM không dây (On-Demand MJPEG Stream trên Port 81) và Webcam máy tính.

Cung cấp interface tương thích hoàn toàn với cv2.VideoCapture:
  - isOpened() -> bool
  - read() -> (ret, frame)
  - release()
  - set(propId, value) -> bool

Tích hợp:
  - CameraSource: Bộ giải mã luồng video MJPEG thời gian thực (< 80ms) từ ESP32-CAM (mDNS esp32cam.local:81/stream)
  - RelayCamera: Relay luồng frame từ AI REST Service qua Bearer token nội bộ
  - open_camera: Hàm factory thống nhất cho toàn bộ hệ thống
  - FramePump: Luồng công nhân xử lý nền an toàn cho Tkinter và AI
"""

from __future__ import annotations
import io
import os
import sys
import time
import socket
import threading
import urllib.request
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
from PIL import Image

from .runtime_config import load_environment


# Đường dẫn mặc định
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
DEFAULT_ESP32_STREAM_URL = "http://esp32cam.local:81/stream"


class CameraSource:
    """
    Adapter tương thích cv2.VideoCapture cho cả Webcam và ESP32-CAM.
    Hỗ trợ On-Demand MJPEG Stream (15-25 FPS) siêu mượt không độ trễ.
    """

    def __init__(
        self,
        source: Union[int, str] = 0,
        stream_url: str = DEFAULT_ESP32_STREAM_URL,
        fallback_file: Optional[Path] = None,
        width: int = 1280,
        height: int = 720,
    ):
        self.source = source
        self.stream_url = stream_url
        self.fallback_file = fallback_file
        self.target_width = width
        self.target_height = height

        # Xác định chế độ: ESP32-CAM hay Webcam
        self.is_esp32 = (
            isinstance(source, str)
            and (source.lower() == "esp32" or source.startswith("http://") or source.startswith("https://"))
        )

        self._lock = threading.Lock()
        self._current_frame: Optional[np.ndarray] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._opened = False
        self._frame_count = 0
        self._last_frame_time = 0.0

        if self.is_esp32:
            if isinstance(source, str) and (source.startswith("http://") or source.startswith("https://")):
                self.stream_url = source
            self._init_esp32_stream()
        else:
            self._init_webcam()

    def _init_webcam(self):
        """Khởi tạo Webcam vật lý (Local OpenCV VideoCapture)."""
        idx = int(self.source) if isinstance(self.source, (int, str)) and str(self.source).isdigit() else 0
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(idx, backend)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(idx)

        if self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            self._opened = True
            print(f">> [CameraSource] Đã mở thành công Webcam (Index {idx}).")
        else:
            self._opened = False
            print(f">> [CameraSource] ❌ Không thể mở Webcam (Index {idx})!")

    def _init_esp32_stream(self):
        """Khởi tạo luồng nền giải mã On-Demand MJPEG Stream từ ESP32-CAM."""
        self._running = True
        self._opened = True
        self._current_frame = self._create_standby_frame()
        self._thread = threading.Thread(target=self._mjpeg_stream_worker, daemon=True, name="ESP32-MJPEG-Worker")
        self._thread.start()
        print(f">> [CameraSource] Đã kích hoạt On-Demand Stream Worker ({self.stream_url}).")

    def _resolve_ip(self, host: str) -> Optional[str]:
        """Phân giải mDNS hoặc DNS host thành địa chỉ IP thực tế."""
        try:
            return socket.gethostbyname(host)
        except Exception:
            return None

    def _mjpeg_stream_worker(self):
        """Luồng chuyên dụng đọc và giải mã dòng multipart/x-mixed-replace JPEG từ ESP32."""
        stream_bytes = b""
        cached_ip = None
        last_dns_check = 0.0

        while self._running:
            url_to_connect = self.stream_url

            # Tự động phân giải mDNS nếu url chứa tên miền .local
            if "esp32cam.local" in self.stream_url:
                now = time.time()
                if cached_ip is None or (now - last_dns_check > 3.0):
                    last_dns_check = now
                    resolved = self._resolve_ip("esp32cam.local")
                    if resolved:
                        cached_ip = resolved
                if cached_ip:
                    url_to_connect = self.stream_url.replace("esp32cam.local", cached_ip)

            try:
                req = urllib.request.Request(
                    url_to_connect,
                    headers={"User-Agent": "PBL4-FaceAI-Client", "Connection": "keep-alive"},
                )
                with urllib.request.urlopen(req, timeout=3.0) as stream:
                    stream_bytes = b""
                    while self._running:
                        chunk = stream.read(4096)
                        if not chunk:
                            break
                        stream_bytes += chunk

                        # Tìm header bắt đầu JPEG (0xFF 0xD8) và kết thúc JPEG (0xFF 0xD9)
                        a = stream_bytes.find(b"\xff\xd8")
                        if a != -1:
                            b = stream_bytes.find(b"\xff\xd9", a + 2)
                            if b != -1:
                                jpg = stream_bytes[a : b + 2]
                                stream_bytes = stream_bytes[b + 2 :]

                                if len(jpg) > 100:
                                    img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                    if img is not None and img.size > 0:
                                        with self._lock:
                                            self._current_frame = img
                                            self._frame_count += 1
                                            self._last_frame_time = time.time()
            except Exception:
                pass

            if not self._running:
                break

            time.sleep(0.5)  # Thử kết nối lại stream sau 0.5s

    def _create_standby_frame(self) -> np.ndarray:
        """Tạo khung hình chờ trực quan khi chưa có tín hiệu ESP32."""
        h, w = 480, 640
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        canvas[:] = (20, 24, 30)  # Nền xám đen công nghệ

        # Vẽ viền xanh
        cv2.rectangle(canvas, (10, 10), (w - 10, h - 10), (50, 60, 75), 2)

        # Tiêu đề
        title = "DANG CHO TIN HIEU ESP32-CAM..."
        cv2.putText(canvas, title, (80, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 215, 255), 2)

        # Hướng dẫn
        sub1 = "1. Kiem tra ESP32-CAM da bat nguon & ket noi WiFi"
        sub2 = "2. Ket noi cung mang 2.4GHz voi May tinh"
        sub3 = f"3. Dia chi Stream: {self.stream_url}"
        cv2.putText(canvas, sub1, (70, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        cv2.putText(canvas, sub2, (70, 275), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        cv2.putText(canvas, sub3, (70, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 180, 255), 1)

        # Chấm nhấp nháy báo hiệu đang kết nối
        blink = int(time.time() * 2) % 2 == 0
        dot_color = (0, 255, 100) if blink else (80, 80, 80)
        cv2.circle(canvas, (w // 2, 380), 8, dot_color, -1)

        return canvas

    def isOpened(self) -> bool:
        if self.is_esp32:
            return self._opened
        return bool(self._cap and self._cap.isOpened())

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.isOpened():
            return False, None

        if self.is_esp32:
            with self._lock:
                now = time.time()
                # Nếu mất kết nối quá 3.5s, trả về màn hình chờ động
                if self._last_frame_time > 0 and (now - self._last_frame_time > 3.5):
                    return True, self._create_standby_frame()
                if self._current_frame is not None:
                    return True, self._current_frame.copy()
            return True, self._create_standby_frame()
        else:
            ret, frame = self._cap.read()
            return ret, frame

    def set(self, propId: int, value: float) -> bool:
        if self._cap is not None:
            return self._cap.set(propId, value)
        return False

    def release(self):
        self._running = False
        self._opened = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class RelayCamera:
    """Relay kết nối camera qua AI REST Service nội bộ với Bearer token."""

    def __init__(self, url: str, token: str):
        import requests

        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers["Authorization"] = "Bearer " + token
        self.url = url
        self.opened = True

    def isOpened(self) -> bool:
        return self.opened

    def set(self, *args) -> bool:
        return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.opened:
            return False, None
        try:
            with self.session.get(self.url, timeout=(1, 1.5), stream=True, allow_redirects=False) as response:
                if (
                    response.status_code != 200
                    or response.headers.get("Content-Type", "").split(";")[0].strip().lower() != "image/jpeg"
                ):
                    return False, None
                limit = 5 * 1024 * 1024
                if int(response.headers.get("Content-Length", "0")) > limit:
                    return False, None
                content = bytearray()
                deadline = time.monotonic() + 2
                for chunk in response.iter_content(65536):
                    content.extend(chunk)
                    if len(content) > limit or time.monotonic() > deadline:
                        return False, None
                with Image.open(io.BytesIO(content)) as image:
                    if image.format != "JPEG" or image.width * image.height > 16000000:
                        return False, None
                    image.verify()
                frame = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
                return frame is not None, frame
        except Exception:
            return False, None

    def release(self):
        self.opened = False
        self.session.close()


def open_camera(camera_id=0):
    load_environment()
    mode = os.environ.get("PBL4_CAMERA_MODE", "relay")
    if mode not in ("auto", "relay", "local", "esp32"):
        raise ValueError("PBL4_CAMERA_MODE must be auto, relay, local or esp32")
    if str(camera_id).lower() == "esp32" or mode == "esp32":
        return CameraSource(source="esp32", width=1280, height=720)
    if isinstance(camera_id, str) and (camera_id.startswith("http://") or camera_id.startswith("https://")):
        return CameraSource(source=camera_id, width=1280, height=720)
    if mode == "local":
        import cv2
        return cv2.VideoCapture(camera_id)
    if camera_id != 0:
        raise ValueError("Set PBL4_CAMERA_MODE=local to select a local device")
    url = os.environ.get("PBL4_AI_URL", os.environ.get("AI_SERVICE_URL", "http://127.0.0.1:5001")).rstrip("/")
    return RelayCamera(url + "/internal/camera/frame", os.environ.get("PBL4_INTERNAL_TOKEN", ""))


class FramePump:
    """Worker đọc frame và phát hiện mặt ở thread nền, an toàn không gây lag GUI."""

    def __init__(self, factory, engine):
        self.factory = factory
        self.engine = engine
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.thread = threading.Thread(target=self.run, name="registration-camera", daemon=True)
        self.thread.start()

    def run(self):
        camera = None
        try:
            camera = self.factory()
            while not self.stop.is_set():
                try:
                    ok, frame = camera.read()
                    captured_at = time.monotonic()
                    engine = self.engine()
                    faces = engine.detect(frame) if ok and frame is not None and engine is not None else []
                    with self.lock:
                        self.latest = (frame if ok else None, faces, captured_at)
                except Exception:
                    with self.lock:
                        self.latest = (None, [], time.monotonic())
                self.stop.wait(0.03)
        except Exception:
            with self.lock:
                self.latest = (None, [], time.monotonic())
        finally:
            if camera is not None:
                camera.release()

    def snapshot(self, max_age: float = 0.75):
        frame, faces, _ = self.snapshot_with_timestamp(max_age)
        return frame, faces

    def snapshot_with_timestamp(self, max_age: float = 0.75):
        if self.stop.is_set():
            return None, [], None
        with self.lock:
            value = self.latest
        if value is None or time.monotonic() - value[2] > max_age:
            return None, [], None
        return value

    def close(self):
        self.stop.set()


def get_camera_source(source: Union[int, str] = 0, width: int = 1280, height: int = 720) -> CameraSource:
    """Factory helper khởi tạo CameraSource thuận tiện."""
    return CameraSource(source=source, width=width, height=height)
