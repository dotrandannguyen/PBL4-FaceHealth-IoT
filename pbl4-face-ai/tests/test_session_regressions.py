"""Session/outbox contracts without loading models, cameras or the project DB."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.attendance_transport import AttendanceTransport
from unified_engine import UnifiedAttendanceEngine, SessionState
import test_attendance as fixtures


def event(number, employee=1, occurred="2026-10-20T08:00:00+07:00"):
    return {"event_id": str(UUID(int=(number << 96) | (4 << 76) | (2 << 62))),
            "MaNV": employee, "occurred_at": occurred, "MaTB": 1,
            "TrangThai": "Normal", "NhipTim": 80, "SpO2": 98, "image": None}


def ack(payload):
    return types.SimpleNamespace(status_code=200, json=lambda: {
        "event_id": payload["event_id"], "status": "success", "action": "checkin"})


class OutboxRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.observed = []
        def sender(url, **kwargs):
            self.observed.append(kwargs["json"].copy())
            return ack(kwargs["json"])
        self.sender = sender
        self.outbox = AttendanceTransport(self.temp.name, "http://unused", token="", sender=sender)

    def queue(self, payload):
        self.assertEqual(self.outbox.send(payload)["status"], "pending")

    def test_retry_uses_timestamp_not_uuid_order(self):
        later, earlier = event(1, occurred="2026-10-20T09:00:00+07:00"), event(9)
        self.queue(later)
        self.queue(earlier)
        self.outbox.token = "test-only"
        self.outbox.retry_pending()
        self.assertEqual(self.observed, [earlier, later])

    def test_timestamp_order_accounts_for_timezone(self):
        # 02:00 UTC is 09:00 in Vietnam; textual order alone would be wrong.
        later = event(1, occurred="2026-10-20T02:00:00+00:00")
        earlier = event(2, occurred="2026-10-20T08:00:00+07:00")
        self.queue(later)
        self.queue(earlier)
        self.outbox.token = "test-only"
        self.outbox.retry_pending()
        self.assertEqual(self.observed, [earlier, later])

    def test_send_keeps_newer_event_pending_when_earlier_fails(self):
        first = event(1)
        second = event(2, occurred="2026-10-20T09:00:00+07:00")
        self.queue(first)
        def unavailable(url, **kwargs):
            self.observed.append(kwargs["json"])
            return types.SimpleNamespace(status_code=503, json=lambda: {})
        self.outbox.sender, self.outbox.token = unavailable, "test-only"
        result = self.outbox.send(second)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.observed, [first])
        self.assertEqual(len(list(Path(self.temp.name).glob("*.json"))), 2)

    def test_failed_employee_does_not_block_other_employee(self):
        first, second = event(1), event(2, occurred="2026-10-20T09:00:00+07:00")
        other = event(3, employee=2)
        for payload in (first, second, other): self.queue(payload)
        def sender(url, **kwargs):
            payload = kwargs["json"]
            self.observed.append(payload)
            if payload["MaNV"] == 1:
                return types.SimpleNamespace(status_code=409, json=lambda: {})
            return ack(payload)
        self.outbox.sender, self.outbox.token = sender, "test-only"
        self.outbox.retry_pending()
        self.assertEqual(self.observed, [first, other])
        self.assertTrue((Path(self.temp.name) / (second["event_id"] + ".json")).exists())

    def test_wrong_ack_cannot_delete_pending_event(self):
        payload = event(1)
        self.outbox.token = "test-only"
        self.outbox.sender = lambda *a, **k: ack(event(2))
        self.assertEqual(self.outbox.send(payload)["status"], "pending")
        self.assertTrue((Path(self.temp.name) / (payload["event_id"] + ".json")).exists())

    def test_lost_ack_replays_same_payload_and_receipt_prevents_third_send(self):
        payload = event(1)
        self.outbox.token = "test-only"
        def sender(url, **kwargs):
            self.observed.append(kwargs["json"].copy())
            if len(self.observed) == 1:
                raise TimeoutError("Server committed but response was lost")
            return ack(kwargs["json"])
        self.outbox.sender = sender
        self.assertEqual(self.outbox.send(payload)["status"], "pending")
        self.outbox.retry_pending()
        self.assertEqual(self.outbox.send(payload)["status"], "success")
        self.assertEqual(self.observed, [payload, payload])
        receipt = Path(self.temp.name) / "receipts" / (payload["event_id"] + ".json")
        self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["web_result"]["event_id"], payload["event_id"])
        with self.assertRaises(ValueError): self.outbox.send(dict(payload, NhipTim=81))

    def test_missing_timestamp_or_employee_never_creates_queue_file(self):
        for key in ("occurred_at", "MaNV"):
            payload = event(1)
            payload.pop(key)
            with self.assertRaises((ValueError, KeyError)):
                self.outbox.send(payload)
        payload = dict(event(1), occurred_at="2026-10-20T08:00:00")
        with self.assertRaises(ValueError): self.outbox.send(payload)
        self.assertEqual(list(Path(self.temp.name).glob("*.json")), [])

    def test_corrupt_entry_is_preserved_and_blocks_sending(self):
        corrupt = Path(self.temp.name) / "broken.json"
        corrupt.write_text("{", encoding="utf-8")
        self.outbox.token = "test-only"
        with self.assertLogs("src.attendance_transport", level="ERROR"):
            self.assertEqual(self.outbox.send(event(1))["status"], "pending")
            self.assertEqual(self.outbox.retry_pending(), [])
        self.assertEqual(corrupt.read_text(encoding="utf-8"), "{")
        self.assertEqual(self.observed, [])

    def test_send_attempts_are_bounded(self):
        for number in range(1, 8):
            self.queue(event(number, occurred=f"2026-10-20T08:0{number}:00+07:00"))
        self.outbox.token = "test-only"
        newest = event(8, occurred="2026-10-20T08:08:00+07:00")
        self.assertEqual(self.outbox.send(newest)["status"], "pending")
        self.assertEqual(len(self.observed), self.outbox.MAX_SEND_ATTEMPTS)
        self.outbox.retry_pending()
        self.assertEqual(len(self.observed), 8)

    def test_non_json_response_keeps_pending(self):
        self.outbox.token = "test-only"
        self.outbox.sender = lambda *a, **k: types.SimpleNamespace(status_code=200, json=lambda: [])
        self.assertEqual(self.outbox.send(event(1))["status"], "pending")
        self.assertEqual(self.outbox.retry_pending(limit=0), [])


class SessionRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = fixtures.Clock()
        self.transport = fixtures.Transport()
        self.engine = UnifiedAttendanceEngine(self.temp.name, face_engine=object(),
            status_predictor=fixtures.Predictor(), analyzer=lambda frames: fixtures.analysis(),
            transport=self.transport, clock=self.clock)
        self.addCleanup(self.engine.close)

    def prime(self, result=None):
        self.engine.start_session()
        self.engine.captured_frames = [fixtures.Frame()] * 3
        self.engine._accept_analysis(result or fixtures.analysis())

    def test_bad_confidence_and_similarity_never_reach_json_as_nan(self):
        result = fixtures.analysis()
        result["status"]["confidence"] = float("nan")
        result["identity"]["similarity"] = float("inf")
        self.prime(result)
        self.assertFalse(self.engine.ai2_valid)
        self.assertFalse(self.engine.identity_matched)
        self.assertEqual(self.engine.session_status_history, ["Unknown"])
        self.assertEqual(self.engine.identity_sim, 0)

    def test_invalid_serial_values_are_ignored(self):
        self.assertIsNone(self.engine.start_session(ir=float("nan")))
        self.engine.start_session()
        for hr, spo2 in ((True, 98), (80, "98"), (301, 98), (80, 101)):
            self.engine.done_session(hr, spo2)
            self.assertFalse(self.engine.iot_done_received)

    def test_log_failure_does_not_erase_server_ack(self):
        self.prime()
        cv2 = types.SimpleNamespace(imwrite=lambda *a: False, imencode=lambda *a: (False, None))
        with patch.dict(sys.modules, {"cv2": cv2}), patch("builtins.open", side_effect=OSError("disk full")):
            with self.assertLogs("unified_engine", level="ERROR"):
                record = self.engine._finalize_session()
        self.assertEqual(record["attendance_action"], "CHECK-IN")
        self.assertEqual(record["web_result"]["status"], "success")
        self.assertFalse(record["local_log_saved"])

    def test_retry_worker_cannot_delay_inference(self):
        release, entered, analyzed = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def retry():
            entered.set()
            release.wait(2)
            return []
        self.transport.retry_pending = retry
        self.clock.now = 131
        self.engine.update(None)
        self.assertTrue(entered.wait(1))
        def analyze(frames):
            analyzed.set()
            return fixtures.analysis()
        self.engine._analyzer = analyze
        self.engine.start_session()
        for second in (131, 131.31, 131.62):
            self.clock.now = second
            self.engine.update(fixtures.Frame())
        self.assertTrue(analyzed.wait(1), "Inference queued behind an offline retry")
        release.set()

    def test_accepted_finalization_is_drained_on_close(self):
        release, entered = threading.Event(), threading.Event()
        calls = []
        self.addCleanup(release.set)
        def blocker():
            entered.set()
            release.wait(2)
        self.engine._pool.submit(blocker)
        self.assertTrue(entered.wait(1))
        self.engine._future = self.engine._pool.submit(lambda: calls.append("saved"))
        self.engine.state = SessionState.FINALIZING
        release.set()
        self.engine.close()
        self.assertEqual(calls, ["saved"])

    def test_all_three_images_must_belong_to_same_person(self):
        cv2 = types.SimpleNamespace(cvtColor=lambda *a: None, COLOR_BGR2GRAY=0, CV_64F=0,
            Laplacian=lambda *a: types.SimpleNamespace(var=lambda: 1.0))
        numpy = types.SimpleNamespace(argmax=lambda x: 0, dot=lambda a, b: sum(x*y for x,y in zip(a,b)))
        identify = Mock(return_value=fixtures.analysis()["identity"])
        verify = types.ModuleType("src.verify")
        verify.identify = identify
        self.engine.status_predictor = types.SimpleNamespace(predict_status_detailed=lambda frames: fixtures.analysis()["status"], close=lambda: None)
        cases = [([[1, 0], [1, 0], [1, 0]], True),
                 ([[1, 0], [0, 1], [1, 0]], False),
                 ([[1, 0], None, [1, 0]], False)]
        with patch.dict(sys.modules, {"cv2": cv2, "numpy": numpy, "src.verify": verify}):
            for embeddings, expected in cases:
                identify.reset_mock()
                sequence = iter(embeddings)
                self.engine.face_engine = types.SimpleNamespace(embed=lambda frame: next(sequence))
                result = self.engine._analyze_snapshots([fixtures.Frame()] * 3)
                self.assertEqual(bool(result["identity"].get("match")), expected)
                self.assertEqual(identify.call_count, int(expected))
                if expected:
                    self.assertEqual(identify.call_args.kwargs["probe_embedding"], [1, 0])


if __name__ == "__main__":
    unittest.main()
