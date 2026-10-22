"""Desktop tests with real NumPy/Pillow/requests; fake inference/camera.
--database may only be passed by the isolated MariaDB runner.
"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--extra-site', type=Path)
parser.add_argument('--database', action='store_true')
args, remaining = parser.parse_known_args()
if args.extra_site:
    sys.path.append(str(args.extra_site))
import numpy as np
import requests  # Load before temporary sys.modules adapters to keep CookieJar classes stable.
from PIL import Image
from PIL import ImageTk
import tkinter
ROOT = Path(__file__).resolve().parents[1] / 'pbl4-face-ai'
sys.path.insert(0, str(ROOT))
from src import face_sync
from src.atomic_storage import save_gallery
from src.desktop_enrollment import DesktopEnrollment
from src.enrollment_samples import sample_from_frame, prepare_samples
from src.enrollment_pose import POSES
from src.gallery_payload import gallery_revision
from src.gallery_store import GalleryCache
from src.camera_source import RelayCamera, open_camera


def image_bytes(color=0, format='JPEG'):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), (color, color, color)).save(buffer, format=format)
    return buffer.getvalue()

def face(index=0, axis=0):
    nose = [(5,5),(3,5),(7,5),(5,3),(5,8)][index]
    vector = np.zeros(512)
    vector[axis] = 1
    vector[index + 10] = .1
    return types.SimpleNamespace(kps=np.array([(0,0),(10,0),nose,(3,10),(7,10)],float), embedding=vector)

def samples(color=0):
    return [dict(pose=pose, vector=face(index).embedding, image=image_bytes(color + index)) for index, pose in enumerate(POSES)]

def encode(extension, frame, options):
    buffer = io.BytesIO()
    Image.fromarray(frame[:,:,::-1]).save(buffer, format='JPEG')
    return True, np.frombuffer(buffer.getvalue(), dtype=np.uint8)

def decode(raw, flag):
    return np.array(Image.open(io.BytesIO(raw.tobytes())).convert('RGB'))[:,:,::-1].copy()

CV = types.SimpleNamespace(imencode=encode, imdecode=decode, IMWRITE_JPEG_QUALITY=1, IMREAD_COLOR=1)


class PendingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pbl4-desktop-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = DesktopEnrollment(self.root/'jobs', self.root/'gallery.pkl')

    def test_stage_has_paired_images_and_does_not_publish_unconfirmed_faces(self):
        self.store.stage('NV001', 'Test', samples())
        self.assertFalse(self.store.gallery_path.exists())
        path, job = self.store.pending()[0]
        self.assertEqual(job['employee_id'], 1)
        for source, saved in zip(samples(), job['samples']):
            self.assertEqual(source['image'], base64.b64decode(saved['image']))
            self.assertEqual(hashlib.sha256(source['image']).hexdigest(), saved['image_sha256'])
        with self.assertRaises(ValueError):
            self.store.stage('SV001', 'Another', samples())
        self.assertTrue(path.exists())

    def test_capture_revision_is_frozen_before_web_updates_during_capture(self):
        revision = self.store.revision(1)
        save_gallery(self.store.gallery_path, {'SV001': {'name': 'New Web registration', 'revision': 'b'*64}})
        self.store.stage(1, 'Old capture', samples(), revision)
        self.assertEqual(self.store.pending()[0][1]['expected_revision'], revision)

    def test_invalid_batch_or_legacy_gallery_preserves_existing_work(self):
        for batch in (samples()[:2], [dict(s, pose='frontal') for s in samples()],
                      [dict(s, vector=np.zeros(512)) for s in samples()],
                      [dict(s, image=b'fake') for s in samples()]):
            with self.assertRaises(ValueError):
                self.store.stage(1, 'Test', batch)
        bad = samples()
        bad[1]['vector'] = face(1, axis=2).embedding
        with self.assertRaises(ValueError):
            self.store.stage(1, 'Test', bad)
        save_gallery(self.store.gallery_path, {'SV001': {'name': 'Legacy'}})
        before = self.store.gallery_path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.stage_delete(1)
        self.assertEqual(self.store.gallery_path.read_bytes(), before)
        self.assertFalse(self.store.pending())

    def test_offline_retry_survives_restart_and_does_not_publish(self):
        self.store.stage(1, 'Test', samples())
        path, _ = self.store.pending()[0]
        before = path.read_bytes()
        with patch('src.desktop_enrollment.replace_samples', side_effect=OSError('offline')):
            result = self.store.retry()
        self.assertEqual(result['pending'], 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.store.gallery_path.exists())
        restarted = DesktopEnrollment(self.store.directory, self.store.gallery_path)
        def refresh(path):
            save_gallery(path, {'SV001': {'name': 'Confirmed'}})
        with patch('src.desktop_enrollment.replace_samples') as save, patch('src.desktop_enrollment.refresh_gallery', side_effect=refresh):
            result = restarted.retry()
        self.assertEqual((result['completed'], result['pending']), (1,0))
        for source, actual in zip(samples(), save.call_args.args[2]):
            self.assertEqual(source['image'], actual['image'])
        receipt = json.loads(next((self.store.directory/'receipts').glob('*.json')).read_text())
        self.assertNotIn('samples', receipt)

    def test_db_commit_refresh_failure_retry_does_not_repeat_write(self):
        self.store.stage(1, 'Test', samples())
        with patch('src.desktop_enrollment.replace_samples') as save, patch('src.desktop_enrollment.refresh_gallery', side_effect=OSError):
            self.assertEqual(self.store.retry()['pending'], 1)
            save.assert_called_once()
        self.assertTrue(self.store.pending()[0][1]['db_saved'])
        with patch('src.desktop_enrollment.replace_samples', side_effect=AssertionError('must not write again')) as save, patch('src.desktop_enrollment.refresh_gallery'):
            self.assertEqual(self.store.retry()['pending'], 0)
            save.assert_not_called()

    def test_targeted_registration_only_submits_selected_job(self):
        other_id = self.store.stage(1, 'Previously waiting', samples())
        selected_id = self.store.stage(2, 'Selected employee', samples(10))
        other_path = self.store.directory/'pending'/(other_id+'.json')
        original = other_path.read_bytes()
        with patch('src.desktop_enrollment.replace_samples') as save, patch('src.desktop_enrollment.refresh_gallery') as refresh:
            result = self.store.retry(selected_id)
        save.assert_called_once()
        self.assertEqual(save.call_args.args[0],2)
        refresh.assert_called_once_with(self.store.gallery_path)
        self.assertEqual(result['jobs'],{selected_id:'completed'})
        self.assertEqual((result['completed'],result['pending']),(1,1))
        self.assertEqual(other_path.read_bytes(),original)
        self.assertFalse((self.store.directory/'pending'/(selected_id+'.json')).exists())
        self.assertTrue((self.store.directory/'receipts'/(selected_id+'.json')).exists())

    def test_targeted_registration_reports_saved_until_gallery_refresh_succeeds(self):
        selected_id = self.store.stage(1, 'Selected employee', samples())
        other_id = self.store.stage(2, 'Unrelated waiting employee', samples(10))
        other_path = self.store.directory/'pending'/(other_id+'.json')
        other_before = other_path.read_bytes()
        with patch('src.desktop_enrollment.replace_samples') as save, patch('src.desktop_enrollment.refresh_gallery',side_effect=OSError('offline')):
            result = self.store.retry(selected_id)
        save.assert_called_once()
        self.assertEqual(result['jobs'],{selected_id:'saved'})
        self.assertEqual((result['completed'],result['pending']),(0,2))
        self.assertTrue(dict((job['id'],job) for _,job in self.store.pending())[selected_id]['db_saved'])
        self.assertFalse((self.store.directory/'receipts'/(selected_id+'.json')).exists())
        self.assertEqual(other_path.read_bytes(),other_before)
        with patch('src.desktop_enrollment.replace_samples',side_effect=AssertionError('must not resubmit committed data')) as save, patch('src.desktop_enrollment.refresh_gallery'):
            result = self.store.retry(selected_id)
        save.assert_not_called()
        self.assertEqual(result['jobs'],{selected_id:'completed'})
        self.assertEqual((result['completed'],result['pending']),(1,1))
        self.assertEqual(other_path.read_bytes(),other_before)

    def test_targeted_conflict_preserves_selected_and_unrelated_batches(self):
        other_id = self.store.stage(1, 'Do not submit', samples())
        selected_id = self.store.stage(2, 'Conflicted employee', samples(10))
        before = {path:path.read_bytes() for path,_ in self.store.pending()}
        with patch('src.desktop_enrollment.replace_samples',side_effect=face_sync.SyncConflict('Web changed')) as save, patch('src.desktop_enrollment.refresh_gallery') as refresh:
            result = self.store.retry(selected_id)
        save.assert_called_once()
        self.assertEqual(save.call_args.args[0],2)
        refresh.assert_not_called()
        self.assertEqual(result['jobs'],{selected_id:'conflict'})
        self.assertEqual((result['completed'],result['pending']),(0,2))
        self.assertTrue(result['errors'])
        self.assertEqual({path:path.read_bytes() for path,_ in self.store.pending()},before)

    def test_targeted_db_failure_remains_pending_without_publishing(self):
        selected_id = self.store.stage(1, 'Selected employee', samples())
        path,_ = self.store.pending()[0]
        before = path.read_bytes()
        with patch('src.desktop_enrollment.replace_samples',side_effect=OSError('DB unavailable')), patch('src.desktop_enrollment.refresh_gallery') as refresh:
            result = self.store.retry(selected_id)
        refresh.assert_not_called()
        self.assertEqual(result['jobs'],{selected_id:'pending'})
        self.assertEqual((result['completed'],result['pending']),(0,1))
        self.assertEqual(path.read_bytes(),before)
        self.assertFalse(self.store.gallery_path.exists())

    def test_conflict_and_corrupt_pending_are_preserved(self):
        self.store.stage(1, 'Test', samples())
        path, _ = self.store.pending()[0]
        before = path.read_bytes()
        with patch('src.desktop_enrollment.replace_samples', side_effect=face_sync.SyncConflict):
            result = self.store.retry()
        self.assertIn('không ghi đè', result['errors'][0])
        self.assertEqual(path.read_bytes(), before)
        path.write_text('{', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store.retry()
        self.assertEqual(path.read_text(), '{')

    def test_capture_uses_same_detection_for_pose_and_embedding(self):
        frame = np.zeros((8,8,3), dtype=np.uint8)
        with patch.dict(sys.modules, cv2=CV):
            actual = sample_from_frame(frame, [face()], 'frontal')
            self.assertEqual(len(actual['vector']), 512)
            for faces, pose, reference in (([], 'frontal', None), ([face(),face()], 'frontal', None),
                    ([face()], 'left', None), ([face(axis=2)], 'frontal', face().embedding)):
                with self.assertRaises(ValueError):
                    sample_from_frame(frame, faces, pose, reference)

    def test_explicit_archive_preserves_batch_and_allows_new_registration(self):
        self.store.stage(1, 'Old', samples())
        path, job = self.store.pending()[0]
        before = path.read_bytes()
        result = self.store.archive(1)
        self.assertEqual(result['pending'], 0)
        archived = self.store.directory/'archived'/path.name
        self.assertEqual(archived.read_bytes(), before)
        self.assertFalse(self.store.gallery_path.exists())
        self.store.stage(1, 'New', samples(20))
        self.assertNotEqual(self.store.pending()[0][1]['id'], job['id'])
        path, job = self.store.pending()[0]
        job['db_saved'] = True
        path.write_text(json.dumps(job), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store.archive(1)
        self.assertTrue(path.exists())

    def test_folder_rejects_partial_mixed_duplicate_pose_and_accepts_five(self):
        from src.register import collect_folder_samples
        folder = self.root/'images'
        folder.mkdir()
        for i in range(5):
            (folder/f'{i}.png').write_bytes(image_bytes(i, 'PNG'))
        adapter = types.SimpleNamespace(**vars(CV))
        adapter.imread = lambda path: decode(np.frombuffer(Path(path).read_bytes(), np.uint8), 1)
        engine = types.SimpleNamespace(detect=lambda image: [face(int(image[0,0,0]))])
        with patch.dict(sys.modules, cv2=adapter):
            self.assertEqual([s['pose'] for s in collect_folder_samples(engine, folder)], list(POSES))
            engine.detect = lambda image: [face()]
            with self.assertRaises(ValueError):
                collect_folder_samples(engine, folder)
            engine.detect = lambda image: [face(int(image[0,0,0]), axis=2 if int(image[0,0,0])==1 else 0)]
            with self.assertRaises(ValueError):
                collect_folder_samples(engine, folder)
            (folder/'4.png').unlink()
            with self.assertRaises(ValueError):
                collect_folder_samples(engine, folder)

    def test_cli_cancel_never_submits_partial_and_always_releases(self):
        import src.register as register
        class Camera:
            released = False
            def read(self):
                return True, np.zeros((8,8,3), np.uint8)
            def release(self):
                self.released = True
        camera = Camera()
        adapter = types.SimpleNamespace(**vars(CV), putText=lambda *a: None, imshow=lambda *a: None,
            waitKey=lambda delay: ord('q'), destroyAllWindows=lambda: None, FONT_HERSHEY_SIMPLEX=1)
        engine = types.SimpleNamespace(detect=lambda image: [face()])
        with patch.dict(sys.modules, cv2=adapter), patch('src.camera_source.open_camera', return_value=camera), patch.object(register, 'EMBEDDINGS_PATH', self.store.gallery_path), patch.object(register, '_submit') as submit:
            self.assertFalse(register.register_from_webcam(engine, 1, 'Test'))
            submit.assert_not_called()
        self.assertTrue(camera.released)

    def test_gui_capture_keeps_pairs_and_rejects_identity_change(self):
        with patch.dict(sys.modules, {'cv2': CV, 'src.face_engine': types.SimpleNamespace(FaceEngine=object)}):
            import gui_register
        class Variable:
            def set(self, value):
                self.value = value
        class DeferredWorker:
            def __init__(self):
                self.tasks = []
                self.errors = []
            def submit(self, work, success, failure):
                self.tasks.append((work, success, failure))
            def complete(self):
                work, success, failure = self.tasks.pop(0)
                try:
                    result = work()
                except Exception as error:
                    self.errors.append(error)
                    failure(error)
                else:
                    success(result)
        finished = []
        worker = DeferredWorker()
        owner = types.SimpleNamespace(current_step=0, capture_done=False, samples_collected=[],
            embeddings_collected=[], ready_timer=0, flash_timer=0, progress_var=Variable(),
            conf_var=Variable(), hint_var=Variable(), _build_step_indicators=lambda: None,
            _finalize_registration=lambda: finished.append(True), is_capturing=True,
            sample_busy=False, session_token=1, _sample_crops=[], io=worker,
            _update_controls=lambda: None, _refresh_thumbnails=lambda: None)
        ready = types.SimpleNamespace(ready=True, bbox=(0, 0, 8, 8))
        with patch.dict(sys.modules, cv2=CV), patch.object(gui_register, 'assess_frame', return_value=ready), \
                patch.dict(gui_register.capture_sample.__globals__, assess_frame=lambda *unused: ready):
            for index in range(5):
                frame = np.full((8,8,3), index, dtype=np.uint8)
                if index == 1:
                    gui_register.RegisterApp._do_capture(owner, frame, [face(index,axis=2)])
                    self.assertTrue(owner.sample_busy)
                    worker.complete()
                    self.assertEqual(owner.current_step,1)
                gui_register.RegisterApp._do_capture(owner, frame, [face(index)])
                self.assertEqual(owner.current_step,index, 'Pending work must not advance the UI')
                self.assertTrue(owner.sample_busy)
                worker.complete()
                if index == 0:
                    self.assertFalse(worker.errors)
                self.assertEqual(owner.current_step,index+1)
                self.assertFalse(owner.sample_busy)
        self.assertEqual(len(finished),1)
        self.assertEqual(len(worker.errors),1)
        self.assertIn('khớp', str(worker.errors[0]))
        self.assertEqual([sample['pose'] for sample in owner.samples_collected],list(POSES))
        for index,sample in enumerate(owner.samples_collected):
            self.assertEqual(sample['image'],image_bytes(index))


class EmployeeRosterTests(unittest.TestCase):
    def test_roster_uses_official_names_and_includes_employee_without_face_samples(self):
        database = sqlite3.connect(':memory:')
        self.addCleanup(database.close)
        database.executescript('''
            CREATE TABLE NhanVien (MaNV INTEGER PRIMARY KEY, HoTen TEXT);
            CREATE TABLE FaceEmbedding (MaEmbedding INTEGER PRIMARY KEY, MaNV INTEGER);
            INSERT INTO NhanVien VALUES (2,'Employee with no face samples'),(1,'Official employee name');
            INSERT INTO FaceEmbedding VALUES (1,1),(2,1),(3,1),(4,1),(5,1);
        ''')
        queries = []
        class Cursor:
            def __enter__(self):
                self.cursor = database.cursor()
                return self
            def __exit__(self,*unused):
                self.cursor.close()
            def execute(self,query,params=None):
                queries.append(query)
                self.cursor.execute(query,params or ())
            def fetchall(self):
                return self.cursor.fetchall()
        class Connection:
            closed = False
            def cursor(self):
                return Cursor()
            def close(self):
                self.closed = True
        connection = Connection()
        with patch('src.face_sync.connect',return_value=connection):
            result = DesktopEnrollment().employees()
        self.assertEqual(result,[
            {'id':1,'name':'Official employee name','n_images':5},
            {'id':2,'name':'Employee with no face samples','n_images':0},
        ])
        self.assertTrue(connection.closed)
        self.assertTrue(queries)
        self.assertTrue(all(query.lstrip().upper().startswith('SELECT') for query in queries))
        self.assertEqual(database.execute('SELECT COUNT(*) FROM FaceEmbedding').fetchone()[0],5)


class RelayTests(unittest.TestCase):
    def test_default_and_auto_never_fall_back_to_local_camera(self):
        adapter = types.SimpleNamespace(VideoCapture=lambda index: 'local')
        for mode in ('relay', 'auto'):
            with patch.dict(os.environ, PBL4_CAMERA_MODE=mode, PBL4_AI_URL='http://127.0.0.1:1'), patch.dict(sys.modules, cv2=adapter):
                camera = open_camera()
                self.assertIsInstance(camera, RelayCamera)
                self.assertEqual(camera.read(), (False,None))
                camera.release()
                with self.assertRaises(ValueError):
                    open_camera(1)
        with patch.dict(os.environ, PBL4_CAMERA_MODE='local'), patch.dict(sys.modules, cv2=adapter):
            self.assertEqual(open_camera(2), 'local')

    def test_http_status_redirect_invalid_and_oversize_rejected(self):
        state = dict(mode='normal', target_calls=0, authorized=True)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.path == '/target':
                    state['target_calls'] += 1
                state['authorized'] = state['authorized'] and self.headers.get('Authorization') == 'Bearer test-token'
                mode = state['mode']
                raw = b'fake' if mode == 'invalid' else image_bytes()
                self.send_response(302 if mode == 'redirect' else (500 if mode == 'error' else 200))
                self.send_header('Location', '/target')
                self.send_header('Content-Type', 'text/plain' if mode == 'media' else 'image/jpeg')
                self.send_header('Content-Length', str(6*1024*1024 if mode == 'large' else len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        camera = RelayCamera(f'http://127.0.0.1:{server.server_port}/frame','test-token')
        try:
            with patch.dict(sys.modules, cv2=CV):
                self.assertTrue(camera.read()[0])
                for mode in ('redirect','error','invalid','media','large'):
                    state['mode'] = mode
                    self.assertEqual(camera.read(),(False,None),mode)
            self.assertTrue(state['authorized'])
            self.assertEqual(state['target_calls'],0)
        finally:
            camera.release()
            server.shutdown()
            server.server_close()
            thread.join(2)


@unittest.skipUnless(args.database, 'Disposable database runner only')
class DatabaseTests(unittest.TestCase):
    def test_real_transactions_replay_conflict_rollback_and_reconciliation(self):
        if os.environ.get('PBL4_TEST_DATABASE') != 'isolated' or os.environ.get('MARIADB_HOST') != '127.0.0.1' or int(os.environ.get('MARIADB_PORT','3306')) == 3306:
            raise RuntimeError('Refusing non-disposable database')
        connection = face_sync.connect()
        def query(sql, params=None):
            with connection.cursor() as cursor:
                cursor.execute(sql,params)
                return cursor.fetchall()
        query("INSERT INTO NhanVien (MaNV,HoTen,MaVaiTro) VALUES (30,'Original Name',1),(31,'Desktop Two',2)")
        connection.commit()
        history = {table: query('SELECT COUNT(*) FROM '+table)[0][0] for table in ('ChamCong','AttendanceEvent','LichSuSucKhoe','LichSuTrangThai','CanhBao','TaiKhoan')}
        connection.commit()
        with tempfile.TemporaryDirectory(prefix='pbl4-desktop-db-') as directory:
            root = Path(directory)
            store = DesktopEnrollment(root/'jobs',root/'gallery.pkl')
            batch = samples()
            face_sync.replace_samples(30,'Must not rename',batch,gallery_revision([]))
            gallery = face_sync.refresh_gallery(store.gallery_path)
            revision = gallery['SV030']['revision']
            self.assertEqual(query('SELECT HoTen,MaVaiTro FROM NhanVien WHERE MaNV=30')[0],('Original Name',1))
            ids = query('SELECT MaEmbedding FROM FaceEmbedding WHERE MaNV=30 ORDER BY MaEmbedding')
            connection.commit()
            face_sync.replace_samples(30,'Ignored',batch,gallery_revision([]))
            self.assertEqual(query('SELECT MaEmbedding FROM FaceEmbedding WHERE MaNV=30 ORDER BY MaEmbedding'),ids)
            connection.commit()
            store.stage(30,'Old pending',samples(10))
            face_sync.replace_samples(30,'New Web',samples(20),revision)
            new_revision = face_sync.refresh_gallery(store.gallery_path)['SV030']['revision']
            result = store.retry()
            self.assertEqual(result['pending'],1)
            self.assertIn('không ghi đè',result['errors'][0])
            self.assertEqual(face_sync.refresh_gallery(store.gallery_path)['SV030']['revision'],new_revision)
            query("CREATE TRIGGER fail_desktop_avatar BEFORE UPDATE ON NhanVien FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Injected avatar failure'")
            connection.commit()
            for operation in (lambda: face_sync.replace_samples(31,'Ignored',batch,gallery_revision([])),
                              lambda: face_sync.delete_samples(30,new_revision)):
                with self.assertRaises(Exception):
                    operation()
            self.assertEqual(query('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV=31')[0][0],0)
            self.assertEqual(query('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV=30')[0][0],5)
            query('DROP TRIGGER fail_desktop_avatar')
            connection.commit()
            with self.assertRaises(ValueError):
                face_sync.replace_samples(999,'Unknown',batch,gallery_revision([]))
            self.assertEqual(query('SELECT COUNT(*) FROM NhanVien WHERE MaNV=999')[0][0],0)
            connection.commit()
            face_sync.delete_samples(30,new_revision)
            face_sync.delete_samples(30,new_revision)  # Lost delete ACK.
            gallery = face_sync.refresh_gallery(store.gallery_path)
            self.assertNotIn('SV030',gallery)
            self.assertIsNone(query('SELECT AnhKhuonMat FROM NhanVien WHERE MaNV=30')[0][0])
            connection.commit()
            # Other employee succeeds despite employee 30's pending conflict.
            store.stage(31,'Ignored',batch)
            result = store.retry()
            self.assertEqual((result['completed'], result['pending']),(1,1))
            self.assertIn('SV031',GalleryCache().load(store.gallery_path))
            for table,count in history.items():
                self.assertEqual(query('SELECT COUNT(*) FROM '+table)[0][0],count,table)
            connection.commit()
        connection.close()


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + remaining)
