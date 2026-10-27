"""No model, network, camera or project data is used by these regressions."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.atomic_storage import save_gallery, atomic_write
from src.enrollment_pose import estimate_pose, check_pose_match
from src.gallery_store import GalleryCache, replace_from_loader, update_gallery


class PoseTests(unittest.TestCase):
    def test_five_distinct_poses(self):
        for expected, nose in [('frontal', (5, 5)), ('left', (3, 5)),
                               ('right', (7, 5)), ('up', (5, 3)), ('down', (5, 8))]:
            actual, metrics = estimate_pose([(0, 0), (10, 0), nose, (3, 10), (7, 10)])
            self.assertEqual(actual, expected)
            for requested in ('frontal', 'left', 'right', 'up', 'down', 'invalid'):
                self.assertEqual(check_pose_match(requested, actual, metrics), requested == expected)

    def test_invalid_landmarks(self):
        for points in ([], [(0, 0)] * 5, [(0, 0, 1)] * 5,
                       [(0, 0), (10, 0), (float('nan'), 5), (3, 10), (7, 10)]):
            with self.assertRaises(ValueError):
                estimate_pose(points)


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pbl4-gallery-test-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'gallery.pkl'

    def test_independent_caches_observe_replace_and_delete(self):
        caches = [GalleryCache(), GalleryCache()]
        save_gallery(self.path, {'SV001': {'name': 'A'}})
        for cache in caches:
            self.assertIn('SV001', cache.load(self.path))
        save_gallery(self.path, {'SV002': {'name': 'B'}})
        for cache in caches:
            self.assertEqual(set(cache.load(self.path)), {'SV002'})
        save_gallery(self.path, {})
        for cache in caches:
            self.assertEqual(cache.load(self.path), {})
        self.path.unlink()
        self.assertEqual(caches[0].load(self.path), {})

    def test_failed_fetch_preserves_exact_file(self):
        save_gallery(self.path, {'old': 1})
        original = self.path.read_bytes()
        def fail():
            raise ValueError('bad server payload')
        with self.assertRaises(ValueError):
            replace_from_loader(self.path, fail)
        with self.assertRaises(ValueError):
            replace_from_loader(self.path, lambda: [])
        self.assertEqual(self.path.read_bytes(), original)

    def test_refresh_locks_before_fetch(self):
        first_fetching, release = threading.Event(), threading.Event()
        second_fetching = threading.Event()
        def old():
            first_fetching.set()
            if not release.wait(3):
                raise RuntimeError('test timeout')
            return {'old': 1}
        def new():
            second_fetching.set()
            return {'new': 2}
        with ThreadPoolExecutor(2) as workers:
            a = workers.submit(replace_from_loader, self.path, old)
            self.assertTrue(first_fetching.wait(3))
            b = workers.submit(replace_from_loader, self.path, new)
            try:
                self.assertFalse(second_fetching.wait(.1))
            finally:
                release.set()
            a.result(5)
            b.result(5)
        self.assertEqual(GalleryCache().load(self.path), {'new': 2})

    def test_process_updates_do_not_lose_employees(self):
        code = ('import sys; from src.gallery_store import update_gallery; '
                'update_gallery(sys.argv[1], lambda d: dict(d, **{sys.argv[2]: 1}))')
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        processes = [subprocess.Popen([sys.executable, '-B', '-c', code, str(self.path), str(i)],
                     env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
                     for i in range(8)]
        try:
            for process in processes:
                _, error = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, error.decode(errors='replace'))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()
        self.assertEqual(set(GalleryCache().load(self.path)), {str(i) for i in range(8)})

    def test_corrupt_file_never_returns_stale_cache(self):
        cache = GalleryCache()
        save_gallery(self.path, {'old': 1})
        cache.load(self.path)
        self.path.write_bytes(b'invalid')
        with self.assertRaises(Exception):
            cache.load(self.path)

    def test_running_reader_process_reloads_external_changes(self):
        import json
        code = ('import sys,json; from src.gallery_store import GalleryCache\n'
                'cache=GalleryCache()\n'
                'for line in sys.stdin:\n'
                ' print(json.dumps(sorted(cache.load(sys.argv[1]))),flush=True)\n')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        process = subprocess.Popen([sys.executable, '-B', '-u', '-c', code, str(self.path)],
            env=dict(os.environ, PYTHONPATH=str(ROOT)), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, creationflags=flags)
        try:
            with ThreadPoolExecutor(1) as reader:
                for gallery in ({'SV001': 1}, {'SV002': 2}, {}):
                    save_gallery(self.path, gallery)
                    process.stdin.write('load\n')
                    process.stdin.flush()
                    response = reader.submit(process.stdout.readline).result(timeout=5)
                    self.assertEqual(json.loads(response), sorted(gallery))
        finally:
            process.kill()
            process.communicate(timeout=5)

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing violation handling')
    def test_atomic_replace_retries_temporary_windows_sharing_violation(self):
        self.path.write_bytes(b'old')
        replace = os.replace
        attempts = []
        def sharing_violation(source, target):
            attempts.append(True)
            if len(attempts) < 3:
                self.assertEqual(self.path.read_bytes(), b'old')
                raise PermissionError('temporary sharing violation')
            return replace(source, target)
        with patch('src.atomic_storage.os.replace', side_effect=sharing_violation):
            atomic_write(self.path, b'new')
        self.assertEqual(len(attempts), 3)
        self.assertEqual(self.path.read_bytes(), b'new')

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing violation handling')
    def test_permanent_replace_failure_is_bounded_and_preserves_old_file(self):
        self.path.write_bytes(b'old')
        with patch('src.atomic_storage.os.replace', side_effect=PermissionError), patch('src.atomic_storage.time.monotonic', side_effect=[0, 3]):
            with self.assertRaises(PermissionError):
                atomic_write(self.path, b'new')
        self.assertEqual(self.path.read_bytes(), b'old')
        self.assertFalse(list(self.path.parent.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
