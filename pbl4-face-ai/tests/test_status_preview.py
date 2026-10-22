"""State prediction timing and thread cleanup without a model or webcam."""
from pathlib import Path
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.predict_status import StatusPredictor, to_serializable
from src.status_preview import StatusPreviewWorker, confidence_text, draw_status_frame


def observation(**overrides):
    return dict(dict(ear=.3, mar=.1, pitch=180., yaw=0., roll=2.,
                     pts=[(10., 15.), (50., 60.)]), **overrides)


class PredictorPreviewTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.
        self.model_calls = []
        def predict(rows):
            self.model_calls.append(rows)
            return [[.1, .2, .7]]
        self.model = types.SimpleNamespace(classes_=['Exhausted', 'Fatigue', 'Normal'], predict_proba=predict)
        extractor = types.SimpleNamespace(extract_features=lambda frame: observation(), close=lambda: None)
        with patch('src.status_model.load_status_model', return_value=(self.model, {})):
            self.predictor = StatusPredictor(extractor=extractor, clock=lambda: self.now)
        self.addCleanup(self.predictor.close)

    def test_prediction_remains_stable_between_samples_with_current_metrics(self):
        for stamp in (0., .3):
            self.now = stamp
            self.assertFalse(self.predictor.predict_frame(object())['is_valid'])
        self.now = .6
        first = self.predictor.predict_frame(object())
        self.assertEqual(first['status'], 'Normal')
        self.now = .7
        current = self.predictor.predict_features(observation(ear=.21, roll=7.))
        self.assertEqual(current['status'], first['status'])
        self.assertEqual(current['confidence'], first['confidence'])
        self.assertEqual(current['metrics']['ear'], .21)
        self.assertEqual(current['metrics']['roll'], 7.)
        self.assertTrue(current['is_valid'])
        self.assertFalse(current['sampled'])
        self.assertEqual(len(self.model_calls), 1)

    def test_head_turn_retains_geometry_without_inventing_model_probability(self):
        result = self.predictor.predict_features(observation(yaw=48., roll=11.))
        self.assertEqual(result['status'], 'Distracted')
        self.assertEqual(result['source'], 'pose_rule')
        self.assertIsNone(result['confidence'])
        self.assertEqual(result['probabilities'], {})
        self.assertEqual(result['metrics']['yaw'], 48.)
        self.assertEqual(result['metrics']['roll'], 11.)
        self.assertEqual(result['bounding_box'], (10., 15., 50., 60.))
        self.assertIn('quy tắc', confidence_text(result))
        self.assertFalse(self.model_calls)
        self.assertNotIn('pts', to_serializable(result))

    def test_absent_face_or_snapshot_gap_cannot_reuse_a_previous_prediction(self):
        for stamp in (0., .3, .6):
            self.predictor.predict_features(observation(), captured_at=stamp)
        missing = self.predictor.predict_features(None, captured_at=.7)
        self.assertEqual(missing['status'], 'No_Face')
        self.assertFalse(missing['is_valid'])
        self.assertEqual(missing['metrics']['ear'], None)
        for stamp in (1., 1.3, 1.6):
            self.predictor.predict_features(observation(), captured_at=stamp)
        stale = self.predictor.predict_features(observation(), captured_at=3.)
        self.assertEqual(stale['status'], 'Buffering')
        self.assertFalse(stale['is_valid'])
        self.assertEqual(stale['valid_count'], 1)

    def test_invalid_measurements_do_not_trigger_a_distraction_rule(self):
        result = self.predictor.predict_features(observation(ear=float('nan'), yaw=60.))
        self.assertEqual(result['status'], 'Unknown')
        self.assertFalse(result['is_valid'])
        self.assertNotIn('rule_based', result)

    def test_snapshot_api_retains_strict_pose_gate_and_reports_roll(self):
        result = self.predictor.predict_status_detailed([object()] * 3)
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['metrics']['roll'], 2.)
        self.predictor.extractor.extract_features = lambda frame: observation(yaw=60.)
        result = self.predictor.predict_status_detailed([object()] * 3)
        self.assertFalse(result['is_valid'])
        self.assertEqual(result['status'], 'Unknown')
        self.assertEqual(result['metrics']['yaw'], 60.)


