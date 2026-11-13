"""Frame source abstraction shared by webcam and future HTTP JPEG cameras."""

import threading
import time
from urllib.request import urlopen

import cv2
import numpy as np

from .config import CAMERA_HEIGHT, CAMERA_WIDTH


class CameraSource:
    def get_frame(self):
        """Return one BGR ndarray snapshot, or None when no frame is available."""
        raise NotImplementedError

    def release(self):
        raise NotImplementedError


class WebcamSource(CameraSource):
    """Windows webcam reader with a background capture thread for live preview."""

    def __init__(self, width=CAMERA_WIDTH, height=CAMERA_HEIGHT):
        self.width = int(width)
        self.height = int(height)
        self._capture = None
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._stop_event = threading.Event()
        self._reader_thread = None
        self.camera_index = None
        self.backend_name = None
        self._open_first_working_camera()

    @staticmethod
    def _backend_candidates():
        candidates = []
        for name in ("CAP_MSMF", "CAP_DSHOW"):
            backend = getattr(cv2, name, None)
            if backend is not None:
                candidates.append((name, backend))
        candidates.append(("default", None))
        return candidates

    def _open_first_working_camera(self):
        errors = []
        for backend_name, backend in self._backend_candidates():
            for index in range(6):
                capture = None
                try:
                    capture = (cv2.VideoCapture(index) if backend is None
                               else cv2.VideoCapture(index, backend))
                    if not capture.isOpened():
                        errors.append(f"{backend_name} index {index}: isOpened=False")
                        capture.release()
                        continue
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    buffer_property = getattr(cv2, "CAP_PROP_BUFFERSIZE", None)
                    if buffer_property is not None:
                        capture.set(buffer_property, 1)
                    ok, frame = capture.read()
                    if not ok or frame is None or getattr(frame, "size", 0) == 0:
                        errors.append(f"{backend_name} index {index}: no real frame")
                        capture.release()
                        continue
                    self._capture = capture
                    self.camera_index = index
                    self.backend_name = backend_name
                    with self._frame_lock:
                        self._latest_frame = frame
                    self._reader_thread = threading.Thread(
                        target=self._capture_loop, name="ai1-standalone-camera", daemon=True
                    )
                    self._reader_thread.start()
                    return
                except Exception as exc:
                    errors.append(f"{backend_name} index {index}: {exc}")
                    if capture is not None:
                        capture.release()
        detail = "; ".join(errors[-8:]) or "camera not found"
        raise RuntimeError(f"Could not open webcam (MSMF/DSHOW/default, indexes 0-5): {detail}")

    def _capture_loop(self):
        while not self._stop_event.is_set():
            capture = self._capture
            if capture is None:
                break
            try:
                ok, frame = capture.read()
            except Exception:
                ok, frame = False, None
            if ok and frame is not None and getattr(frame, "size", 0) > 0:
                with self._frame_lock:
                    self._latest_frame = frame
            else:
                with self._frame_lock:
                    self._latest_frame = None
                time.sleep(0.01)

    def get_frame(self):
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def release(self):
        self._stop_event.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2.0)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        with self._frame_lock:
            self._latest_frame = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.release()


class Esp32HttpSource(CameraSource):
    """Fetch one HTTP JPEG snapshot and decode it to the same BGR ndarray interface."""

    def __init__(self, snapshot_url, timeout=2.0, max_bytes=8 * 1024 * 1024):
        self.snapshot_url = str(snapshot_url)
        self.timeout = float(timeout)
        self.max_bytes = int(max_bytes)

    def get_frame(self):
        with urlopen(self.snapshot_url, timeout=self.timeout) as response:
            jpeg = response.read(self.max_bytes + 1)
        if not jpeg or len(jpeg) > self.max_bytes:
            return None
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        return frame if frame is not None and frame.size else None

    def release(self):
        return None
