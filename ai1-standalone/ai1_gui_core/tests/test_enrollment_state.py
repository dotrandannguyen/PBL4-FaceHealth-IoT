"""Hardware-free checks for manual five-pose enrollment capture."""

import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ai1_gui_core.gui import AI1Gui
from ai1_gui_core.enrollment_state import EnrollmentCaptureState
from ai1_standalone_core.ai1_adapter import classify_pose, validate_enrollment_frame
from ai1_standalone_core.config import POSES


def basis(index):
    value = np.zeros(512, dtype=np.float32)
    value[index] = 1.0
    return value


def valid_outcome(detected_pose="between", embedding=None):
    return {"status": "OK", "detected_pose": detected_pose,
            "embedding": embedding if embedding is not None else basis(0)}


class FakePoseEngine:
    def __init__(self, yaw, pitch):
        self.face = {
            "embedding": basis(0), "detection_score": 0.94,
            "bbox": [170, 100, 370, 370],
            "head_pose": {"yaw": yaw, "pitch": pitch},
        }

    def detect_embeddings(self, _frame):
        return [self.face]


def make_test_frame():
    return np.random.default_rng(201).integers(0, 256, size=(480, 640, 3), dtype=np.uint8)


class Value:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value


class EnrollmentStateTests(unittest.TestCase):
    def test_pose_classifier_remains_available_for_debug(self):
        def face(yaw, pitch):
            return {"head_pose": {"yaw": yaw, "pitch": pitch}}

        self.assertEqual(classify_pose(face(7.2, 14.1)), "frontal")
        self.assertEqual(classify_pose(face(22.0, 24.0)), "left")
        self.assertEqual(classify_pose(face(-22.0, -24.0)), "right")
        self.assertEqual(classify_pose(face(14.0, 22.0)), "up")
        self.assertEqual(classify_pose(face(-14.0, -22.0)), "down")
        self.assertEqual(classify_pose(face(60.0, 0.0)), "between")

    def test_pose_mismatch_is_diagnostic_and_does_not_reject_quality_valid_frame(self):
        outcome = validate_enrollment_frame(
            FakePoseEngine(0, 23), make_test_frame(), "frontal", enforce_pose=False
        )
        self.assertEqual(outcome["status"], "OK", outcome)
        self.assertEqual(outcome["code"], "OK")
        self.assertEqual(outcome["expected_pose"], "frontal")
        self.assertEqual(outcome["detected_pose"], "up")
        self.assertEqual(outcome["diagnostics"]["pitch"], 23.0)
        self.assertEqual(outcome["diagnostics"]["quality_result"], "PASS")

    def test_legacy_standalone_caller_keeps_pose_gate_by_default(self):
        outcome = validate_enrollment_frame(FakePoseEngine(0, 23), make_test_frame(), "frontal")
        self.assertEqual(outcome["status"], "RETRY")
        self.assertEqual(outcome["code"], "WRONG POSE")
        self.assertIn("pitch=23", outcome["reason"])

    def test_manual_adapter_still_rejects_bad_quality(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        outcome = validate_enrollment_frame(
            FakePoseEngine(0, 0), frame, "frontal", enforce_pose=False
        )
        self.assertEqual(outcome["status"], "RETRY")
        self.assertEqual(outcome["code"], "BAD LIGHTING")

    def test_quality_metrics_and_scrfd_data_remain_present(self):
        outcome = validate_enrollment_frame(
            FakePoseEngine(7.2, 14.1), make_test_frame(), "frontal", enforce_pose=False
        )
        debug = outcome["diagnostics"]
        self.assertEqual(outcome["status"], "OK")
        self.assertAlmostEqual(debug["detection_score"], 0.94)
        self.assertEqual(debug["bbox"], [170.0, 100.0, 370.0, 370.0])
        self.assertAlmostEqual(debug["bbox_width_frame_ratio"], 200 / 640)
        self.assertAlmostEqual(debug["yaw"], 7.2)
        self.assertAlmostEqual(debug["pitch"], 14.1)
        self.assertIsNotNone(debug["brightness"])
        self.assertIsNotNone(debug["sharpness"])
        self.assertEqual(debug["quality_result"], "PASS")

    def test_manual_capture_advances_pose_even_if_detected_pose_disagrees(self):
        state = EnrollmentCaptureState()
        result = state.capture(valid_outcome("between"))
        self.assertEqual(result, {"pose": "frontal", "captured": 1, "complete": False})
        self.assertEqual(state.current_pose, "left")

    def test_quality_failure_does_not_capture_or_advance(self):
        state = EnrollmentCaptureState()
        outcome = {"status": "RETRY", "code": "TOO BLURRY", "reason": "blur"}
        with self.assertRaisesRegex(ValueError, "TOO BLURRY"):
            state.capture(outcome)
        self.assertEqual(state.current_pose, "frontal")
        self.assertFalse(state.embeddings)

    def test_same_person_check_rejects_other_identity(self):
        state = EnrollmentCaptureState(same_person_threshold=0.45)
        state.capture(valid_outcome("between", basis(0)))
        with self.assertRaisesRegex(ValueError, "frontal reference"):
            state.capture(valid_outcome("left", basis(1)))
        self.assertEqual(state.current_pose, "left")
        self.assertEqual(set(state.embeddings), {"frontal"})

    def test_manual_capture_sequence_reaches_exactly_five_pose_samples(self):
        state = EnrollmentCaptureState()
        for pose in POSES:
            result = state.capture(valid_outcome("between", basis(0)))
            self.assertEqual(result["pose"], pose)
        self.assertTrue(state.complete)
        self.assertIsNone(state.current_pose)
        self.assertTrue(state.validate_complete()["valid"])

    def test_worker_captures_five_manual_requests_then_waits_for_save(self):
        frame = make_test_frame()
        state = EnrollmentCaptureState()
        requests = queue.Queue()
        for _ in POSES:
            requests.put({"action": "capture"})
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            stage = Path(temporary)
            sequence = [0]

            def get_packet():
                sequence[0] += 1
                return SimpleNamespace(
                    frame=frame.copy(), sequence=sequence[0], captured_at=time.monotonic()
                )

            gui = AI1Gui.__new__(AI1Gui)
            gui.enrollment = {
                "identity": "MaNV_2", "state": state, "requests": requests,
                "stage": stage, "frames": {},
            }
            gui.controller = SimpleNamespace(
                engine=FakePoseEngine(0, 168), get_packet=get_packet,
                find_duplicate_employee=lambda _embedding, exclude_identity=None: None,
            )
            gui.events = queue.Queue()
            with patch("ai1_gui_core.gui._atomic_write_jpeg") as write_jpeg:
                result = gui._enrollment_worker("session", threading.Event())

            self.assertEqual(result["status"], "READY_TO_SAVE")
            self.assertEqual(set(state.embeddings), set(POSES))
            self.assertEqual(write_jpeg.call_count, 5)
            events = []
            while not gui.events.empty():
                events.append(gui.events.get_nowait())
            captured = [item[2]["pose"] for item in events
                        if item[0] == "enrollment_captured"]
            self.assertEqual(captured, list(POSES))
            self.assertEqual(sum(item[2].get("captured") is True for item in events
                                 if item[0] == "enrollment_capture_result"), 5)

    def test_worker_stops_enrollment_when_frontal_matches_another_employee(self):
        frame = make_test_frame()
        state = EnrollmentCaptureState()
        requests = queue.Queue()
        requests.put({"action": "capture"})
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            stage = Path(temporary)
            packet = SimpleNamespace(frame=frame, sequence=1, captured_at=time.monotonic())
            duplicate = {"MaNV": "MaNV_1", "HoTen": "Employee One",
                         "similarity": 0.91, "threshold": 0.45}
            gui = AI1Gui.__new__(AI1Gui)
            gui.enrollment = {
                "identity": "MaNV_2", "state": state, "requests": requests,
                "stage": stage, "frames": {},
            }
            gui.controller = SimpleNamespace(
                engine=FakePoseEngine(0, 168), get_packet=lambda: packet,
                find_duplicate_employee=lambda _embedding, exclude_identity=None: duplicate,
            )
            gui.events = queue.Queue()
            with patch("ai1_gui_core.gui._atomic_write_jpeg") as write_jpeg:
                result = gui._enrollment_worker("session", threading.Event())

            self.assertEqual(result, {"status": "DUPLICATE_FACE", "duplicate": duplicate})
            self.assertEqual(state.embeddings, {})
            write_jpeg.assert_not_called()

    def test_invalid_embedding_is_rejected(self):
        state = EnrollmentCaptureState()
        with self.assertRaises(ValueError):
            state.capture(valid_outcome("frontal", np.zeros(511, dtype=np.float32)))
        self.assertEqual(state.current_pose, "frontal")

    def test_final_validation_requires_all_five_samples(self):
        state = EnrollmentCaptureState()
        self.assertFalse(state.validate_complete()["valid"])

    def test_space_key_only_queues_one_capture_during_enrollment(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.active_operation = "enrollment"
        gui.enrollment = {"requests": queue.Queue(), "ready_to_save": False}
        gui.space_is_down = False
        gui.space_capture_pending = False
        gui.state_var = Value()

        self.assertEqual(gui._on_space_press(), "break")
        self.assertEqual(gui._on_space_press(), "break")
        self.assertEqual(gui.enrollment["requests"].qsize(), 1)
        self.assertEqual(gui.enrollment["requests"].get_nowait(), {"action": "capture"})

        gui._on_space_release()
        gui.space_capture_pending = False  # GUI clears this when the worker responds.
        self.assertEqual(gui._on_space_press(), "break")
        self.assertEqual(gui.enrollment["requests"].qsize(), 1)

        gui.active_operation = "recognition"
        self.assertIsNone(gui._on_space_press())
        self.assertEqual(gui.enrollment["requests"].qsize(), 1)


if __name__ == "__main__":
    unittest.main()