class StatusPreviewThreadTests(unittest.TestCase):
    def wait_until(self, check):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(.005)
        self.fail('worker did not reach the expected state')

    def test_one_worker_owns_camera_inference_and_closes_both_resources(self):
        owner = threading.get_ident()
        threads, closed = [], []
        class Camera:
            def read(self):
                threads.append(threading.get_ident())
                return True, 'frame'
            def release(self):
                closed.append(('camera', threading.get_ident()))
        class Predictor:
            def predict_frame(self, frame):
                threads.append(threading.get_ident())
                return {'status': 'Normal', 'is_valid': True}
            def close(self):
                closed.append(('model', threading.get_ident()))
        worker = StatusPreviewWorker(Predictor, Camera)
        try:
            self.wait_until(lambda: worker.snapshot()['state'] == 'running')
            self.assertEqual(worker.snapshot()['frame'], 'frame')
            self.assertEqual(len(set(threads)), 1)
            self.assertNotIn(owner, threads)
        finally:
            worker.close()
            worker.thread.join(2)
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual([name for name, _ in closed], ['camera', 'model'])
        self.assertTrue(all(thread != owner for _, thread in closed))
        self.assertIsNone(worker.snapshot()['frame'])

    def test_stalled_read_does_not_block_snapshot_or_close(self):
        entered, release, released = threading.Event(), threading.Event(), threading.Event()
        class Camera:
            def read(self):
                entered.set()
                release.wait(2)
                return False, None
            def release(self):
                released.set()
        predictor = types.SimpleNamespace(reset=lambda: None, close=lambda: None)
        worker = StatusPreviewWorker(lambda: predictor, Camera)
        try:
            self.assertTrue(entered.wait(1))
            start = time.monotonic()
            self.assertEqual(worker.snapshot()['state'], 'loading')
            worker.close()
            self.assertLess(time.monotonic() - start, .1)
        finally:
            release.set()
            worker.close()
            worker.thread.join(2)
        self.assertTrue(released.is_set())

    def test_camera_recovery_clears_old_prediction_and_failed_inference_releases(self):
        reset, closed = [], []
        frames = iter([(False, None), (True, 'frame')])
        camera = types.SimpleNamespace(read=lambda: next(frames), release=lambda: closed.append('camera'))
        def fail(frame):
            raise RuntimeError('model failure')
        predictor = types.SimpleNamespace(reset=lambda: reset.append(True), predict_frame=fail,
                                          close=lambda: closed.append('model'))
        worker = StatusPreviewWorker(lambda: predictor, lambda: camera)
        try:
            self.wait_until(lambda: worker.snapshot()['state'] == 'error')
            self.assertIn('model failure', worker.snapshot()['message'])
        finally:
            worker.close()
            worker.thread.join(2)
        self.assertEqual(reset, [True])
        self.assertEqual(closed, ['camera', 'model'])

    def test_invalid_model_is_reported_before_opening_camera(self):
        cameras = []
        def invalid():
            raise ValueError('incompatible model metadata')
        worker = StatusPreviewWorker(invalid, lambda: cameras.append(True))
        worker.thread.join(2)
        try:
            self.assertEqual(worker.snapshot()['state'], 'error')
            self.assertIn('metadata', worker.snapshot()['message'])
            self.assertEqual(cameras, [])
        finally:
            worker.close()


class StatusOverlayTests(unittest.TestCase):
    def test_overlay_draws_measured_geometry_and_confidence_on_a_copy(self):
        class Frame:
            shape = (100, 100, 3)
            def copy(self):
                return Frame()
        calls = []
        ui = types.SimpleNamespace(FONT_HERSHEY_SIMPLEX=1,
            rectangle=lambda *args: calls.append(('rectangle', args)),
            circle=lambda *args: calls.append(('circle', args)),
            putText=lambda *args: calls.append(('text', args)))
        frame = Frame()
        rendered = draw_status_frame(frame, dict(status='Fatigue', is_valid=True, confidence=.8,
            bounding_box=(10, 10, 80, 80), pts=[(20, 30)], metrics={'ear': .18, 'roll': 2.}), ui=ui)
        self.assertIsNot(rendered, frame)
        self.assertEqual({kind for kind, _ in calls}, {'rectangle', 'circle', 'text'})
        self.assertTrue(all(args[0] is rendered for _, args in calls))
        self.assertTrue(any('80.0%' in args[1] for kind, args in calls if kind == 'text'))
        self.assertTrue(any('EAR 0.180' in args[1] for kind, args in calls if kind == 'text'))


if __name__ == '__main__':
    unittest.main()
