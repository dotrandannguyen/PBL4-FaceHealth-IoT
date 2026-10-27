"""Exercise tracking, camera/inference isolation and graceful module switching."""
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.live_attendance import AttendanceWorker, LiveFaceAnalyzer, read_history
from src.desktop_lifecycle import CameraModuleLauncher
from unified_engine import UnifiedAttendanceEngine


def face(axis, x):
    vector = np.zeros(512)
    vector[axis] = 1
    return SimpleNamespace(embedding=vector, bbox=np.array([x, 20, x + 80, 110]))


class Extractor:
    def extract_features(self, frame):
        return dict(ear=.3, mar=.1, pitch=180., yaw=0., roll=0., pts=np.tile([50., 50.], (468, 1)))

    def _calculate_head_pose(self, pts, width, height):
        self.geometry = width, height
        return 180., 0., 0.


class Predictor:
    def __init__(self):
        self.extractor = Extractor()
        self.count, self.closed = 0, False

    def predict_features(self, features, captured_at):
        self.count += 1
        return dict(status='Normal', confidence=.9, is_valid=True, count=self.count, metrics=features)

    def reset(self):
        self.count = 0

    def close(self):
        self.closed = True


class LiveTrackingTests(unittest.TestCase):
    def setUp(self):
        self.engine = SimpleNamespace(detect=Mock())
        self.predictors = []
        def factory():
            predictor = Predictor()
            self.predictors.append(predictor)
            return predictor
        def identify(engine, frame, probe_embedding):
            identity = str(int(np.argmax(probe_embedding)))
            return dict(match=True, student_id=identity, name='Person ' + identity, similarity=.9)
        self.analyzer = LiveFaceAnalyzer(self.engine, factory, identify)
        self.addCleanup(self.analyzer.close)
        self.frame = np.zeros((240, 320, 3), np.uint8)

    def test_face_order_swap_keeps_each_person_buffer_and_identity(self):
        self.engine.detect.return_value = [face(0, 20), face(1, 170)]
        first = self.analyzer.analyze(self.frame, 1.)
        self.engine.detect.return_value = [face(1, 170), face(0, 20)]
        second = self.analyzer.analyze(self.frame, 1.3)
        self.assertEqual([f['student_id'] for f in second], ['1', '0'])
        self.assertEqual([f['track_id'] for f in second], [first[1]['track_id'], first[0]['track_id']])
        self.assertEqual([f['state']['count'] for f in second], [2, 2])
        self.assertEqual(len(self.predictors), 2)
        self.assertEqual(self.predictors[0].extractor.geometry, (320, 240))

    def test_replacement_at_same_position_does_not_inherit_state(self):
        self.engine.detect.return_value = [face(0, 20)]
        first = self.analyzer.analyze(self.frame, 1.)
        self.engine.detect.return_value = [face(1, 20)]
        replacement = self.analyzer.analyze(self.frame, 1.3)
        self.assertNotEqual(first[0]['track_id'], replacement[0]['track_id'])
        self.assertEqual(replacement[0]['state']['count'], 1)
        self.assertTrue(self.predictors[0].closed)

    def test_absent_or_stale_face_releases_mesh_and_clears_sequence(self):
        self.engine.detect.return_value = [face(0, 20)]
        self.analyzer.analyze(self.frame, 1.)
        self.engine.detect.return_value = []
        self.assertEqual(self.analyzer.analyze(self.frame, 1.3), [])
        self.assertTrue(self.predictors[0].closed)
        self.engine.detect.return_value = [face(0, 20)]
        self.analyzer.analyze(self.frame, 2.)
        self.analyzer.analyze(self.frame, 3.)
        self.assertEqual(len(self.predictors), 3)


