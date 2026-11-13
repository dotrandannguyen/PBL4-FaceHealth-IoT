"""Recognition-session logic tests that use generated in-memory frames only."""

import threading
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from unittest.mock import patch

from camera_source import FramePacket
from face_engine import assess_capture_quality
from ai1_standalone_core.config import (
    ENROLLMENT_CENTER_TOLERANCE,
    ENROLLMENT_EDGE_MARGIN_RATIO,
    ENROLLMENT_MAX_SIZE_RATIO,
    FRAME_CONSISTENCY_THRESHOLD,
    PROJECT_ROOT,
)
from ai1_standalone_core.recognition import (
    assess_recognition_face_quality,
    check_three_frame_consistency,
    face_sharpness,
    recognize_sequence_from_source,
)
from ai1_gui_core.gui import AI1Gui


def basis(index=0):
    vector = np.zeros(512, dtype=np.float32)
    vector[index] = 1.0
    return vector


def sharp_frame(seed):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(180, 160, 3), dtype=np.uint8)


def wide_sharp_frame(seed):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(480, 640, 3), dtype=np.uint8)


class FakeEngine:
    def __init__(self, embeddings=None):
        self.embeddings = list(embeddings or [basis()])
        self.calls = 0

    def detect_embeddings(self, _frame):
        index = min(self.calls, len(self.embeddings) - 1)
        self.calls += 1
        return [{"embedding": self.embeddings[index], "detection_score": 0.99,
                 "bbox": [10, 10, 145, 170]}]


class MultipleFaceEngine(FakeEngine):
    def detect_embeddings(self, _frame):
        return [
            {"embedding": basis(0), "detection_score": 0.99, "bbox": [10, 10, 70, 80]},
            {"embedding": basis(1), "detection_score": 0.99, "bbox": [80, 10, 140, 80]},
        ]


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FreshSource:
    def __init__(self):
        self.sequence = 0

    def get_frame(self):
        self.sequence += 1
        return FramePacket(sharp_frame(self.sequence), self.sequence, time.monotonic())


class StaleSource:
    def get_frame(self):
        return FramePacket(sharp_frame(1), 1, time.monotonic() - 2.0)


