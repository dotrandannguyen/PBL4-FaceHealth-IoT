import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_engine import UnifiedAttendanceEngine, SessionState
from src.attendance_transport import AttendanceTransport
from src.atomic_storage import save_gallery
from src.sequence_features import calculate_sequence_features


class Clock:
    now = 100.0
    def __call__(self):
        return self.now


class Frame:
    size = 1
    def copy(self):
        return self


class Predictor:
    def reset(self): pass
    def close(self): pass


class Transport:
    def __init__(self): self.payloads = []
    def send(self, payload):
        self.payloads.append(payload)
        return {"action": "checkin", "status": "success"}
    def retry_pending(self): return []


def analysis(status="Normal", valid=True):
    return {"scores": [1.0, 2.0, 1.0], "best": 1,
            "identity": {"match": True, "student_id": "SV001", "name": "Test", "similarity": .9},
            "status": {"status": status, "is_valid": valid, "confidence": .8}}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.transport = Transport()
        self.engine = UnifiedAttendanceEngine(self.temp.name, face_engine=object(),
            status_predictor=Predictor(), analyzer=lambda f: analysis(),
            transport=self.transport, clock=self.clock)
        self.addCleanup(self.engine.close)

    def capture(self):
        for second in (100.0, 100.31, 100.62):
            self.clock.now = second
            self.engine.update(Frame())

    def face_only_engine(self):
        self.engine.close()
        with patch.dict(sys.modules, {'src.predict_status': None}):
            self.engine = UnifiedAttendanceEngine(self.temp.name, face_engine=object(), face_only=True,
                analyzer=lambda frames: analysis(), transport=self.transport, clock=self.clock)
        self.addCleanup(self.engine.close)

    def camera_ai2_engine(self, label='Fatigue', valid=True):
        self.engine.close()
        self.engine = UnifiedAttendanceEngine(self.temp.name, face_engine=object(), camera_only=True,
            status_predictor=Predictor(), analyzer=lambda frames: analysis(label,valid),
            transport=self.transport, clock=self.clock)
        self.addCleanup(self.engine.close)

    def test_camera_ai2_classifies_without_fabricating_sensor_values(self):
        self.camera_ai2_engine()
        self.engine.start_session()
        self.engine.done_session(80,98)
        fake_cv2=types.SimpleNamespace(imwrite=lambda *args:False,imencode=lambda *args:(False,None))
        with patch.dict(sys.modules,{'cv2':fake_cv2}):
            self.capture()
            self.await_state(SessionState.COMPLETED)
        record=self.engine.last_completed_record
        self.assertEqual(record['assessment_mode'],'face_ai2')
        self.assertTrue(record['ai2_valid'])
        self.assertEqual(record['ai2_face_status'],'Fatigue')
        self.assertEqual(record['fusion_result']['final_status'],'Mệt mỏi (AI 2)')
        self.assertEqual(self.transport.payloads[0]['TrangThai'],'Fatigue')
        self.assertIsNone(self.transport.payloads[0]['NhipTim'])
        self.assertIsNone(self.transport.payloads[0]['SpO2'])
        self.assertIsNone(record['iot_metrics']['hr'])
        self.assertFalse(self.engine.iot_done_received)

    def test_camera_ai2_invalid_assessment_remains_unknown(self):
        self.camera_ai2_engine('Unknown',False)
        self.engine.start_session()
        fake_cv2=types.SimpleNamespace(imwrite=lambda *args:False,imencode=lambda *args:(False,None))
        with patch.dict(sys.modules,{'cv2':fake_cv2}):
            self.capture()
            self.await_state(SessionState.COMPLETED)
        self.assertEqual(self.transport.payloads[0]['TrangThai'],'Unknown')
        self.assertEqual(self.engine.last_completed_record['fusion_result']['final_status'],'Chưa phân tích được thể trạng')
        self.assertNotEqual(self.engine.last_completed_record['fusion_result']['alert_level'],'GREEN')

    def test_camera_ai2_normal_without_sensor_does_not_claim_complete_health(self):
        self.camera_ai2_engine('Normal')
        self.engine.start_session()
        fake_cv2=types.SimpleNamespace(imwrite=lambda *args:False,imencode=lambda *args:(False,None))
        with patch.dict(sys.modules,{'cv2':fake_cv2}):
            self.capture()
            self.await_state(SessionState.COMPLETED)
        record=self.engine.last_completed_record
        self.assertEqual(record['fusion_result']['final_status'],'Bình thường (AI 2)')
        self.assertNotEqual(record['fusion_result']['alert_level'],'GREEN')

    def test_face_only_skips_rf_and_sensor_data_and_sends_unknown(self):
        self.face_only_engine()
        self.engine.start_session()
        self.engine.done_session(80, 98)
        self.assertFalse(self.engine.iot_done_received)
        fake_cv2 = types.SimpleNamespace(imwrite=lambda *a: False, imencode=lambda *a: (False, None))
        with patch.dict(sys.modules, {'cv2': fake_cv2}):
            self.capture()
            self.await_state(SessionState.COMPLETED)
        record = self.engine.last_completed_record
        payload = self.transport.payloads[0]
        self.assertEqual(payload['TrangThai'], 'Unknown')
        self.assertIsNone(payload['NhipTim'])
        self.assertIsNone(payload['SpO2'])
        self.assertFalse(record['ai2_valid'])
        self.assertEqual(record['assessment_mode'], 'face_only')
        self.assertIsNone(record['iot_metrics']['hr'])
        self.assertNotEqual(record['fusion_result']['alert_level'], 'GREEN')
        self.assertEqual(record['attendance_action'], 'CHECK-IN')
        self.assertIsNone(self.engine.status_predictor)

    def test_face_only_cancel_before_finalization(self):
        self.face_only_engine()
        self.engine.start_session()
        for second in (100.0, 100.31):
            self.clock.now = second
            self.engine.update(Frame())
        self.engine.abort_session('USER_CANCEL')
        self.assertEqual(self.engine.state, SessionState.ABORTED)
        self.assertEqual(self.transport.payloads, [])

    def test_face_only_snapshot_gap_aborts_without_writing(self):
        self.face_only_engine()
        self.engine.start_session()
        for second in (100.0, 100.31, 101.0):
            self.clock.now = second
            self.engine.update(Frame())
        self.assertEqual(self.engine.state, SessionState.ABORTED)
        self.assertEqual(self.engine.abort_reason, 'SNAPSHOT_GAP_EXCEEDED')
        self.assertEqual(self.transport.payloads, [])

    def test_face_only_unrecognized_identity_never_sends_event(self):
        self.face_only_engine()
        self.engine._analyzer = lambda frames: dict(analysis(), identity={'match': False})
        self.engine.start_session()
        fake_cv2 = types.SimpleNamespace(imwrite=lambda *a: False, imencode=lambda *a: (False, None))
        with patch.dict(sys.modules, {'cv2': fake_cv2}):
            self.capture()
            self.await_state(SessionState.COMPLETED)
        self.assertEqual(self.transport.payloads, [])
        self.assertEqual(self.engine.last_completed_record['attendance_action'], 'NOT_RECORDED')

    def await_state(self, state):
        deadline = time.monotonic() + 3
        while self.engine.state != state and time.monotonic() < deadline:
            self.engine.update(Frame())
            time.sleep(.001)
        self.assertEqual(self.engine.state, state)

    def test_concurrent_done_events_finalize_once(self):
        self.engine.start_session()
        self.capture()
        calls = []
        self.engine._finalize_session = lambda: calls.append(1) or {"ok": True}
        workers = [threading.Thread(target=self.engine.done_session, args=(80, 98)) for _ in range(20)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.await_state(SessionState.COMPLETED)
        for _ in range(20): self.engine.update(Frame())
        self.assertEqual(calls, [1])

    def test_preview_does_not_wait_for_inference(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.engine._analyzer = lambda frames: release.wait(2) or analysis()
        self.engine.start_session()
        started = time.monotonic()
        self.capture()
        self.engine.update(Frame())
        self.assertLess(time.monotonic() - started, .25)
        release.set()

    def test_stale_session_and_invalid_metrics_ignored(self):
        event = self.engine.start_session()
        self.engine.done_session(80, 98, session_id="old")
        self.assertFalse(self.engine.iot_done_received)
        self.engine.done_session(80, float("nan"), session_id=event)
        self.assertFalse(self.engine.iot_done_received)
        self.engine.done_session(80, 98, session_id=event)
        self.assertTrue(self.engine.iot_done_received)
        self.assertIsNone(self.engine.start_session())

    def test_abort_during_inference_never_finalizes(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.engine._analyzer = lambda frames: (release.wait(2), analysis())[1]
        self.engine.start_session()
        self.capture()
        self.engine.abort_session()
        release.set()
        self.engine.update(Frame())
        self.assertEqual(self.engine.state, SessionState.ABORTED)
        self.assertEqual(self.transport.payloads, [])

    def test_hard_timeout_does_not_immediately_reset_aborted_state(self):
        self.engine.start_session()
        self.clock.now = 107
        self.engine.update(None)
        self.assertEqual(self.engine.state, SessionState.ABORTED)

    def test_snapshot_gap_outside_training_contract_aborts_without_writing(self):
        self.engine.start_session()
        for second in (100.0, 100.31, 101.0):
            self.clock.now = second
            self.engine.update(Frame())
        self.assertEqual(self.engine.state, SessionState.ABORTED)
        self.assertEqual(self.engine.abort_reason, 'SNAPSHOT_GAP_EXCEEDED')
        self.engine.done_session(80, 98)
        self.assertFalse(self.transport.payloads)

    def test_invalid_ai_missing_iot_is_not_green_and_log_has_web_result(self):
        self.engine.start_session()
        self.engine.captured_frames = [Frame()] * 3
        self.engine._accept_analysis(analysis("Unknown", False))
        fake_cv2 = types.SimpleNamespace(imwrite=lambda *a: False, imencode=lambda *a: (False, None))
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            record = self.engine._finalize_session()
        self.assertEqual(record["ai2_face_status"], "Unknown")
        self.assertNotEqual(record["fusion_result"]["alert_level"], "GREEN")
        self.assertEqual(record["evidence_snapshots"], ["", "", ""])
        saved = json.loads(self.engine.jsonl_log_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["web_result"]["status"], "success")
        self.assertEqual(self.transport.payloads[0]["event_id"], self.engine.session_id)


class OutboxTests(unittest.TestCase):
    def test_retry_preserves_payload_and_removes_only_after_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {"event_id": "12345678-1234-4234-8234-123456789abc", "occurred_at": "2026-10-19T08:00:00+07:00", "MaNV": 1}
            outbox = AttendanceTransport(directory, "http://unused", token="")
            self.assertEqual(outbox.send(payload)["status"], "pending")
            observed = []
            def send(url, **kwargs):
                observed.append(kwargs["json"])
                return types.SimpleNamespace(status_code=200, json=lambda: {"status": "success", "action": "checkin", "event_id": payload["event_id"]})
            outbox.sender, outbox.token = send, "test-token"
            outbox.retry_pending()
            self.assertEqual(observed, [payload])
            self.assertEqual(list(Path(directory).glob("*.json")), [])

    def test_existing_event_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = AttendanceTransport(directory, "http://unused", token="")
            payload = {"event_id": "12345678-1234-4234-8234-123456789abc", "MaNV": 1, "occurred_at": "2026-10-19T08:00:00+07:00"}
            outbox.send(payload)
            with self.assertRaises(ValueError): outbox.send(dict(payload, MaNV=2))


class PredictorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_numpy = types.SimpleNamespace(isfinite=math.isfinite, argmax=lambda x: max(range(len(x)), key=x.__getitem__))
        spec = importlib.util.spec_from_file_location("predictor_under_test", Path(__file__).resolve().parents[1] / "src/predict_status.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"numpy": fake_numpy, "joblib": types.ModuleType("joblib"),
                                     "status_features": types.SimpleNamespace(StatusFeatureExtractor=object)}):
            spec.loader.exec_module(module)
        cls.predictor_type = module.StatusPredictor

    def predictor(self, features):
        result = self.predictor_type.__new__(self.predictor_type)
        observations = iter(features)
        result.extractor = types.SimpleNamespace(extract_features=lambda frame: next(observations))
        result.max_yaw_deg, result.max_pitch_deg = 25, 35
        result.classes_ = ["Normal", "Fatigue", "Exhausted"]
        result.model = types.SimpleNamespace(predict_proba=lambda rows: [[.8, .1, .1]])
        return result

    def test_missing_landmarks_are_not_padded(self):
        result = self.predictor([None]).predict_status_detailed([Frame()] * 3)
        self.assertEqual(result["status"], "Unknown")
        self.assertFalse(result["is_valid"])

    def test_wrong_pose_and_nan_are_invalid(self):
        for yaw in (50, float("nan")):
            features = dict(ear=.3, mar=.1, pitch=180, yaw=yaw, roll=0)
            self.assertFalse(self.predictor([features]).predict_status_detailed([Frame()] * 3)["is_valid"])

    def test_three_valid_observations(self):
        features = dict(ear=.3, mar=.1, pitch=180, yaw=0, roll=0)
        result = self.predictor([features] * 3).predict_status_detailed([Frame()] * 3)
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["valid_count"], 3)
        self.assertIsNone(calculate_sequence_features([features, None, features]))

    def test_model_confidence_outside_probability_range_is_unknown(self):
        features = dict(ear=.3, mar=.1, pitch=180, yaw=0, roll=0)
        for confidence in (-.1, 1.1, float("nan")):
            predictor = self.predictor([features] * 3)
            predictor.model = types.SimpleNamespace(predict_proba=lambda rows: [[confidence, -1, -1]])
            result = predictor.predict_status_detailed([Frame()] * 3)
            self.assertFalse(result["is_valid"])
            self.assertEqual(result["status"], "Unknown")


if __name__ == "__main__":
    unittest.main()
