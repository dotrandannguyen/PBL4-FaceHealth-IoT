"""Receiver regression tests; generated JPEGs and storage are temporary."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pbl4_upload', ROOT/'PhanCung/esp32_server/app.py')
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pbl4-upload-test-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)/'images'
        self.app = receiver.create_app({'TESTING': True, 'UPLOAD_FOLDER': self.folder,
                                       'UPLOAD_TOKEN': 'test-only-upload-token'})
        stream = io.BytesIO()
        Image.new('RGB', (12, 12), 'blue').save(stream, 'JPEG')
        self.jpeg = stream.getvalue()

    def post(self, data=None, token='test-only-upload-token', content_type='image/jpeg', **headers):
        if token is not None:
            headers['Authorization'] = 'Bearer '+token
        with self.app.test_client() as client:
            return client.post('/upload', data=self.jpeg if data is None else data,
                               content_type=content_type, headers=headers)

    def test_authentication_and_missing_configuration(self):
        for token in (None, '', 'wrong'):
            self.assertEqual(self.post(token=token).status_code, 401)
        self.app.config['UPLOAD_TOKEN'] = ''
        self.assertEqual(self.post().status_code, 503)
        self.assertFalse(self.folder.exists())

    def test_media_empty_invalid_png_and_truncated(self):
        self.assertEqual(self.post(content_type='application/octet-stream').status_code, 415)
        png = io.BytesIO()
        Image.new('RGB', (8, 8)).save(png, 'PNG')
        for data in (b'', b'not a jpeg', png.getvalue(), self.jpeg[:100]):
            self.assertEqual(self.post(data=data).status_code, 400)
        self.assertFalse(self.folder.exists())

    def test_request_limit_and_dimensions(self):
        self.app.config['MAX_CONTENT_LENGTH'] = 100
        response = self.post()
        self.assertEqual(response.status_code, 413)
        self.assertFalse(response.json['success'])
        self.app.config['MAX_CONTENT_LENGTH'] = 5*1024*1024
        with patch.object(receiver.Image, 'open') as opened:
            image = opened.return_value.__enter__.return_value
            image.format, image.width, image.height = 'JPEG', 5000, 5000
            self.assertEqual(self.post().status_code, 400)
            image.load.assert_not_called()

    def test_exact_bytes_hash_unique_names_and_untrusted_filename(self):
        first = self.post(**{'X-Filename': '../../outside.jpg'})
        second = self.post()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.json['filename'], second.json['filename'])
        for response in (first, second):
            self.assertRegex(response.json['filename'], r'^[0-9a-f]{32}\.jpg$')
            self.assertEqual((self.folder/response.json['filename']).read_bytes(), self.jpeg)
            self.assertEqual(response.json['sha256'], hashlib.sha256(self.jpeg).hexdigest())
            self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertFalse((self.folder.parent/'outside.jpg').exists())

    def test_byte_and_count_quotas_preserve_existing_images(self):
        self.app.config['MAX_STORED_BYTES'] = len(self.jpeg)-1
        self.assertEqual(self.post().status_code, 507)
        self.app.config['MAX_STORED_BYTES'] = len(self.jpeg)*4
        self.app.config['MAX_STORED_IMAGES'] = 1
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 507)
        self.assertEqual(len(list(self.folder.glob('*.jpg'))), 1)

    def test_concurrent_quota_is_atomic(self):
        self.app.config['MAX_STORED_IMAGES'] = 2
        with ThreadPoolExecutor(max_workers=6) as workers:
            statuses = list(workers.map(lambda _: self.post().status_code, range(8)))
        self.assertEqual(statuses.count(200), 2)
        self.assertEqual(statuses.count(507), 6)
        self.assertEqual(len(list(self.folder.glob('*.jpg'))), 2)

    def test_storage_failure_is_generic_and_preserves_files(self):
        with patch.object(receiver, 'atomic_write', side_effect=OSError('private storage detail')):
            with self.assertLogs(receiver.app.name, level='ERROR'):
                response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private storage detail', response.get_data(as_text=True))
        self.assertEqual(list(self.folder.glob('*.jpg')), [])

    def test_health_has_no_secrets(self):
        with self.app.test_client() as client:
            response = client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['service'], 'PBL4 JPEG receiver')
        self.assertNotIn('token', response.get_data(as_text=True).lower())


if __name__ == '__main__':
    unittest.main()