class WorkerTests(unittest.TestCase):
    def wait_for(self, predicate, message='Worker did not reach the expected state', timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertTrue(predicate(), message)

    @staticmethod
    def state(worker):
        value = worker.snapshot()['info'].get('state')
        return getattr(value, 'value', value)

    def stop_worker(self, worker):
        worker.close()
        worker.thread.join(3)
        self.assertFalse(worker.thread.is_alive())

    @staticmethod
    def analysis():
        return dict(best=0, scores=[1., 1., 1.],
            identity=dict(match=True, student_id='SV001', name='Test', similarity=.92),
            status=dict(status='Normal', confidence=.9, is_valid=True))

    def capture_three(self, worker, clock):
        self.assertTrue(worker.start_session())
        self.wait_for(lambda: worker.snapshot()['info'].get('captured_count') == 1)
        clock.now = 100.31
        self.wait_for(lambda: worker.snapshot()['info'].get('captured_count') == 2)
        clock.now = 100.62

    def test_idle_camera_never_runs_preview_models_or_auto_starts_a_scan(self):
        reads, released, available = [], threading.Event(), threading.Event()
        frame = np.zeros((40, 40, 3), np.uint8)
        def read():
            reads.append(len(reads))
            return available.is_set(), frame if available.is_set() else None
        engine = SimpleNamespace(face_engine=Mock(), best_frame_bgr=None,
            start_session=Mock(), update=Mock(return_value={'state': 'IDLE'}), close=Mock())
        analyzer_factory = Mock(side_effect=AssertionError('Idle camera must not load a preview model'))
        with tempfile.TemporaryDirectory() as directory:
            worker = AttendanceWorker(engine_factory=lambda: engine,
                camera_factory=lambda: SimpleNamespace(read=read, release=released.set),
                analyzer_factory=analyzer_factory, logs_dir=directory)
            try:
                self.wait_for(lambda: not worker.loading and len(reads) >= 2)
                self.assertFalse(worker.start_session(), 'A press without a camera frame must be rejected')
                available.set()
                self.wait_for(lambda: len(reads) >= 5 and worker.snapshot()['frame'] is not None)
                first = worker.snapshot()
                self.wait_for(lambda: worker.snapshot()['seq'] > first['seq'])
                latest = worker.snapshot()
                self.assertIs(latest['frame'], frame)
                self.assertEqual(latest['faces'], [])
                self.assertIsNone(latest['result_frame'])
                self.assertEqual(self.state(worker), 'IDLE')
                self.assertFalse(worker.error)
                engine.start_session.assert_not_called()
                engine.face_engine.detect.assert_not_called()
                engine.face_engine.embed.assert_not_called()
                analyzer_factory.assert_not_called()
            finally:
                self.stop_worker(worker)
            self.assertTrue(released.is_set())
            self.assertIsNone(worker.snapshot()['frame'])
            self.assertEqual(worker.snapshot()['faces'], [])
            engine.close.assert_called_once()

    def test_camera_worker_records_identity_and_state_through_existing_engine(self):
        vector = np.zeros(512)
        vector[0] = 1.
        frame = np.zeros((80, 80, 3), np.uint8)
        released = threading.Event()
        predictor = SimpleNamespace(reset=Mock(), close=Mock(),
            predict_status_detailed=Mock(return_value=dict(status='Fatigue', is_valid=True,
                confidence=.86, metrics=dict(ear=.19, mar=.4, pitch=179., yaw=1., roll=2.))))
        transport = SimpleNamespace(send=Mock(return_value={'status': 'success', 'action': 'checkin'}),
                                    retry_pending=lambda: [])
        camera = SimpleNamespace(read=lambda: (True, frame), release=released.set)
        analyzer = SimpleNamespace(analyze=lambda image, stamp: [], close=lambda: None)
        identity = dict(match=True, student_id='SV001', name='Test', similarity=.92)
        with tempfile.TemporaryDirectory() as directory, patch('src.verify.identify', return_value=identity):
            def factory():
                return UnifiedAttendanceEngine(logs_dir=directory,
                    face_engine=SimpleNamespace(embed=lambda image: vector),
                    status_predictor=predictor, transport=transport, camera_only=True)
            worker = AttendanceWorker(engine_factory=factory, camera_factory=lambda: camera,
                                      analyzer_factory=lambda engine: analyzer, logs_dir=directory)
            try:
                deadline = time.monotonic() + 4
                while worker.snapshot()['frame'] is None and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(worker.start_session())
                while not worker.history() and time.monotonic() < deadline:
                    time.sleep(.01)
                record = worker.history()[-1]
                self.assertEqual(record['student_id'], 'SV001')
                self.assertEqual(record['ai2_face_status'], 'Fatigue')
                self.assertEqual(record['ai2_confidence'], .86)
                self.assertEqual(record['attendance_action'], 'CHECK-IN')
                self.assertEqual(transport.send.call_args.args[0]['TrangThai'], 'Fatigue')
                self.assertEqual(len(predictor.predict_status_detailed.call_args.args[0]), 3)
                self.assertEqual(read_history(Path(directory) / 'attendance_logs.jsonl')[-1]['ai2_face_status'], 'Fatigue')
            finally:
                worker.close()
                worker.thread.join(3)
            self.assertTrue(released.is_set())
            predictor.close.assert_called_once()

    def test_unavailable_state_metrics_do_not_abort_recognized_attendance(self):
        from src.predict_status import StatusPredictor
        with tempfile.TemporaryDirectory() as directory:
            engine = UnifiedAttendanceEngine(logs_dir=directory, face_engine=object(),
                status_predictor=SimpleNamespace(close=lambda: None), camera_only=True)
            try:
                engine.captured_frames = ['one', 'two', 'three']
                engine._accept_analysis(dict(best=0, scores=[1., 1., 1.],
                    identity=dict(match=True, similarity=.9, student_id='SV001', name='Test'),
                    status=StatusPredictor._invalid('No usable face')))
                self.assertTrue(engine.ai_processed)
                self.assertTrue(engine.identity_matched)
                self.assertFalse(engine.ai2_valid)
                self.assertEqual(engine.session_status_history, ['Unknown'])
            finally:
                engine.close()

    def test_one_physical_request_is_accepted_despite_keyspam_and_busy_presses_are_not_queued(self):
        released = threading.Event()
        frame = np.zeros((40, 40, 3), np.uint8)
        class Engine:
            face_engine = object()
            best_frame_bgr = None
            starts, closed, state = 0, False, 'IDLE'
            def update(self, image):
                return dict(state=self.state)
            def start_session(self):
                if self.state != 'IDLE':
                    return None
                self.starts += 1
                self.state = 'CAPTURING'
                return 'scan-' + str(self.starts)
            def close(self):
                self.closed = True
        engine = Engine()
        with tempfile.TemporaryDirectory() as directory:
            worker = AttendanceWorker(engine_factory=lambda: engine,
                camera_factory=lambda: SimpleNamespace(read=lambda: (True, frame), release=released.set),
                analyzer_factory=Mock(side_effect=AssertionError('No preview models')), logs_dir=directory)
            try:
                self.wait_for(lambda: worker.snapshot()['frame'] is not None and self.state(worker) == 'IDLE')
                barrier, answers = threading.Barrier(9), []
                def press():
                    barrier.wait(2)
                    answers.append(worker.start_session())
                keys = [threading.Thread(target=press) for _ in range(8)]
                for key in keys:
                    key.start()
                barrier.wait(2)
                for key in keys:
                    key.join(2)
                    self.assertFalse(key.is_alive())
                self.assertEqual(sum(answers), 1)
                self.wait_for(lambda: self.state(worker) == 'CAPTURING')
                self.assertEqual(engine.starts, 1)
                for _ in range(10):
                    self.assertFalse(worker.start_session())
                engine.state = 'COMPLETED'
                self.wait_for(lambda: self.state(worker) == 'COMPLETED')
                for _ in range(10):
                    self.assertFalse(worker.start_session())
                engine.state = 'IDLE'
                self.wait_for(lambda: self.state(worker) == 'IDLE')
                previous = worker.snapshot()['seq']
                self.wait_for(lambda: worker.snapshot()['seq'] >= previous + 3)
                self.assertEqual(engine.starts, 1, 'Busy key presses were replayed into a later idle period')
                self.assertTrue(worker.start_session())
                self.wait_for(lambda: engine.starts == 2)
            finally:
                self.stop_worker(worker)
            self.assertTrue(released.is_set())
            self.assertTrue(engine.closed)

    def test_raw_camera_continues_during_slow_session_inference_and_finalization(self):
        inference_entered, inference_release = threading.Event(), threading.Event()
        persistence_entered, persistence_release = threading.Event(), threading.Event()
        camera_released, reads = threading.Event(), []
        clock = SimpleNamespace(now=100.)
        frame = np.zeros((40, 40, 3), np.uint8)
        def read():
            reads.append(len(reads))
            return True, frame
        def analyze(frames):
            inference_entered.set()
            inference_release.wait(5)
            return self.analysis()
        def send(payload):
            persistence_entered.set()
            persistence_release.wait(5)
            return {'status': 'success', 'action': 'checkin'}
        transport = SimpleNamespace(send=Mock(side_effect=send), retry_pending=lambda: [])
        with tempfile.TemporaryDirectory() as directory:
            engine = UnifiedAttendanceEngine(logs_dir=directory, face_engine=object(),
                status_predictor=SimpleNamespace(reset=lambda: None, close=lambda: None),
                analyzer=analyze, transport=transport, camera_only=True, clock=lambda: clock.now)
            worker = AttendanceWorker(engine_factory=lambda: engine,
                camera_factory=lambda: SimpleNamespace(read=read, release=camera_released.set),
                logs_dir=directory, clock=lambda: clock.now)
            try:
                self.wait_for(lambda: worker.snapshot()['frame'] is not None)
                self.capture_three(worker, clock)
                self.assertTrue(inference_entered.wait(2))
                self.wait_for(lambda: self.state(worker) == 'PROCESSING')
                count, sequence = len(reads), worker.snapshot()['seq']
                self.wait_for(lambda: len(reads) >= count + 3 and worker.snapshot()['seq'] > sequence,
                              'A slow model stopped the raw camera preview')
                self.assertFalse(worker.start_session())
                inference_release.set()
                self.assertTrue(persistence_entered.wait(2))
                self.wait_for(lambda: self.state(worker) == 'FINALIZING')
                count, sequence = len(reads), worker.snapshot()['seq']
                self.wait_for(lambda: len(reads) >= count + 3 and worker.snapshot()['seq'] > sequence,
                              'A slow attendance write stopped the raw camera preview')
                self.assertFalse(worker.start_session())
                persistence_release.set()
                self.wait_for(lambda: self.state(worker) == 'COMPLETED')
                transport.send.assert_called_once()
            finally:
                inference_release.set()
                persistence_release.set()
                self.stop_worker(worker)
            self.assertTrue(camera_released.is_set())

    def test_result_is_shown_for_five_seconds_then_cleared_until_another_physical_request(self):
        clock = SimpleNamespace(now=100.)
        reads = []
        def read():
            reads.append(len(reads))
            return True, np.full((40, 40, 3), len(reads) % 255, dtype=np.uint8)
        analyze = Mock(side_effect=lambda frames: self.analysis())
        transport = SimpleNamespace(send=Mock(return_value={'status': 'success', 'action': 'checkout'}),
                                    retry_pending=lambda: [])
        with tempfile.TemporaryDirectory() as directory:
            engine = UnifiedAttendanceEngine(logs_dir=directory, face_engine=object(),
                status_predictor=SimpleNamespace(reset=lambda: None, close=lambda: None),
                analyzer=analyze, transport=transport, camera_only=True, clock=lambda: clock.now)
            worker = AttendanceWorker(engine_factory=lambda: engine,
                camera_factory=lambda: SimpleNamespace(read=read, release=lambda: None),
                logs_dir=directory, clock=lambda: clock.now)
            try:
                self.wait_for(lambda: worker.snapshot()['frame'] is not None)
                self.capture_three(worker, clock)
                self.wait_for(lambda: self.state(worker) == 'COMPLETED')
                completed = worker.snapshot()
                self.assertEqual(completed['info']['completed_record']['attendance_action'], 'CHECK-OUT')
                self.assertIsNotNone(completed['result_frame'])
                result = completed['result_frame'].copy()
                completed_at = engine.state_enter_time
                self.assertFalse(worker.start_session())
                clock.now = completed_at + 4.999
                previous = worker.snapshot()['seq']
                self.wait_for(lambda: worker.snapshot()['seq'] > previous)
                self.assertEqual(self.state(worker), 'COMPLETED')
                np.testing.assert_array_equal(worker.snapshot()['result_frame'], result)
                self.assertFalse(worker.start_session())
                clock.now = completed_at + 5.
                self.wait_for(lambda: self.state(worker) == 'IDLE')
                idle = worker.snapshot()
                self.assertIsNone(idle['result_frame'])
                self.assertIsNone(idle['info']['completed_record'])
                self.assertEqual(idle['info']['captured_count'], 0)
                self.assertIsNone(idle['info']['identified_id'])
                self.assertIsNone(engine.best_frame_bgr)
                previous = idle['seq']
                self.wait_for(lambda: worker.snapshot()['seq'] >= previous + 3)
                self.assertEqual(self.state(worker), 'IDLE')
                analyze.assert_called_once()
                transport.send.assert_called_once()
                self.assertTrue(worker.start_session())
                self.wait_for(lambda: self.state(worker) == 'CAPTURING')
                self.assertIsNone(worker.snapshot()['result_frame'])
            finally:
                self.stop_worker(worker)

    def test_history_accepts_legacy_and_status_records_skips_partial_and_sync_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'attendance_logs.jsonl'
            path.write_text('{"timestamp":"old","student_id":"SV001"}\n'
                            '{"type":"sync_result","event_id":"1"}\n'
                            '{"timestamp":"new","student_id":"SV002","ai2_face_status":"Fatigue"}\n'
                            '{"incomplete":', encoding='utf-8')
            records = read_history(path)
            self.assertEqual([r['student_id'] for r in records], ['SV001', 'SV002'])
            self.assertEqual(records[-1]['ai2_face_status'], 'Fatigue')


class LauncherTests(unittest.TestCase):
    def test_switch_waits_for_exit_and_duplicate_click_does_not_open_camera_twice(self):
        owner = SimpleNamespace(after=Mock(return_value='timer'), after_cancel=Mock())
        first, second = Mock(), Mock()
        first.poll.return_value = None
        second.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = CameraModuleLauncher(owner, 'python', root / 'ai', {}, Mock())
            launcher.run_dir = root / 'desktop'
            with patch('src.desktop_lifecycle.subprocess.Popen', side_effect=[first, second]) as spawn:
                launcher.launch('gui_register.py', 'Register')
                launcher.launch('gui_register.py', 'Register')
                self.assertEqual(spawn.call_count, 1)
                launcher.launch('gui_status.py', 'Status')
                self.assertTrue(launcher.active['stop'].exists())
                self.assertEqual(spawn.call_count, 1)
                first.poll.return_value, first.returncode = 0, 0
                launcher._poll()
                self.assertEqual(spawn.call_count, 2)
                self.assertIn('gui_status.py', spawn.call_args.args[0])
                closed = Mock()
                launcher.close(closed)
                closed.assert_not_called()
                second.poll.return_value, second.returncode = 0, 0
                launcher._poll()
                closed.assert_called_once()


if __name__ == '__main__':
    unittest.main()
