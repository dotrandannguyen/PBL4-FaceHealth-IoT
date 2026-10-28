"""Real Flask routes, synthetic detector/OpenCV adapter; no model/camera/DB.

Use Python with Flask, requests, NumPy and Pillow. --extra-site may supply
pure-Python Flask/requests from an existing environment without installing.
"""
import argparse
import base64
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--extra-site', type=Path)
args, remaining = parser.parse_known_args()
if args.extra_site:
    sys.path.append(str(args.extra_site))
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'pbl4-face-ai'
sys.path.insert(0, str(ROOT))

def decode(data, flag):
    return np.array(Image.open(io.BytesIO(data.tobytes())).convert('RGB'))[:, :, ::-1].copy()

def encode(extension, frame, options):
    stream = io.BytesIO()
    Image.fromarray(frame[:, :, ::-1]).save(stream, format='JPEG')
    return True, np.frombuffer(stream.getvalue(), dtype=np.uint8)

adapter = types.SimpleNamespace(imdecode=decode, imencode=encode, IMREAD_COLOR=1, IMWRITE_JPEG_QUALITY=1)
with patch.dict(sys.modules, {'cv2': adapter}):
    import ai_web_service as service
from src.gallery_payload import build_gallery
from src.gallery_store import GalleryCache
from src.atomic_storage import save_gallery

def face(nose=(5, 5), embedding=None):
    return types.SimpleNamespace(kps=np.array([(0, 0), (10, 0), nose, (3, 10), (7, 10)], dtype=float),
        embedding=np.ones(512, dtype=np.float32) if embedding is None else embedding)

def sample(vector=None, employee=1, sample_id=1):
    raw = (np.ones(512, dtype='<f4') if vector is None else vector).tobytes()
    return dict(ma_nv=employee, ma_embedding=sample_id, so_chieu=512, ho_ten='Test',
                vector=base64.b64encode(raw).decode(), sha256=hashlib.sha256(raw).hexdigest())

class EnrollmentApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pbl4-ai-enrollment-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'gallery.pkl'
        for context in (patch.dict(os.environ, PBL4_INTERNAL_TOKEN='isolated-test-token'),
                        patch.object(service, 'EMBEDDINGS_PATH', self.path),
                        patch.object(service, '_engine', types.SimpleNamespace(detect=lambda img: self.faces))):
            context.start()
            self.addCleanup(context.stop)
        self.faces = [face()]
        self.client = service.app.test_client()
        self.headers = {'Authorization': 'Bearer isolated-test-token'}
        stream = io.BytesIO()
        Image.new('RGB', (8, 8), 'white').save(stream, format='PNG')
        self.payload = dict(image=base64.b64encode(stream.getvalue()).decode(), expected_pose='frontal')

    def post(self, endpoint='capture', **kwargs):
        return self.client.post('/api/ai/enrollment/' + endpoint,
                                headers=self.headers, json=kwargs or self.payload)

    def test_auth_and_no_store(self):
        for authorization in ('', 'Bearer wrong', 'Bearer tiêng'):
            response = self.client.post('/api/ai/enrollment/capture', json=self.payload,
                                       headers={'Authorization': authorization})
            self.assertEqual(response.status_code, 401)
            self.assertIn('no-store', response.headers['Cache-Control'])
        with patch.dict(os.environ, PBL4_INTERNAL_TOKEN=''):
            self.assertEqual(self.post().status_code, 503)

    def test_health_does_not_load_model(self):
        with patch.object(service, '_engine', None), patch.object(service, 'get_face_engine') as loader:
            self.assertFalse(self.client.get('/health').json['model_ready'])
            loader.assert_not_called()
        self.assertTrue(self.client.get('/health').json['model_ready'])

    def test_invalid_input_and_size(self):
        for payload in ({}, [], {'image': 'garbage'}, dict(self.payload, expected_pose='side')):
            self.assertEqual(self.client.post('/api/ai/enrollment/capture', headers=self.headers,
                                             json=payload).status_code, 400)
        with patch.dict(service.app.config, MAX_CONTENT_LENGTH=32):
            self.assertEqual(self.post().status_code, 413)
            self.assertEqual(self.post('inspect').status_code, 413)

    def test_face_count_pose_and_invalid_landmarks(self):
        for faces in ([], [face(), face()], [face((3, 5))], [face((float('nan'), 5))]):
            self.faces = faces
            self.assertEqual(self.post().status_code, 409)
        self.faces = [face((3, 5))]
        self.assertFalse(self.post('inspect').json['pose_ok'])
        self.assertEqual(self.post(expected_pose='left', image=self.payload['image']).status_code, 200)

    def test_capture_integrity_and_finite_unit_vector(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        data = response.json
        raw = base64.b64decode(data['vector'], validate=True)
        self.assertEqual(len(raw), 2048)
        self.assertAlmostEqual(float(np.linalg.norm(np.frombuffer(raw, dtype='<f4'))), 1, places=5)
        image = base64.b64decode(data['image_jpeg'], validate=True)
        self.assertEqual(data['image_sha256'], hashlib.sha256(image).hexdigest())
        self.assertEqual(Image.open(io.BytesIO(image)).format, 'JPEG')
        self.assertEqual(data['pose'], 'frontal')

    def test_invalid_vector_never_emits_sample(self):
        for vector in (np.zeros(512), np.full(512, np.nan), np.ones(511)):
            self.faces = [face(embedding=vector)]
            with self.assertLogs(service.app.logger, level='ERROR'):
                response = self.post()
            self.assertEqual(response.status_code, 500)
            self.assertNotIn('vector', response.json)

    def test_gallery_refresh_failure_and_deletion(self):
        save_gallery(self.path, {'SV999': {'name': 'Old'}})
        caches = [GalleryCache(), GalleryCache()]
        for cache in caches:
            cache.load(self.path)
        original = self.path.read_bytes()
        for status, payload in ((302, {}), (500, {}), (200, {'success': True, 'embeddings': [sample(vector=np.zeros(512))]})):
            response = types.SimpleNamespace(status_code=status, json=lambda: payload)
            with patch.object(service.requests, 'get', return_value=response), self.assertLogs(service.app.logger, level='ERROR'):
                self.assertEqual(self.client.post('/api/ai/gallery/refresh', headers=self.headers).status_code, 503)
            self.assertEqual(self.path.read_bytes(), original)
        for samples, expected in (([sample()], {'SV001'}), ([], set())):
            response = types.SimpleNamespace(status_code=200, json=lambda: {'success': True, 'embeddings': samples})
            with patch.object(service.requests, 'get', return_value=response) as fetch:
                self.assertEqual(self.client.post('/api/ai/gallery/refresh', headers=self.headers).status_code, 200)
                self.assertFalse(fetch.call_args.kwargs['allow_redirects'])
            for cache in caches:
                self.assertEqual(set(cache.load(self.path)), expected)

    def test_gallery_validation(self):
        valid = sample()
        for invalid in (dict(valid, ma_nv=True), dict(valid, sha256='bad'), dict(valid, so_chieu=511),
                        dict(valid, vector='not base64'), sample(vector=np.zeros(512)), sample(vector=np.full(512, np.nan))):
            with self.assertRaises((ValueError, TypeError)):
                build_gallery({'success': True, 'embeddings': [invalid]})
        with self.assertRaises(ValueError):
            build_gallery({'success': True, 'embeddings': [valid, valid]})
        gallery = build_gallery({'success': True, 'embeddings': [valid, sample(sample_id=2)]})
        self.assertEqual(set(gallery), {'SV001'})
        self.assertEqual(gallery['SV001']['n_images'], 2)

class CameraApiTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.timers = []
        test = self
        class Timer:
            def __init__(self, delay, callback):
                self.delay, self.callback, self.cancelled = delay, callback, False
                test.timers.append(self)
            def start(self): pass
            def cancel(self): self.cancelled = True
        self.cap = types.SimpleNamespace(isOpened=lambda: True, set=lambda *args: None,
            read=lambda: (True, np.zeros((8, 8, 3), dtype=np.uint8)), release=unittest.mock.Mock())
        self.factory = unittest.mock.Mock(return_value=self.cap)
        camera_cv = types.SimpleNamespace(VideoCapture=self.factory, CAP_DSHOW=700, CAP_MSMF=1400, CAP_ANY=0,
            CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4, imencode=encode, IMWRITE_JPEG_QUALITY=1)
        for context in (patch.dict(os.environ, PBL4_INTERNAL_TOKEN='camera-test-token', PBL4_CAMERA_MODE='local', CAMERA_SOURCE='local'),
                        patch.object(service, '_cap', None), patch.object(service, '_camera_idle_timer', None),
                        patch.object(service, '_camera_last_used', 0.0), patch.object(service, 'cv2', camera_cv),
                        patch.object(service.time, 'monotonic', lambda: self.now),
                        patch.object(service.threading, 'Timer', Timer)):
            context.start()
            self.addCleanup(context.stop)
        self.addCleanup(service.release_camera)
        self.client = service.app.test_client()
        self.headers = {'Authorization': 'Bearer camera-test-token'}

    def frame(self):
        return self.client.get('/internal/camera/frame', headers=self.headers)

    def test_health_and_unauthorized_requests_never_open_camera(self):
        self.assertFalse(self.client.get('/health').json['camera_open'])
        self.assertEqual(self.client.get('/internal/camera/frame').status_code, 401)
        self.factory.assert_not_called()

    def test_idle_camera_releases_without_more_requests_and_reopens_on_demand(self):
        self.assertEqual(self.frame().status_code, 200)
        self.assertTrue(self.client.get('/health').json['camera_open'])
        self.now += service.CAMERA_IDLE_SECONDS
        self.timers[-1].callback()
        self.cap.release.assert_called_once()
        self.assertFalse(self.client.get('/health').json['camera_open'])
        self.assertEqual(self.frame().status_code, 200)
        self.assertEqual(self.factory.call_count, 2)

    def test_active_clients_extend_idle_deadline_without_one_timer_per_frame(self):
        self.frame()
        first = self.timers[-1]
        self.now += 2
        self.frame()
        self.assertEqual(len(self.timers), 1)
        self.now += 1
        first.callback()
        self.cap.release.assert_not_called()
        self.assertEqual(self.timers[-1].delay, 2)
        self.now += 2
        self.timers[-1].callback()
        self.cap.release.assert_called_once()

    def test_stale_cancelled_timer_cannot_release_reopened_camera(self):
        self.frame()
        stale = self.timers[-1]
        service.release_camera()
        self.frame()
        current = self.timers[-1]
        self.now += 100
        stale.callback()
        self.assertIs(service._camera_idle_timer, current)
        self.assertEqual(self.cap.release.call_count, 1)
        current.callback()
        self.assertEqual(self.cap.release.call_count, 2)

    def test_failed_read_releases_immediately(self):
        self.cap.read = lambda: (False, None)
        self.assertEqual(self.frame().status_code, 503)
        self.cap.release.assert_called_once()
        self.assertIsNone(service._cap)
        self.assertTrue(self.timers[-1].cancelled)

    def test_read_exception_releases_immediately(self):
        self.cap.read = unittest.mock.Mock(side_effect=OSError('Camera disconnected'))
        self.assertEqual(self.frame().status_code, 503)
        self.cap.release.assert_called_once()
        self.assertIsNone(service._cap)

    def test_idle_callback_cannot_release_camera_during_frame_read(self):
        self.frame()
        timer = self.timers[-1]
        self.now += 3
        reading, finish = threading.Event(), threading.Event()
        result = []
        def read():
            reading.set()
            if not finish.wait(2):
                raise RuntimeError('Test frame read timeout')
            return True, np.zeros((8, 8, 3), dtype=np.uint8)
        self.cap.read = read
        def request_frame():
            with service.app.test_client() as client:
                result.append(client.get('/internal/camera/frame', headers=self.headers).status_code)
        worker = threading.Thread(target=request_frame)
        reaper = threading.Thread(target=timer.callback)
        worker.start()
        try:
            self.assertTrue(reading.wait(2))
            reaper.start()
            self.cap.release.assert_not_called()
        finally:
            finish.set()
            worker.join(2)
            if reaper.ident is not None:
                reaper.join(2)
        self.assertEqual(result, [200])
        self.cap.release.assert_not_called()
        self.now += 3
        self.timers[-1].callback()
        self.cap.release.assert_called_once()

    def test_camera_source_switch_releases_and_recreates(self):
        esp_cap = types.SimpleNamespace(
            isOpened=lambda: True,
            read=lambda: (True, np.zeros((8, 8, 3), dtype=np.uint8)),
            release=unittest.mock.Mock(),
        )
        with patch.object(service, 'CameraSource', return_value=esp_cap):
            # First request with local
            resp_local = self.client.get('/internal/camera/frame?source=local', headers=self.headers)
            self.assertEqual(resp_local.status_code, 200)
            self.assertEqual(self.client.get('/health').json['camera_source'], 'local')

            # Switch to esp32: old cap must be released and new esp32 opened
            resp_esp = self.client.get('/internal/camera/frame?source=esp32', headers=self.headers)
            self.assertEqual(resp_esp.status_code, 200)
            self.cap.release.assert_called_once()
            self.assertEqual(self.client.get('/health').json['camera_source'], 'esp32')


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + remaining)
