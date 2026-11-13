"""Single-owner camera sources and a non-blocking latest-frame pump for AI1.

Frames are BGR ndarrays with a monotonic capture timestamp and a source sequence
number. Only this module opens VideoCapture; application routes consume the
shared FramePump instead of reading the device concurrently.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import socket
import sys
import threading
import time
from urllib.parse import urlsplit
import urllib.request

import cv2
import numpy as np


STALE_FRAME_SECONDS = 0.75
MAX_JPEG_BYTES = 5 * 1024 * 1024
DEFAULT_ESP32_STREAM_URL = "http://esp32cam.local:81/stream"


@dataclass(frozen=True)
class FramePacket:
    frame: np.ndarray
    sequence: int
    captured_at: float


class CameraSource:
    """Common interface for webcam and ESP32-CAM sources."""

    def get_frame(self) -> FramePacket | None:
        raise NotImplementedError

    def is_opened(self) -> bool:
        raise NotImplementedError

    def release(self) -> None:
        raise NotImplementedError


class WebcamSource(CameraSource):
    """Open one working Windows webcam, checking a real frame before selecting it."""

    def __init__(self, indexes=range(6), width=640, height=480, fps=30):
        self._capture = None
        self._lock = threading.Lock()
        self._sequence = 0
        self._first: FramePacket | None = None
        backends = ([cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
                    if sys.platform == "win32" else [cv2.CAP_ANY])
        for index in indexes:
            for backend in backends:
                capture = None
                try:
                    capture = cv2.VideoCapture(int(index), backend)
                    if not capture.isOpened():
                        capture.release()
                        continue
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    capture.set(cv2.CAP_PROP_FPS, fps)
                    packet = None
                    for _ in range(3):
                        ok, frame = capture.read()
                        if ok and isinstance(frame, np.ndarray) and frame.size:
                            packet = FramePacket(frame.copy(), 1, time.monotonic())
                            break
                    if packet is None:
                        capture.release()
                        continue
                    self._capture = capture
                    self._sequence = 1
                    self._first = packet
                    return
                except Exception:
                    if capture is not None:
                        capture.release()

    def is_opened(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    def get_frame(self) -> FramePacket | None:
        with self._lock:
            if self._first is not None:
                packet, self._first = self._first, None
                return packet
            if not self.is_opened():
                return None
            ok, frame = self._capture.read()
            if not ok or not isinstance(frame, np.ndarray) or frame.size == 0:
                return None
            self._sequence += 1
            return FramePacket(frame.copy(), self._sequence, time.monotonic())

    def release(self) -> None:
        with self._lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None


def validate_stream_url(url: str) -> str:
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise ValueError("ESP32-CAM stream URL is invalid.")
    parsed = urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("ESP32-CAM stream URL must be HTTP(S) without embedded credentials.")
    return url


class Esp32MjpegSource(CameraSource):
    """Reconnectable MJPEG reader that exposes only recent, decoded JPEG frames."""

    def __init__(self, url=DEFAULT_ESP32_STREAM_URL, stale_seconds=STALE_FRAME_SECONDS):
        self.url = validate_stream_url(url)
        self.stale_seconds = float(stale_seconds)
        self._lock = threading.Lock()
        self._running = True
        self._sequence = 0
        self._latest: FramePacket | None = None
        self._worker = threading.Thread(target=self._read_stream, daemon=True, name="ai1-esp32-mjpeg")
        self._worker.start()

    def is_opened(self) -> bool:
        return self._running

    def get_frame(self) -> FramePacket | None:
        with self._lock:
            packet = self._latest
            if packet is None or time.monotonic() - packet.captured_at > self.stale_seconds:
                return None
            return FramePacket(packet.frame.copy(), packet.sequence, packet.captured_at)

    def _connection_url(self) -> str:
        parsed = urlsplit(self.url)
        hostname = parsed.hostname or ""
        if hostname.endswith(".local"):
            try:
                address = socket.gethostbyname(hostname)
                return self.url.replace(hostname, address, 1)
            except OSError:
                return self.url
        return self.url

    def _decode_jpegs(self, buffer: bytearray) -> None:
        while self._running:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                if len(buffer) > MAX_JPEG_BYTES:
                    del buffer[:-1]
                return
            end = buffer.find(b"\xff\xd9", start + 2)
            if end < 0:
                if start:
                    del buffer[:start]
                if len(buffer) > MAX_JPEG_BYTES:
                    del buffer[:-1]
                return
            encoded = bytes(buffer[start:end + 2])
            del buffer[:end + 2]
            if len(encoded) > MAX_JPEG_BYTES:
                continue
            frame = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None or frame.ndim != 3 or frame.size == 0:
                continue
            with self._lock:
                self._sequence += 1
                self._latest = FramePacket(frame, self._sequence, time.monotonic())

    def _read_stream(self) -> None:
        while self._running:
            buffer = bytearray()
            try:
                request = urllib.request.Request(self._connection_url(), headers={"User-Agent": "AI1-CameraSource"})
                with urllib.request.urlopen(request, timeout=3.0) as response:
                    while self._running:
                        chunk = response.read(4096)
                        if not chunk:
                            break
                        buffer.extend(chunk)
                        self._decode_jpegs(buffer)
            except Exception:
                pass
            if self._running:
                time.sleep(0.5)

    def release(self) -> None:
        self._running = False
        worker = self._worker
        if worker.is_alive():
            worker.join(timeout=3.5)


class FramePump:
    """Read a source in the background and serve cloned, fresh latest snapshots."""

    def __init__(self, source: CameraSource, stale_seconds=STALE_FRAME_SECONDS):
        self.source = source
        self.stale_seconds = float(stale_seconds)
        self._lock = threading.Lock()
        self._running = True
        self._latest: FramePacket | None = None
        self._worker = threading.Thread(target=self._pump, daemon=True, name="ai1-frame-pump")
        self._worker.start()

    def is_opened(self) -> bool:
        return self._running and self.source.is_opened()

    def _pump(self) -> None:
        last_sequence = -1
        while self._running:
            try:
                packet = self.source.get_frame()
            except Exception:
                packet = None
            if packet is None or packet.sequence == last_sequence:
                time.sleep(0.01)
                continue
            if (not isinstance(packet.frame, np.ndarray) or packet.frame.ndim != 3
                    or packet.frame.shape[2] != 3 or packet.frame.size == 0):
                time.sleep(0.01)
                continue
            last_sequence = packet.sequence
            with self._lock:
                self._latest = FramePacket(packet.frame.copy(), packet.sequence, packet.captured_at)

    def get_frame(self) -> FramePacket | None:
        with self._lock:
            packet = self._latest
            if packet is None or time.monotonic() - packet.captured_at > self.stale_seconds:
                return None
            return FramePacket(packet.frame.copy(), packet.sequence, packet.captured_at)

    def release(self) -> None:
        self._running = False
        self.source.release()
        if self._worker.is_alive():
            self._worker.join(timeout=1.0)


def open_camera():
    source_type = os.getenv("AI1_CAMERA_SOURCE", "webcam").strip().lower()
    if source_type in {"esp32", "esp32cam", "mjpeg"}:
        source = Esp32MjpegSource(os.getenv("AI1_ESP32_STREAM_URL", DEFAULT_ESP32_STREAM_URL))
    elif source_type == "webcam":
        source = WebcamSource()
    else:
        raise ValueError("AI1_CAMERA_SOURCE must be webcam or esp32.")
    return FramePump(source)
