"""UI controller that composes the existing standalone store and AI1 core."""

import os
import threading
import time
import uuid

import numpy as np

from camera_source import Esp32MjpegSource, FramePacket, FramePump, WebcamSource, validate_stream_url
import face_matching
from ai1_standalone_core.ai1_adapter import initialize_ai1
from ai1_standalone_core.config import RECOGNITION_THRESHOLD
from ai1_standalone_core.data_store import StandaloneStore
from ai1_standalone_core.recognition import recognize_sequence_from_source, recognize_three_embeddings


class DuplicateFaceError(ValueError):
    """Raised when enrollment would assign an existing face to another ID."""

    def __init__(self, duplicate):
        self.duplicate = dict(duplicate)
        super().__init__("Khuôn mặt đã tồn tại trong gallery standalone.")


def create_camera_source(source_type="webcam", stream_url=None):
    source_type = str(source_type).strip().lower()
    if source_type == "webcam":
        return FramePump(WebcamSource())
    if source_type in {"esp32", "esp32cam"}:
        url = stream_url or os.getenv("AI1_ESP32_STREAM_URL", "http://esp32cam.local:81/stream")
        return FramePump(Esp32MjpegSource(validate_stream_url(url)))
    raise ValueError("Camera source must be webcam or esp32.")


class AI1GuiController:
    """Own one buffalo_l engine, one local gallery, and one replaceable frame source."""

    def __init__(self, store=None, camera_factory=None, source_factory=None,
                 threshold=RECOGNITION_THRESHOLD):
        self.store = store or StandaloneStore()
        # camera_factory remains a small injection hook for the hardware-free tests.
        self.camera_factory = camera_factory
        self.source_factory = source_factory or create_camera_source
        self.threshold = float(threshold)
        self.engine = None
        self.source = None
        self.source_type = "webcam"
        self.stream_url = os.getenv("AI1_ESP32_STREAM_URL", "http://esp32cam.local:81/stream")
        self.employees = []
        self.gallery = {}
        self.ready = False
        self.camera_error = None
        self._lock = threading.RLock()
        self._camera_lock = threading.RLock()
        self._session_lock = threading.Lock()
        self._active_session_id = None
        self._legacy_sequence = 0

    def startup(self, stop_event=None):
        """Load local data first, initialize buffalo_l once, then try the camera."""
        stop_event = stop_event or threading.Event()
        self.store.ensure()
        employees, gallery = self.store.load()
        with self._lock:
            self.employees = employees
            self.gallery = gallery

        # Keep the standalone list/gallery available even if model initialization fails.
        self.engine = initialize_ai1()
        with self._lock:
            self.ready = True

        if stop_event.is_set():
            return self.snapshot()
        try:
            self._open_camera("webcam", self.stream_url)
        except Exception as exc:
            # Model/gallery remain available to the GUI so camera setup can be retried.
            with self._camera_lock:
                self.source = None
            self.camera_error = str(exc)
        return self.snapshot()

    def snapshot(self):
        with self._lock, self._camera_lock:
            source = self.source
            opened = bool(source is not None and (not hasattr(source, "is_opened") or source.is_opened()))
            return {
                "ready": self.ready,
                "employees": list(self.employees),
                "gallery": self.gallery,
                "camera_available": opened,
                "camera_error": self.camera_error,
                "camera_type": self.source_type,
                "stream_url": self.stream_url,
                "threshold": self.threshold,
            }

    def get_packet(self):
        """Return one cloned, fresh BGR FramePacket from the configured FramePump."""
        with self._camera_lock:
            source = self.source
        if source is None:
            return None
        packet = source.get_frame()
        if isinstance(packet, FramePacket):
            return packet
        # Support injected/legacy CLI sources. The desktop default always uses FramePump.
        if isinstance(packet, np.ndarray) and packet.ndim == 3 and packet.shape[2] == 3:
            self._legacy_sequence += 1
            return FramePacket(packet.copy(), self._legacy_sequence, time.monotonic())
        return None

    def _open_camera(self, source_type, stream_url):
        with self._camera_lock:
            old_source, self.source = self.source, None
        if old_source is not None:
            old_source.release()
        if self.camera_factory is not None:
            if source_type != "webcam":
                raise RuntimeError("ESP32 source selection needs the shared camera_source adapter.")
            new_source = self.camera_factory()
        else:
            new_source = self.source_factory(source_type, stream_url)
        with self._camera_lock:
            self.source = new_source
            self.source_type = source_type
            self.stream_url = stream_url
            self.camera_error = None
        return self.snapshot()

    def change_camera(self, source_type, stream_url=None):
        source_type = str(source_type).strip().lower()
        if source_type not in {"webcam", "esp32", "esp32cam"}:
            raise ValueError("Camera source must be webcam or esp32.")
        url = stream_url or self.stream_url
        if source_type in {"esp32", "esp32cam"}:
            url = validate_stream_url(url)
            source_type = "esp32"
        else:
            source_type = "webcam"
        try:
            return self._open_camera(source_type, url)
        except Exception as exc:
            self.camera_error = str(exc)
            raise

    def refresh_data(self):
        employees, gallery = self.store.load()
        with self._lock:
            self.employees = employees
            self.gallery = gallery
        return self.snapshot()

    def register_employee(self, identity, name, embeddings_by_pose, staged_images, overwrite=False):
        frontal = embeddings_by_pose.get("frontal") if isinstance(embeddings_by_pose, dict) else None
        with self._lock:
            if frontal is not None:
                duplicate = self.find_duplicate_employee(frontal, exclude_identity=identity)
                if duplicate is not None:
                    raise DuplicateFaceError(duplicate)
            employees, gallery = self.store.add_employee(
                identity, name, embeddings_by_pose, staged_images, overwrite=overwrite
            )
            self.employees = employees
            self.gallery = gallery
        return self.snapshot()

    def find_duplicate_employee(self, embedding, exclude_identity=None):
        """Find a different local employee matching by cosine / MAX sample score."""
        with self._lock:
            gallery = {
                identity: person for identity, person in self.gallery.items()
                if exclude_identity is None or str(identity) != str(exclude_identity)
            }
            threshold = self.threshold
        result = face_matching.identify_embedding(embedding, gallery, threshold)
        if not result["match"]:
            return None
        return {
            "MaNV": result["MaNV"],
            "HoTen": result["HoTen"],
            "similarity": float(result["similarity"]),
            "threshold": float(result["threshold"]),
        }

    def delete_employee(self, identity, confirmed=False):
        employees, gallery = self.store.delete_employee(identity, confirmed=confirmed)
        with self._lock:
            self.employees = employees
            self.gallery = gallery
        return self.snapshot()

    def begin_session(self, session_id=None):
        session_id = session_id or uuid.uuid4().hex
        with self._session_lock:
            if self._active_session_id is not None:
                return None
            self._active_session_id = session_id
            return session_id

    def end_session(self, session_id):
        with self._session_lock:
            if session_id is not None and self._active_session_id == session_id:
                self._active_session_id = None
                return True
            return False

    def recognize(self, stop_event, progress_callback=None, session_id=None, frame_callback=None):
        own_session = session_id is None
        if own_session:
            session_id = self.begin_session()
            if session_id is None:
                raise RuntimeError("Another AI1 session is already running.")
        else:
            with self._session_lock:
                if self._active_session_id != session_id:
                    raise RuntimeError("The recognition session is no longer active.")
        try:
            with self._lock:
                engine = self.engine
                gallery = self.gallery
                ready = self.ready
            with self._camera_lock:
                source = self.source
            if not ready or engine is None:
                raise RuntimeError("ArcFace is not ready yet.")
            if source is None:
                raise RuntimeError(self.camera_error or "Camera is unavailable.")
            return recognize_sequence_from_source(
                engine, source, gallery, stop_event, threshold=self.threshold,
                progress_callback=progress_callback, frame_callback=frame_callback,
            )
        finally:
            if own_session:
                self.end_session(session_id)

    @staticmethod
    def recognize_embeddings(embeddings, gallery, threshold=RECOGNITION_THRESHOLD,
                             sharpnesses=None):
        """Expose the same 3-frame consistency/best-frame/MAX path to pure tests."""
        return recognize_three_embeddings(embeddings, gallery, threshold, sharpnesses=sharpnesses)

    def release(self):
        with self._camera_lock:
            source, self.source = self.source, None
        if source is not None:
            source.release()