class RecognitionTests(unittest.TestCase):
    @staticmethod
    def display_gui():
        gui = AI1Gui.__new__(AI1Gui)
        gui.last_result_status = None
        gui.controller = type("Controller", (), {
            "threshold": 0.45,
            "employees": [{"MaNV": "MaNV_1", "HoTen": "thang"}],
            "gallery": {"MaNV_1": {"HoTen": "thang", "embeddings": (basis(),) * 5}},
            "ready": True,
        })()
        gui.threshold_var = Value("")
        gui.score_var = Value("")
        gui.latency_var = Value("")
        gui.sharpness_var = Value("")
        gui.progress_var = Value("")
        gui.state_var = Value("")
        gui.prediction_var = Value("")
        gui.preview_hint = Value("")
        gui.best_result_frame = None
        gui.best_frame_until = 0.0
        gui.result_card_until = 0.0
        gui.result_title_var = Value("")
        gui.result_detail_var = Value("")
        return gui

    def test_match_unknown_and_retry_have_distinct_clear_ui_results(self):
        match_gui = self.display_gui()
        match_gui._show_recognition({
            "status": "MATCH", "predicted_id": "MaNV_1", "score": 0.783,
            "threshold": 0.45, "latency_ms": 91.2, "sharpness": 52.0,
            "captured_frames": 3,
        })
        self.assertEqual(match_gui.state_var.get(), "KẾT QUẢ: MATCH")
        self.assertIn("Employee: MaNV_1 - thang", match_gui.prediction_var.get())
        self.assertIn("Similarity: 0.783", match_gui.prediction_var.get())
        self.assertIn("Threshold: 0.450", match_gui.prediction_var.get())
        self.assertEqual(match_gui.result_title_var.get(), "MATCH")
        self.assertIn("Employee ID: MaNV_1", match_gui.result_detail_var.get())
        self.assertGreater(match_gui.result_card_until, time.monotonic())

        unknown_gui = self.display_gui()
        unknown_gui._show_recognition({
            "status": "UNKNOWN", "predicted_id": "UNKNOWN", "score": 0.31,
            "threshold": 0.45, "latency_ms": 80.0, "sharpness": 45.0,
            "captured_frames": 3,
        })
        self.assertEqual(unknown_gui.state_var.get(), "KẾT QUẢ: UNKNOWN")
        self.assertIn("Best similarity: 0.310", unknown_gui.prediction_var.get())
        self.assertNotIn("MaNV_1", unknown_gui.prediction_var.get())
        self.assertEqual(unknown_gui.result_title_var.get(), "UNKNOWN")
        self.assertIn("Không tìm thấy nhân viên phù hợp", unknown_gui.result_detail_var.get())

        retry_gui = self.display_gui()
        retry_gui._show_recognition({
            "status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
            "threshold": 0.45, "reason": "MULTIPLE FACES", "latency_ms": 12.0,
            "sharpness": 0.0, "captured_frames": 0,
        })
        self.assertEqual(retry_gui.state_var.get(), "KẾT QUẢ: RETRY")
        self.assertIn("MULTIPLE FACES", retry_gui.prediction_var.get())
        self.assertEqual(retry_gui.preview_hint.get(), "MULTIPLE FACES")
        self.assertEqual(retry_gui.result_title_var.get(), "RETRY")
        self.assertIn("Reason: MULTIPLE FACES", retry_gui.result_detail_var.get())

    def test_gui_refresh_employee_list_renders_loaded_local_gallery_counts(self):
        class Tree:
            def __init__(self):
                self.rows = {}

            def get_children(self):
                return tuple(self.rows)

            def delete(self, item):
                self.rows.pop(item, None)

            def insert(self, _parent, _where, iid, values):
                self.rows[iid] = values

        gui = AI1Gui.__new__(AI1Gui)
        gui.controller = type("Controller", (), {
            "ready": True,
            "employees": [{"MaNV": "1", "HoTen": "thang"}],
            "gallery": {"1": {"HoTen": "thang", "embeddings": (basis(),) * 5}},
        })()
        gui.employee_table = Tree()
        gui.gallery_status_var = Value("")
        gui.header_status = Value("")
        gui.header_label = type("Label", (), {"configure": lambda _self, **_kwargs: None})()

        counts = gui.refresh_employee_list()

        self.assertEqual(gui.employee_table.rows["1"], ("1", "thang", 5))
        self.assertEqual(gui.gallery_status_var.get(), "Gallery: 1 nhân viên / 5 embeddings")
        self.assertEqual(counts, {"employees": 1, "gallery_employees": 1, "embeddings": 5})
        self.assertIn("1 nhân viên standalone", gui.header_status.get())

    def test_duplicate_face_warning_shows_existing_employee_and_similarity(self):
        gui = self.display_gui()
        gui.root = object()
        with patch("ai1_gui_core.gui.messagebox.showwarning") as warning:
            gui._show_duplicate_face({
                "MaNV": "MaNV_1", "HoTen": "thang",
                "similarity": 0.783, "threshold": 0.45,
            })
        self.assertEqual(gui.state_var.get(), "TRẠNG THÁI: DUPLICATE FACE")
        self.assertIn("Employee: MaNV_1 - thang", gui.prediction_var.get())
        self.assertIn("Similarity: 0.783", gui.prediction_var.get())
        warning.assert_called_once()

    def test_existing_employee_id_offers_clear_reenrollment_and_prefills_name(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.controller = SimpleNamespace(
            source=object(),
            employees=[{"MaNV": "1", "HoTen": "thang"}],
            store=SimpleNamespace(
                root=PROJECT_ROOT,
                images_root=PROJECT_ROOT / "ai1_standalone_data" / "images",
                ensure=lambda: None,
            ),
        )
        gui.id_var = Value("1")
        gui.name_var = Value("")
        gui.root = object()
        gui._reset_thumbnails = lambda: None
        gui.progress = SimpleNamespace(configure=lambda **_kwargs: None)
        gui.progress_var = Value("")
        gui.quality_var = Value("")
        gui.pose_var = Value("")
        gui.detected_pose_var = Value("")
        gui.capture_hint_var = Value("")
        gui.state_var = Value("")
        gui._start_session = lambda _kind, _worker: "test-session"
        gui._set_controls = lambda: None

        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as stage:
            with patch("ai1_gui_core.gui.tempfile.mkdtemp", return_value=stage), \
                 patch("ai1_gui_core.gui.messagebox.askyesno", return_value=True) as confirm:
                gui._begin_registration()

        message = confirm.call_args.args[1]
        self.assertIn("Employee ID 1 đã tồn tại: thang", message)
        self.assertIn("thay thế bộ khuôn mặt", message)
        self.assertEqual(gui.name_var.get(), "thang")
        self.assertTrue(gui.enrollment["overwrite"])
        self.assertEqual(gui.enrollment["identity"], "1")

    def test_temporal_consistency_uses_point_six_threshold(self):
        self.assertEqual(FRAME_CONSISTENCY_THRESHOLD, 0.60)
        self.assertTrue(check_three_frame_consistency([basis(), basis(), basis()])["valid"])
        self.assertFalse(check_three_frame_consistency([basis(0), basis(0), basis(1)])["valid"])

    def test_laplacian_sharpness_distinguishes_flat_and_detailed_frame(self):
        flat = np.full((180, 160, 3), 127, dtype=np.uint8)
        detailed = sharp_frame(8)
        self.assertLess(face_sharpness(flat, [10, 10, 145, 170]),
                        face_sharpness(detailed, [10, 10, 145, 170]))

    def test_three_fresh_distinct_snapshots_and_progress(self):
        progress = []
        frame_updates = []
        engine = FakeEngine()
        gallery = {"MaNV_1": {"HoTen": "Employee One", "embeddings": (basis(),) * 5}}
        result = recognize_sequence_from_source(
            engine, FreshSource(), gallery, threading.Event(),
            progress_callback=lambda count, total: progress.append((count, total)),
            frame_callback=frame_updates.append,
            timeout_seconds=2.0,
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["captured_frames"], 3)
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])
        self.assertEqual(len(frame_updates), 3)
        self.assertEqual(frame_updates[0]["bbox"], [10, 10, 145, 170])
        self.assertEqual(frame_updates[0]["quality_status"], "READY")
        self.assertEqual(engine.calls, 3)
        self.assertEqual(result["threshold"], 0.45)
        self.assertIn("best_frame", result)

    def test_stale_frame_times_out_as_retry(self):
        result = recognize_sequence_from_source(
            FakeEngine(), StaleSource(), {}, threading.Event(), timeout_seconds=0.05,
        )
        self.assertEqual(result["status"], "RETRY")
        self.assertIn("STALE_FRAME", result["reason"])
        self.assertEqual(result["captured_frames"], 0)

    def test_inconsistent_snapshots_retry_without_gallery_match(self):
        engine = FakeEngine([basis(0), basis(0), basis(1)])
        gallery = {"MaNV_1": {"HoTen": "Employee One", "embeddings": (basis(0),) * 5}}
        result = recognize_sequence_from_source(
            engine, FreshSource(), gallery, threading.Event(), timeout_seconds=2.0,
        )
        self.assertEqual(result["status"], "RETRY")
        self.assertIn("INCONSISTENT", result["reason"])
        self.assertEqual(result["predicted_id"], "UNKNOWN")

    def test_recognition_accepts_face_shifted_from_guide_center(self):
        frame = wide_sharp_frame(101)
        face = {"bbox": [80, 100, 240, 320], "detection_score": 0.95}
        quality = assess_recognition_face_quality(frame, face)
        self.assertTrue(quality["ready"], quality)

    def test_recognition_rejects_small_cropped_edge_and_blurry_faces(self):
        frame = wide_sharp_frame(102)
        self.assertEqual(
            assess_recognition_face_quality(
                frame, {"bbox": [100, 100, 140, 150], "detection_score": 0.95}
            )["code"],
            "FACE TOO SMALL",
        )
        self.assertEqual(
            assess_recognition_face_quality(
                frame, {"bbox": [10, 10, 630, 460], "detection_score": 0.95}
            )["code"],
            "FACE TOO LARGE",
        )
        self.assertEqual(
            assess_recognition_face_quality(
                frame, {"bbox": [-20, 100, 180, 330], "detection_score": 0.95}
            )["code"],
            "FACE CROPPED",
        )
        self.assertEqual(
            assess_recognition_face_quality(
                frame, {"bbox": [0, 100, 200, 330], "detection_score": 0.95}
            )["code"],
            "FACE TOO CLOSE TO EDGE",
        )
        blurry = np.full((480, 640, 3), 127, dtype=np.uint8)
        self.assertEqual(
            assess_recognition_face_quality(
                blurry, {"bbox": [120, 100, 290, 320], "detection_score": 0.95}
            )["code"],
            "TOO BLURRY",
        )

    def test_multiple_faces_retry_before_collecting_a_snapshot(self):
        result = recognize_sequence_from_source(
            MultipleFaceEngine(), FreshSource(), {}, threading.Event(), timeout_seconds=2.0,
        )
        self.assertEqual(result["status"], "RETRY")
        self.assertIn("MULTIPLE FACES", result["reason"])
        self.assertEqual(result["captured_frames"], 0)

    def test_standalone_enrollment_center_gate_is_relaxed_without_changing_default(self):
        frame = wide_sharp_frame(103)
        shifted_face = {
            "bbox": [160, 120, 360, 360],
            "detection_score": 0.95,
        }
        production_default = assess_capture_quality(frame, shifted_face)
        standalone = assess_capture_quality(
            frame, shifted_face,
            center_tolerance=ENROLLMENT_CENTER_TOLERANCE,
            max_size_ratio=ENROLLMENT_MAX_SIZE_RATIO,
            edge_margin_ratio=ENROLLMENT_EDGE_MARGIN_RATIO,
        )
        self.assertFalse(production_default["ready"])
        self.assertTrue(standalone["ready"], standalone)

        near_edge_face = {"bbox": [10, 120, 210, 360], "detection_score": 0.95}
        near_edge = assess_capture_quality(
            frame, near_edge_face,
            center_tolerance=ENROLLMENT_CENTER_TOLERANCE,
            max_size_ratio=ENROLLMENT_MAX_SIZE_RATIO,
            edge_margin_ratio=ENROLLMENT_EDGE_MARGIN_RATIO,
        )
        self.assertFalse(near_edge["ready"])
        very_edge_face = {"bbox": [5, 120, 205, 360], "detection_score": 0.95}
        very_edge = assess_capture_quality(
            frame, very_edge_face,
            center_tolerance=ENROLLMENT_CENTER_TOLERANCE,
            max_size_ratio=ENROLLMENT_MAX_SIZE_RATIO,
            edge_margin_ratio=ENROLLMENT_EDGE_MARGIN_RATIO,
        )
        self.assertFalse(very_edge["ready"])
        self.assertIn("mép khung", very_edge["instruction"])

    def test_standalone_enrollment_accepts_larger_uncropped_face(self):
        frame = wide_sharp_frame(104)
        face = {"bbox": [145, 40, 495, 440], "detection_score": 0.95}
        production_default = assess_capture_quality(frame, face)
        standalone = assess_capture_quality(
            frame, face,
            center_tolerance=ENROLLMENT_CENTER_TOLERANCE,
            max_size_ratio=ENROLLMENT_MAX_SIZE_RATIO,
            edge_margin_ratio=ENROLLMENT_EDGE_MARGIN_RATIO,
        )
        self.assertFalse(production_default["ready"])
        self.assertTrue(standalone["ready"], standalone)

    def test_preview_draws_live_detection_bbox(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        gui = AI1Gui.__new__(AI1Gui)
        gui.latest_analysis = {
            "bbox": [20, 20, 80, 80],
            "frame_shape": [100, 100],
            "observed_at": time.monotonic(),
            "detection_score": 0.93,
            "detected_pose": "left",
            "quality_status": "READY",
        }
        gui.active_operation = "recognition"
        gui.enrollment = None
        gui.progress_var = Value("Snapshot: 1/3")
        rendered = gui._draw_preview(frame, packet=None)
        self.assertTrue(np.any(rendered[20, 20] != frame[20, 20]))
        self.assertTrue(np.any(rendered != frame))

    def test_enrollment_preview_renders_full_diagnostic_hud(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        gui = AI1Gui.__new__(AI1Gui)
        gui.latest_analysis = {
            "bbox": [170, 100, 370, 370],
            "bboxes": [[170, 100, 370, 370]],
            "frame_shape": [480, 640],
            "observed_at": time.monotonic(),
            "detection_score": 0.94,
            "detection_scores": [0.94],
            "detected_pose": "left",
            "expected_pose": "frontal",
            "quality_status": "PASS",
            "code": "OK",
            "reason": "Quality PASS · Nhấn SPACE để chụp",
            "diagnostics": {
                "bbox": [170.0, 100.0, 370.0, 370.0],
                "bbox_width_frame_ratio": 200 / 640,
                "bbox_height_frame_ratio": 270 / 480,
                "center_offset_x_px": -50,
                "center_offset_y_px": -9.8,
                "center_offset_x_ratio": -50 / 640,
                "center_offset_y_ratio": -9.8 / 480,
                "detection_score": 0.94,
                "brightness": 128,
                "sharpness": 63,
                "yaw": 22.2,
                "pitch": 6.1,
                "face_count": 1,
                "quality_result": "PASS",
                "quality_code": "PASS",
            },
        }
        gui.active_operation = "enrollment"
        gui.enrollment = {}
        gui.progress_var = Value("Tiến độ: 0/5")
        rendered = gui._draw_preview(frame, packet=None)
        self.assertEqual(rendered.shape, frame.shape)
        self.assertTrue(np.any(rendered != frame))


if __name__ == "__main__":
    unittest.main()
