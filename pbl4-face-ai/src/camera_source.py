"""The AI service owns the camera unless local mode is explicitly selected."""
import io
import os
import threading
import time
from .runtime_config import load_environment


class RelayCamera:
    def __init__(self, url, token):
        import requests
        self.session = requests.Session()
        self.session.trust_env = False  # Internal bearer tokens must not go to an environment proxy.
        self.session.headers['Authorization'] = 'Bearer ' + token
        self.url, self.opened = url, True

    def isOpened(self):
        return self.opened

    def set(self, *args):
        return False

    def read(self):
        if not self.opened:
            return False, None
        try:
            import cv2
            import numpy as np
            from PIL import Image
            with self.session.get(self.url, timeout=(1, 1.5), stream=True, allow_redirects=False) as response:
                if response.status_code != 200 or response.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'image/jpeg':
                    return False, None
                limit = 5 * 1024 * 1024
                if int(response.headers.get('Content-Length', '0')) > limit:
                    return False, None
                content = bytearray()
                deadline = time.monotonic() + 2
                for chunk in response.iter_content(65536):
                    content.extend(chunk)
                    if len(content) > limit or time.monotonic() > deadline:
                        return False, None
                with Image.open(io.BytesIO(content)) as image:
                    if image.format != 'JPEG' or image.width * image.height > 16000000:
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
    mode = os.environ.get('PBL4_CAMERA_MODE', 'relay')
    if mode not in ('auto', 'relay', 'local'):
        raise ValueError('PBL4_CAMERA_MODE must be auto, relay or local')
    if mode == 'local':
        import cv2
        return cv2.VideoCapture(camera_id)
    if camera_id != 0:
        raise ValueError('Set PBL4_CAMERA_MODE=local to select a local device')
    # Legacy auto now also requires relay; a failed probe must not open a second
    # camera while the service is starting or temporarily unavailable.
    url = os.environ.get('PBL4_AI_URL', os.environ.get('AI_SERVICE_URL', 'http://127.0.0.1:5001')).rstrip('/')
    return RelayCamera(url + '/internal/camera/frame', os.environ.get('PBL4_INTERNAL_TOKEN', ''))


class FramePump:
    """Single reader/detector worker, one latest snapshot, no Tk calls."""
    def __init__(self, factory, engine):
        self.factory, self.engine = factory, engine
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.thread = threading.Thread(target=self.run, name='registration-camera', daemon=True)
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
                self.stop.wait(.03)
        except Exception:
            with self.lock:
                self.latest = (None, [], time.monotonic())
        finally:
            if camera is not None:
                camera.release()

    def snapshot(self, max_age=.75):
        if self.stop.is_set():
            return None, []
        with self.lock:
            value = self.latest
        if value is None or time.monotonic() - value[2] > max_age:
            return None, []
        return value[0], value[1]

    def close(self):
        self.stop.set()
