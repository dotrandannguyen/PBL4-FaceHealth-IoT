import threading
import time
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.ui_worker import UiWorker
from src.camera_source import FramePump


class Owner:
    def __init__(self):
        self.thread = threading.get_ident()
        self.calls = []
    def after(self, delay, callback):
        assert threading.get_ident() == self.thread
        self.calls.append(callback)
        return len(self.calls)
    def after_cancel(self, timer):
        assert threading.get_ident() == self.thread


class DesktopThreadTests(unittest.TestCase):
    def test_worker_never_calls_tk_and_delivers_success_and_error_on_poll(self):
        owner = Owner()
        worker = UiWorker(owner)
        output = []
        future_done = threading.Event()
        def work():
            self.assertNotEqual(threading.get_ident(), owner.thread)
            return 42
        worker.submit(work, lambda value: output.append((threading.get_ident(), value)), lambda error: None)
        def fail():
            raise ValueError('expected')
        worker.submit(fail, lambda value: None, lambda error: (output.append((threading.get_ident(), str(error))), future_done.set()))
        try:
            deadline = time.monotonic() + 3
            while len(output) < 2 and time.monotonic() < deadline:
                worker.poll()
                time.sleep(.01)
            self.assertEqual(output, [(owner.thread, 42), (owner.thread, 'expected')])
        finally:
            worker.close()

    def test_close_never_delivers_late_callback(self):
        owner, started, release, done = Owner(), threading.Event(), threading.Event(), threading.Event()
        worker = UiWorker(owner)
        def work():
            started.set()
            release.wait(3)
            done.set()
        delivered = []
        worker.submit(work, delivered.append, delivered.append)
        self.assertTrue(started.wait(2))
        worker.close()
        release.set()
        self.assertTrue(done.wait(2))
        worker.poll()
        self.assertFalse(delivered)

    def test_frame_pump_has_one_reader_and_releases_on_close(self):
        released, read = threading.Event(), threading.Event()
        threads = set()
        class Camera:
            def read(self):
                threads.add(threading.get_ident())
                read.set()
                return True, 'frame'
            def release(self):
                released.set()
        class Engine:
            def detect(self, frame):
                threads.add(threading.get_ident())
                return ['face']
        pump = FramePump(Camera, Engine)
        try:
            self.assertTrue(read.wait(2))
            deadline = time.monotonic()+2
            while pump.snapshot()[0] is None and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertEqual(pump.snapshot(), ('frame', ['face']))
            self.assertEqual(len(threads), 1)
            self.assertNotIn(threading.get_ident(), threads)
        finally:
            pump.close()
            pump.thread.join(2)
        self.assertTrue(released.is_set())
        self.assertEqual(pump.snapshot(), (None, []))

    def test_stalled_camera_does_not_block_snapshot_or_tk_close(self):
        started, release = threading.Event(), threading.Event()
        class Camera:
            def read(self):
                started.set()
                release.wait(3)
                return False, None
            def release(self):
                pass
        pump = FramePump(Camera, lambda: None)
        try:
            self.assertTrue(started.wait(2))
            start = time.monotonic()
            self.assertEqual(pump.snapshot(), (None, []))
            pump.close()
            self.assertLess(time.monotonic()-start, .1)
        finally:
            release.set()
            pump.thread.join(2)


if __name__ == '__main__':
    unittest.main()
