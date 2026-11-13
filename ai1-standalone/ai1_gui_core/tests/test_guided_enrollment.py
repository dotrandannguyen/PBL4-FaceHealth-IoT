"""Synthetic geometry and state tests for Smart Enrollment v2 pose guidance."""

import queue
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from unittest.mock import patch

import face_engine
from ai1_gui_core.enrollment_state import EnrollmentCaptureState
from ai1_gui_core.gui import AI1Gui, _draw_unicode_runs
from ai1_standalone_core.ai1_adapter import validate_enrollment_pose_frame
from ai1_standalone_core.config import GUIDED_POSE_STABILITY_WINDOW_SECONDS, POSES
from ai1_standalone_core.pose_tracking import (
    GuidedPoseTracker,
    assess_frontal_camera_alignment,
    angular_delta_degrees,
    average_rotation_matrices,
    classify_relative_pose,
    relative_pose_angles,
    rotation_distance_degrees,
    wrap_degrees,
)


def axis_rotation(axis, radians):
    vector = np.zeros(3, dtype=np.float64)
    vector[axis] = radians
    return cv2.Rodrigues(vector)[0]


FRONTAL_ROTATION = axis_rotation(0, np.pi)
POSE_ROTATIONS = {
    "frontal": FRONTAL_ROTATION,
    "left": FRONTAL_ROTATION @ axis_rotation(1, np.deg2rad(24.0)),
    "right": FRONTAL_ROTATION @ axis_rotation(1, np.deg2rad(-24.0)),
    "up": FRONTAL_ROTATION @ axis_rotation(0, np.deg2rad(-24.0)),
    "down": FRONTAL_ROTATION @ axis_rotation(0, np.deg2rad(24.0)),
}


def projected_head_pose(rotation):
    camera = np.asarray([[640.0, 0.0, 320.0], [0.0, 640.0, 240.0],
                         [0.0, 0.0, 1.0]], dtype=np.float64)
    translation = np.asarray([[0.0], [0.0], [600.0]], dtype=np.float64)
    rotation_vector, _ = cv2.Rodrigues(rotation)
    points, _ = cv2.projectPoints(
        face_engine._POSE_MODEL_POINTS, rotation_vector, translation,
        camera, np.zeros((4, 1), dtype=np.float64),
    )
    return face_engine.estimate_head_pose(points.reshape(-1, 2), (480, 640, 3))


def projected_points(rotation):
    camera = np.asarray([[640.0, 0.0, 320.0], [0.0, 640.0, 240.0],
                         [0.0, 0.0, 1.0]], dtype=np.float64)
    translation = np.asarray([[0.0], [0.0], [600.0]], dtype=np.float64)
    rotation_vector, _ = cv2.Rodrigues(rotation)
    points, _ = cv2.projectPoints(
        face_engine._POSE_MODEL_POINTS, rotation_vector, translation,
        camera, np.zeros((4, 1), dtype=np.float64),
    )
    return points.reshape(-1, 2)


def valid_outcome(rotation, sharpness=10.0, embedding=None):
    vector = np.zeros(512, dtype=np.float32)
    vector[0] = 1.0
    return {
        "status": "OK",
        "embedding": vector if embedding is None else embedding,
        "quality": {"ready": True, "sharpness": float(sharpness)},
        "face": {
            "bbox": [200.0, 100.0, 440.0, 380.0],
            "keypoints": [[270.0, 180.0], [370.0, 180.0], [320.0, 230.0],
                          [285.0, 290.0], [355.0, 290.0]],
            "detection_score": 0.99,
            "head_pose": {
                "rotation_matrix": np.asarray(rotation).tolist(),
                "reprojection_error_px": 1.0,
                "positive_depth": True,
                "yaw": 0.0, "pitch": 180.0,
            },
        },
        "faces": [],
        "face_count": 1,
        "diagnostics": {
            "quality_result": "PASS", "quality_code": "PASS", "face_count": 1,
            "detection_score": 0.99, "bbox": [200.0, 100.0, 440.0, 380.0],
            "brightness": 120.0, "sharpness": float(sharpness),
            "raw_yaw": 0.0, "raw_pitch": 180.0,
        },
    }


def pose_only_outcome(rotation, sharpness=10.0, face_count=1):
    """SCRFD/quality result intentionally contains no ArcFace embedding."""
    outcome = valid_outcome(rotation, sharpness=sharpness)
    outcome.pop("embedding", None)
    outcome["face_count"] = face_count
    if face_count != 1:
        outcome["status"] = "RETRY"
        outcome["code"] = "MULTIPLE FACES" if face_count > 1 else "NO FACE"
        outcome["reason"] = outcome["code"]
    return outcome


class _Var:
    def __init__(self):
        self.value = None

    def set(self, _value):
        self.value = _value

    def get(self):
        return self.value


class GuidedEnrollmentTests(unittest.TestCase):
    def test_raw_frontal_pitch_branch_is_near_180_but_relative_front_is_zero(self):
        raw = projected_head_pose(FRONTAL_ROTATION)
        self.assertGreater(abs(raw["pitch"]), 150.0)
        self.assertLess(raw["reprojection_error_px"], 1e-5)
        calibrated = relative_pose_angles(raw["rotation_matrix"], raw["rotation_matrix"])
        self.assertAlmostEqual(calibrated["yaw"], 0.0, places=6)
        self.assertAlmostEqual(calibrated["pitch"], 0.0, places=6)

    def test_face_engine_preserves_scrfd_keypoints_for_frontal_camera_check(self):
        embedding = np.zeros(512, dtype=np.float32)
        embedding[0] = 1.0
        fake_face = SimpleNamespace(
            det_score=0.99,
            bbox=np.asarray([200.0, 100.0, 440.0, 380.0]),
            normed_embedding=embedding,
            kps=projected_points(FRONTAL_ROTATION),
        )

        class FakeFaceAnalysis:
            def __init__(self):
                self.det_model = SimpleNamespace(det_thresh=0.5)

            def get(self, _frame):
                return [fake_face]

        engine = face_engine.FaceRecognitionEngine()
        engine._app = FakeFaceAnalysis()
        engine._initialized = True
        result = engine.detect_embeddings(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertEqual(np.asarray(result[0]["keypoints"]).shape, (5, 2))
        self.assertEqual(len(result[0]["head_pose"]["rotation_matrix"]), 3)

    def test_face_engine_pose_only_path_uses_scrfd_and_never_calls_faceanalysis_get(self):
        points = projected_points(FRONTAL_ROTATION)

        class Detector:
            det_thresh = 0.5

            def detect(self, _frame, max_num=0, metric="default", det_thresh=None):
                self.requested_threshold = det_thresh
                return (np.asarray([[200, 100, 440, 380, 0.84],
                                    [24, 30, 100, 110, 0.28]], dtype=np.float32),
                        np.stack([points, points]).astype(np.float32))

        detector = Detector()

        class FakeFaceAnalysis:
            det_model = detector

            @staticmethod
            def get(_frame):
                raise AssertionError("AUTO tracking must not invoke ArcFace recognition")

        engine = face_engine.FaceRecognitionEngine()
        engine._app = FakeFaceAnalysis()
        engine._initialized = True
        faces = engine.detect_pose_faces(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertEqual(len(faces), 2, "low-confidence secondary face must count")
        self.assertEqual(detector.requested_threshold, face_engine.ENROLLMENT_DETECTION_FLOOR)
        self.assertNotIn("embedding", faces[0])
        self.assertEqual(np.asarray(faces[0]["keypoints"]).shape, (5, 2))
        self.assertTrue(faces[0]["head_pose"]["positive_depth"])

    def test_face_engine_pose_only_restores_detector_threshold_on_legacy_scrfd_api(self):
        points = projected_points(FRONTAL_ROTATION)

        class LegacyDetector:
            det_thresh = 0.5

            def detect(self, _frame, max_num=0, metric="default"):
                self.threshold_during_detect = self.det_thresh
                return (np.asarray([[200, 100, 440, 380, 0.84]], dtype=np.float32),
                        np.asarray([points], dtype=np.float32))

        detector = LegacyDetector()
        engine = face_engine.FaceRecognitionEngine()
        engine._app = SimpleNamespace(det_model=detector)
        engine._initialized = True
        result = engine.detect_pose_faces(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertEqual(detector.threshold_during_detect,
                         face_engine.ENROLLMENT_DETECTION_FLOOR)
        self.assertEqual(detector.det_thresh, face_engine.DETECTION_MIN_SCORE)
        self.assertEqual(len(result), 1)

    def test_pose_only_adapter_preserves_quality_gates_and_has_no_embedding(self):
        face = valid_outcome(FRONTAL_ROTATION)["face"]

        class FakeEngine:
            @staticmethod
            def detect_pose_faces(_frame, detection_threshold):
                self_threshold[0] = detection_threshold
                return [face]

        self_threshold = [None]
        frame = np.full((480, 640, 3), 127, dtype=np.uint8)
        with patch("ai1_standalone_core.ai1_adapter.production_face_engine.assess_capture_quality",
                   return_value={"ready": True, "instruction": "OK", "sharpness": 42.0,
                                 "brightness": 127.0}):
            result = validate_enrollment_pose_frame(FakeEngine(), frame, "frontal")
        self.assertEqual(result["status"], "OK")
        self.assertIsNone(result["embedding"])
        self.assertEqual(result["face_count"], 1)
        self.assertEqual(self_threshold[0], face_engine.ENROLLMENT_DETECTION_FLOOR)

    def test_pose_only_adapter_rejects_no_face_and_multiple_faces(self):
        one_face = valid_outcome(FRONTAL_ROTATION)["face"]

        class FakeEngine:
            def __init__(self, detections):
                self.detections = detections

            def detect_pose_faces(self, _frame, detection_threshold):
                return self.detections

        frame = np.full((480, 640, 3), 127, dtype=np.uint8)
        self.assertEqual(validate_enrollment_pose_frame(
            FakeEngine([]), frame, "frontal")["code"], "NO FACE")
        multiple = validate_enrollment_pose_frame(
            FakeEngine([one_face, one_face]), frame, "frontal")
        self.assertEqual(multiple["code"], "MULTIPLE FACES")
        self.assertEqual(multiple["face_count"], 2)

    def test_synthetic_relative_rotations_classify_all_five_pose_directions(self):
        reference = POSE_ROTATIONS["frontal"]
        for target in POSES:
            angles = relative_pose_angles(reference, POSE_ROTATIONS[target])
            with self.subTest(target=target, angles=angles):
                self.assertEqual(
                    classify_relative_pose(angles["yaw"], angles["pitch"], angles["roll"]),
                    target,
                )

    def test_solvepnp_projected_landmarks_recover_all_relative_pose_directions(self):
        estimates = {pose: projected_head_pose(POSE_ROTATIONS[pose]) for pose in POSES}
        reference = estimates["frontal"]["rotation_matrix"]
        for pose in POSES:
            estimated = estimates[pose]
            angles = relative_pose_angles(reference, estimated["rotation_matrix"])
            with self.subTest(pose=pose, angles=angles):
                self.assertLess(estimated["reprojection_error_px"], 1e-5)
                self.assertEqual(
                    classify_relative_pose(angles["yaw"], angles["pitch"], angles["roll"]),
                    pose,
                )

    def test_relative_yaw_pitch_are_euler_decomposition_not_rodrigues_components(self):
        yaw, pitch, roll = np.deg2rad([27.0, 18.0, -9.0])
        relative = (axis_rotation(1, yaw) @ axis_rotation(0, -pitch)
                    @ axis_rotation(2, roll))
        angles = relative_pose_angles(np.eye(3), relative)
        self.assertAlmostEqual(angles["yaw"], 27.0, places=5)
        self.assertAlmostEqual(angles["pitch"], 18.0, places=5)
        self.assertAlmostEqual(angles["roll"], -9.0, places=5)
        with self.assertRaisesRegex(ValueError, "gimbal lock"):
            relative_pose_angles(np.eye(3), axis_rotation(0, -np.pi / 2))

    def test_frontal_calibration_ignores_raw_180_pitch_and_displays_no_fake_angles(self):
        tracker = GuidedPoseTracker(stable_frames=3)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        outputs = []
        for sequence in range(1, 4):
            outcome = valid_outcome(FRONTAL_ROTATION)
            outcome["face"]["head_pose"].update(yaw=16.22, pitch=171.42)
            timestamp = 50.0 + (sequence - 1) * 0.2
            outputs.append(tracker.observe(
                "frontal", outcome, frame, sequence, timestamp, now=timestamp
            ))
        self.assertEqual(outputs[0]["status"], "STABILIZING")
        self.assertIsNone(outputs[0]["yaw"])
        self.assertIsNone(outputs[0]["pitch"])
        self.assertEqual(outputs[-1]["status"], "CAPTURE_READY")
        self.assertAlmostEqual(outputs[-1]["yaw"], 0.0, places=4)
        self.assertAlmostEqual(outputs[-1]["pitch"], 0.0, places=4)

    def test_personalized_frontal_accepts_moderate_raw_yaw_and_ignores_pitch_branch(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        outcome = valid_outcome(FRONTAL_ROTATION)
        outcome["face"]["head_pose"].update(yaw=23.0, pitch=179.0)
        result = tracker.observe("frontal", outcome, np.zeros((480, 640, 3), dtype=np.uint8),
                                 1, 10.0, now=10.0)
        self.assertEqual(result["status"], "STABILIZING")
        self.assertEqual(result["stable_count"], 1)
        self.assertLessEqual(result["frontal_view"]["raw_yaw"], 35.0)

    def test_clear_side_view_cannot_be_used_as_personal_frontal_reference(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        side_rotation = FRONTAL_ROTATION @ axis_rotation(1, np.deg2rad(60.0))
        outcome = valid_outcome(side_rotation)
        outcome["face"]["keypoints"] = projected_points(side_rotation).tolist()
        # Even if raw yaw is biased back to zero, the visible landmark spread
        # rejects a clear profile rather than learning it as the user baseline.
        outcome["face"]["head_pose"].update(yaw=0.0, raw_yaw=0.0, pitch=180.0)
        result = tracker.observe(
            "frontal", outcome, np.zeros((480, 640, 3), dtype=np.uint8),
            1, 10.0, now=10.0,
        )
        self.assertEqual(result["status"], "POSE_NOT_READY")
        self.assertEqual(result["stable_count"], 0)
        self.assertIn("hướng về camera", result["reason"])
        self.assertIn("tâm mắt quá hẹp", result["reason"])

    def test_asymmetric_eye_centers_and_strabismus_metadata_do_not_block_frontal(self):
        outcome = valid_outcome(FRONTAL_ROTATION)
        outcome["face"]["keypoints"] = [
            [268.0, 184.0], [374.0, 193.0], [329.0, 239.0],
            [284.0, 294.0], [360.0, 288.0],
        ]
        outcome["face"]["eye_gaze"] = {"left": [-1.0, 0.0], "right": [1.0, 0.0]}
        outcome["face"]["head_pose"].update(yaw=27.0, raw_yaw=27.0, pitch=171.0)
        accepted, reason, metrics = assess_frontal_camera_alignment(
            outcome["face"], outcome["face"]["head_pose"]
        )
        self.assertTrue(accepted, reason)
        self.assertGreater(metrics["eye_line_tilt_deg"], 0.0)
        self.assertLess(metrics["eye_line_tilt_deg"], 30.0)
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = None
        for sequence in range(1, 6):
            timestamp = 15.0 + (sequence - 1) * 0.2
            result = tracker.observe(
                "frontal", outcome, frame, sequence, timestamp, now=timestamp,
            )
        self.assertEqual(result["status"], "CAPTURE_READY")
        self.assertEqual(result["stable_count"], 5)

    def test_mild_natural_head_tilt_calibrates_then_relative_left_pose_is_detected(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tilted_frontal = FRONTAL_ROTATION @ axis_rotation(2, np.deg2rad(12.0))
        result = None
        for sequence in range(1, 6):
            outcome = valid_outcome(tilted_frontal, sharpness=sequence)
            points = projected_points(tilted_frontal)
            outcome["face"]["keypoints"] = points.tolist()
            pose = projected_head_pose(tilted_frontal)
            outcome["face"]["head_pose"].update(
                yaw=pose["yaw"], raw_yaw=pose["raw_yaw"],
                pitch=pose["pitch"], raw_pitch=pose["raw_pitch"],
            )
            timestamp = 10.0 + (sequence - 1) * 0.2
            result = tracker.observe("frontal", outcome, frame, sequence, timestamp, now=timestamp)
        self.assertEqual(result["status"], "CAPTURE_READY")
        self.assertLess(result["frontal_view"]["eye_line_tilt_deg"], 30.0)
        tracker.capture_result(True, "left", now=11.0)

        left_rotation = tilted_frontal @ axis_rotation(1, np.deg2rad(24.0))
        result = None
        for sequence in range(6, 11):
            timestamp = 11.2 + (sequence - 6) * 0.2
            result = tracker.observe(
                "left", valid_outcome(left_rotation, sharpness=sequence), frame,
                sequence, timestamp, now=timestamp,
            )
        self.assertEqual(result["status"], "CAPTURE_READY")
        self.assertEqual(result["detected_pose"], "left")

    def test_five_frames_at_1_33_fps_fit_inside_twelve_second_window(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = None
        for sequence in range(1, 6):
            timestamp = (sequence - 1) * 0.75
            result = tracker.observe(
                "frontal", valid_outcome(FRONTAL_ROTATION, sharpness=sequence),
                frame, sequence, timestamp, now=timestamp,
            )
        self.assertEqual(result["status"], "CAPTURE_READY")
        self.assertEqual(result["stable_count"], 5)
        self.assertAlmostEqual(result["candidate"]["captured_at"], 3.0, places=6)
        self.assertGreaterEqual(result["inference_fps"], 1.33)
        self.assertEqual(tracker.max_stability_deg, 8.0)
        self.assertEqual(tracker.max_step_deg, 18.0)

    def test_missing_frontal_landmarks_is_explicit_and_never_calibrates(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        outcome = valid_outcome(FRONTAL_ROTATION)
        outcome["face"].pop("keypoints")
        result = tracker.observe("frontal", outcome, np.zeros((480, 640, 3), dtype=np.uint8),
                                 1, 10.0, now=10.0)
        self.assertEqual(result["status"], "POSE_NOT_READY")
        self.assertEqual(result["stable_count"], 0)
        self.assertIn("landmark", result["reason"].lower())

    def test_timeout_pauses_auto_with_reason_and_reset_restarts_tracker(self):
        tracker = GuidedPoseTracker(stable_frames=2, pose_timeout_seconds=2.0)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        first = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION),
                                frame, 1, 10.0, now=10.0)
        self.assertEqual(first["status"], "STABILIZING")
        timed_out = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION),
                                    frame, 2, 12.1, now=12.1)
        self.assertEqual(timed_out["status"], "AUTO_PAUSED")
        self.assertIn("chưa đạt quality/hướng", timed_out["reason"])
        tracker.reset()
        restarted = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION),
                                    frame, 3, 13.0, now=13.0)
        self.assertEqual(restarted["status"], "STABILIZING")
        self.assertEqual(restarted["stable_count"], 1)

    def test_angle_wrap_and_rotation_geodesic_are_continuous_at_boundary(self):
        self.assertEqual(wrap_degrees(181.0), -179.0)
        self.assertAlmostEqual(angular_delta_degrees(179.0, -179.0), 2.0)
        first = axis_rotation(1, np.deg2rad(179.0))
        second = axis_rotation(1, np.deg2rad(-179.0))
        self.assertAlmostEqual(rotation_distance_degrees(first, second), 2.0, places=4)

    def test_rotation_average_returns_a_valid_rotation(self):
        average = average_rotation_matrices([
            axis_rotation(1, np.deg2rad(2.0)),
            axis_rotation(1, np.deg2rad(3.0)),
            axis_rotation(1, np.deg2rad(4.0)),
        ])
        self.assertAlmostEqual(np.linalg.det(average), 1.0, places=6)
        self.assertLess(np.linalg.norm(average.T @ average - np.eye(3)), 1e-6)

    def test_tracker_uses_five_fresh_frames_within_three_seconds_and_selects_sharpest(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        now = 100.0
        results = []
        for sequence in range(1, 6):
            captured_at = now + (sequence - 1) * 0.5  # 2 inference FPS, natural pauses.
            results.append(tracker.observe(
                "frontal", valid_outcome(FRONTAL_ROTATION, sharpness=sequence),
                frame, sequence, captured_at, now=captured_at,
            ))
        self.assertEqual([item["status"] for item in results[:-1]], ["STABILIZING"] * 4)
        self.assertEqual(results[-1]["status"], "CAPTURE_READY")
        self.assertEqual(results[-1]["candidate"]["sequence"], 5)
        self.assertLessEqual(results[-1]["candidate"]["captured_at"] - 100.0, 3.0)
        duplicate = tracker.observe(
            "frontal", valid_outcome(FRONTAL_ROTATION, sharpness=20),
            frame, 5, 102.1, now=102.1,
        )
        self.assertEqual(duplicate["status"], "STALE_FRAME")
        self.assertEqual(duplicate["stable_count"], 5)
        tracker.capture_result(True, "left", now=102.1)
        self.assertEqual(tracker.stable_count, 0)
        self.assertEqual(tracker.expected_pose, "left")

    def test_pose_timeout_restarts_for_each_pose_across_session_longer_than_25_seconds(self):
        tracker = GuidedPoseTracker(stable_frames=8)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        sequence = 0
        completed_at = None

        for pose, start_time in (("frontal", 0.0), ("left", 12.0), ("right", 26.0)):
            results = []
            for index in range(8):
                sequence += 1
                timestamp = start_time + index * 0.1
                results.append(tracker.observe(
                    pose, valid_outcome(POSE_ROTATIONS[pose], sharpness=index + 1),
                    frame, sequence, timestamp, now=timestamp,
                ))
            self.assertEqual(results[-1]["status"], "CAPTURE_READY", (pose, results[-1]))
            capture_time = results[-1]["candidate"]["captured_at"]
            if completed_at is None:
                session_start = start_time
            self.assertLess(capture_time - tracker.pose_started_at, 25.0)
            next_pose = {"frontal": "left", "left": "right", "right": "up"}[pose]
            tracker.capture_result(True, next_pose, now=capture_time)
            completed_at = capture_time

        self.assertGreater(completed_at - session_start, 25.0)
        self.assertFalse(tracker.manual_fallback)
        self.assertEqual(tracker.expected_pose, "up")

    def test_low_fps_is_measured_and_reported_without_false_capture(self):
        tracker = GuidedPoseTracker(pose_timeout_seconds=20.0)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = []
        for sequence in range(1, 16):
            timestamp = (sequence - 1) * 4.0  # 0.25 FPS cannot fit 5 frames in 12s.
            result = tracker.observe(
                "frontal", pose_only_outcome(FRONTAL_ROTATION, sharpness=sequence),
                frame, sequence, timestamp, now=timestamp,
            )
            results.append(result)
            if result["status"] in {"AUTO_PAUSED", "CAPTURE_READY"}:
                break

        self.assertFalse(any(item["status"] == "CAPTURE_READY" for item in results))
        self.assertTrue(any(item["status"] == "LOW_FPS" for item in results))
        self.assertEqual(results[-1]["status"], "AUTO_PAUSED")
        self.assertIn("FPS inference thấp", results[-1]["reason"])
        self.assertAlmostEqual(results[-1]["inference_fps"], 0.25, places=2)
        self.assertEqual(tracker.stable_frames, 5)
        self.assertEqual(tracker.stability_window_seconds, 12.0)

    def test_rate_below_five_in_custom_three_second_window_reports_required_fps(self):
        tracker = GuidedPoseTracker(pose_timeout_seconds=20.0,
                                    stability_window_seconds=3.0,
                                    max_interframe_gap_seconds=3.0)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        statuses = []
        for sequence in range(1, 6):
            timestamp = (sequence - 1) / 1.2
            result = tracker.observe(
                "frontal", valid_outcome(FRONTAL_ROTATION), frame,
                sequence, timestamp, now=timestamp,
            )
            statuses.append(result["status"])
        self.assertIn("LOW_FPS", statuses)
        self.assertNotIn("CAPTURE_READY", statuses)
        self.assertAlmostEqual(tracker.inference_fps, 1.2, places=1)
        reason = tracker._low_fps_reason(now=4.0)
        self.assertIn("cần tối thiểu 1.3 FPS", reason)

    def test_pose_only_tracking_finishes_at_cpu_fps_from_half_to_over_five(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for fps in (0.5, 0.6, 0.8, 1.0, 1.5, 2.5, 6.0):
            with self.subTest(fps=fps):
                tracker = GuidedPoseTracker()
                final = None
                for sequence in range(1, 6):
                    timestamp = (sequence - 1) / fps
                    final = tracker.observe(
                        "frontal", pose_only_outcome(FRONTAL_ROTATION, sequence),
                        frame, sequence, timestamp, now=timestamp,
                    )
                self.assertEqual(final["status"], "CAPTURE_READY", final)
                self.assertEqual(final["valid_frames"], 5)
                self.assertEqual(final["candidate"]["sequence"], 5)
                self.assertIsNone(final["candidate"]["embedding"])
                self.assertLessEqual(
                    final["candidate"]["captured_at"],
                    GUIDED_POSE_STABILITY_WINDOW_SECONDS,
                )
                self.assertAlmostEqual(final["inference_fps"], fps, places=3)
                self.assertGreater(final["time_remaining_seconds"], 0)

    def test_pose_only_five_pose_run_extracts_and_keeps_exactly_five_embeddings(self):
        tracker = GuidedPoseTracker()
        state = EnrollmentCaptureState(same_person_threshold=0.45)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        vector = np.eye(1, 512, 0, dtype=np.float32).reshape(-1)
        sequence = 0
        now = 0.0
        selected_sequences = []
        for pose in POSES:
            result = None
            for index in range(5):
                sequence += 1
                now += 0.4
                result = tracker.observe(
                    pose, pose_only_outcome(POSE_ROTATIONS[pose], 20 + index),
                    frame, sequence, now, now=now,
                )
            self.assertEqual(result["status"], "CAPTURE_READY", (pose, result))
            candidate = result["candidate"]
            selected_sequences.append(candidate["sequence"])
            selected = valid_outcome(POSE_ROTATIONS[pose], 20 + sequence, embedding=vector)
            verification = tracker.validate_selected_candidate(candidate, selected, pose)
            self.assertEqual(verification["status"], "OK", verification)
            selected = {**selected, "embedding": verification["embedding"]}
            state.capture(selected)
            tracker.capture_result(True, state.current_pose, now=now,
                                   embedding=state.embeddings[pose])
        self.assertTrue(state.complete)
        self.assertTrue(state.validate_complete()["valid"])
        self.assertEqual(len(state.embeddings), 5)
        self.assertEqual(len(set(selected_sequences)), 5)

    def test_selected_embedding_recheck_rejects_wrong_pose_and_other_person(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = None
        for sequence in range(1, 3):
            timestamp = sequence * 0.2
            result = tracker.observe(
                "frontal", pose_only_outcome(FRONTAL_ROTATION), frame,
                sequence, timestamp, now=timestamp,
            )
        candidate = result["candidate"]
        wrong = valid_outcome(POSE_ROTATIONS["left"])
        rejected = tracker.validate_selected_candidate(candidate, wrong, "frontal")
        self.assertEqual(rejected["code"], "POSE CHANGED")
        correct = valid_outcome(FRONTAL_ROTATION)
        checked = tracker.validate_selected_candidate(candidate, correct, "frontal")
        self.assertEqual(checked["status"], "OK")
        tracker.capture_result(True, "left", now=1.0, embedding=checked["embedding"])
        other = np.eye(1, 512, 1, dtype=np.float32).reshape(-1)
        right_result = None
        for sequence in range(3, 5):
            timestamp = sequence * 0.2
            right_result = tracker.observe(
                "left", pose_only_outcome(POSE_ROTATIONS["left"]), frame,
                sequence, timestamp, now=timestamp,
            )
        self.assertEqual(right_result["status"], "CAPTURE_READY")
        impostor = valid_outcome(POSE_ROTATIONS["left"], embedding=other)
        rejected = tracker.validate_selected_candidate(
            right_result["candidate"], impostor, "left"
        )
        self.assertEqual(rejected["code"], "SAME PERSON")

    def test_small_pose_jitter_within_eight_degrees_captures_five_frames(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = []
        for sequence, offset in enumerate((-3.5, -1.75, 0.0, 1.75, 3.5), start=1):
            rotation = FRONTAL_ROTATION @ axis_rotation(1, np.deg2rad(offset))
            results.append(tracker.observe(
                "frontal", valid_outcome(rotation, sharpness=sequence), frame,
                sequence, 20.0 + (sequence - 1) * 0.5,
                now=20.0 + (sequence - 1) * 0.5,
            ))
        self.assertEqual(results[-1]["status"], "CAPTURE_READY")
        spread = max(rotation_distance_degrees(a["rotation"], b["rotation"])
                     for i, a in enumerate(tracker.window)
                     for b in tracker.window[i + 1:])
        self.assertLessEqual(spread, 8.0)

    def test_jitter_over_eight_degrees_trims_old_cluster_without_full_reset(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = None
        for sequence, offset in enumerate((-4.5, -2.0, 0.0, 2.0, 4.5), start=1):
            rotation = FRONTAL_ROTATION @ axis_rotation(1, np.deg2rad(offset))
            result = tracker.observe(
                "frontal", valid_outcome(rotation, sharpness=sequence), frame,
                sequence, 30.0 + (sequence - 1) * 0.4,
                now=30.0 + (sequence - 1) * 0.4,
            )
        self.assertEqual(result["status"], "STABILIZING")
        self.assertGreater(result["stable_count"], 1)
        self.assertIn("bỏ frame", result["reason"])

    def test_single_angular_step_over_eighteen_degrees_reseeds_candidate_window(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                        1, 35.0, now=35.0)
        moved = FRONTAL_ROTATION @ axis_rotation(1, np.deg2rad(19.0))
        result = tracker.observe("frontal", valid_outcome(moved), frame,
                                 2, 35.2, now=35.2)
        self.assertEqual(result["status"], "STABILIZING")
        self.assertEqual(result["stable_count"], 1)
        self.assertIn("18.0°", result["reason"])

    def test_short_blur_and_stale_gaps_do_not_count_or_clear_good_candidates(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        first = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                                1, 40.0, now=40.0)
        self.assertEqual(first["stable_count"], 1)
        blur = tracker.observe("frontal", {"status": "RETRY", "code": "TOO BLURRY",
                                            "reason": "Ảnh bị mờ"}, frame,
                              2, 40.25, now=40.25)
        self.assertEqual(blur["status"], "QUALITY_REJECTED")
        self.assertEqual(blur["stable_count"], 1)
        stale = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                                3, 39.0, now=40.5)
        self.assertEqual(stale["status"], "STALE_FRAME")
        self.assertEqual(stale["stable_count"], 1)
        result = None
        for sequence, timestamp in ((4, 40.75), (5, 41.25), (6, 41.75), (7, 42.25)):
            result = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                                     sequence, timestamp, now=timestamp)
        self.assertEqual(result["status"], "CAPTURE_READY")

    def test_duplicate_sequence_is_ignored_and_does_not_advance_stability(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        first = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                                1, 50.0, now=50.0)
        duplicate = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                                    1, 50.1, now=50.1)
        self.assertEqual(first["stable_count"], 1)
        self.assertEqual(duplicate["status"], "STALE_FRAME")
        self.assertEqual(duplicate["stable_count"], 1)

    def test_nonincreasing_capture_timestamp_is_rejected_as_duplicate(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                        1, 55.0, now=55.0)
        duplicate = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                                    2, 55.0, now=55.2)
        self.assertEqual(duplicate["status"], "STALE_FRAME")
        self.assertIn("frame trùng", duplicate["reason"])
        self.assertEqual(duplicate["stable_count"], 1)

    def test_multiple_faces_clear_window_and_never_count_as_sample(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                        1, 60.0, now=60.0)
        multiple = valid_outcome(FRONTAL_ROTATION)
        multiple["face_count"] = None
        multiple["faces"] = [{"bbox": [20, 20, 80, 90]}, {"bbox": [100, 20, 160, 90]}]
        result = tracker.observe("frontal", multiple, frame, 2, 60.2, now=60.2)
        self.assertEqual(result["status"], "QUALITY_REJECTED")
        self.assertEqual(result["rejected_code"], "MULTIPLE FACES")
        self.assertEqual(result["stable_count"], 0)

    def test_wrong_pose_is_reported_and_correct_next_pose_is_captured(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = None
        for sequence in range(1, 6):
            timestamp = 70.0 + (sequence - 1) * 0.2
            result = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                                     sequence, timestamp, now=timestamp)
        self.assertEqual(result["status"], "CAPTURE_READY")
        tracker.capture_result(True, "left", now=70.9)
        wrong = tracker.observe("left", valid_outcome(POSE_ROTATIONS["right"]), frame,
                                6, 71.0, now=71.0)
        self.assertEqual(wrong["status"], "WRONG_POSE")
        self.assertEqual(wrong["detected_pose"], "right")
        self.assertIn("Sai hướng", wrong["reason"])
        result = None
        for sequence in range(7, 12):
            timestamp = 71.2 + (sequence - 7) * 0.2
            result = tracker.observe("left", valid_outcome(POSE_ROTATIONS["left"]), frame,
                                     sequence, timestamp, now=timestamp)
        self.assertEqual(result["status"], "CAPTURE_READY")

    def test_different_person_embedding_is_rejected_after_frontal_reference(self):
        tracker = GuidedPoseTracker()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = None
        for sequence in range(1, 6):
            timestamp = 80.0 + (sequence - 1) * 0.2
            result = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION), frame,
                                     sequence, timestamp, now=timestamp)
        tracker.capture_result(True, "left", now=80.9)
        other = np.zeros(512, dtype=np.float32)
        other[1] = 1.0
        result = tracker.observe("left", valid_outcome(POSE_ROTATIONS["left"],
                                                        embedding=other), frame,
                                 6, 81.0, now=81.0)
        self.assertEqual(result["status"], "IDENTITY_MISMATCH")
        self.assertEqual(result["stable_count"], 0)

    def test_gui_shows_wrong_direction_and_low_fps_reasons(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.enrollment = {"mode": "AUTO", "state": EnrollmentCaptureState(),
                          "fallback_reason": None}
        gui.pose_var = _Var()
        gui.detected_pose_var = _Var()
        gui.enrollment_mode_var = _Var()
        gui.quality_var = _Var()
        gui.auto_status_var = _Var()
        gui.capture_hint_var = _Var()
        gui.capture_feedback = None
        gui.state_var = _Var()
        gui.preview_hint = _Var()
        gui.sharpness_var = _Var()
        gui.progress_var = _Var()
        gui.enrollment_progress_var = _Var()
        gui.latest_analysis = {}
        gui._update_pose_ring = lambda *_args: None
        common = {
            "mode": "AUTO", "current_pose": "left", "captured": 0,
            "detected_pose": "right", "expected_pose": "left", "code": "OK",
            "quality_status": "PASS", "stable_count": 2,
            "diagnostics": {"quality_result": "PASS", "quality_code": "PASS"},
        }
        gui._show_enrollment_progress({
            **common, "auto_status": "WRONG_POSE",
            "reason": "Sai hướng: yêu cầu left, hiện phát hiện right.",
        })
        self.assertIn("Sai hướng", gui.capture_hint_var.get())
        self.assertIn("SAI HƯỚNG", gui.state_var.get())
        gui._show_enrollment_progress({
            **common, "auto_status": "LOW_FPS", "inference_fps": 0.8,
            "reason": "FPS inference thấp: 0.8 FPS; cần tối thiểu 1.1 FPS.",
        })
        self.assertIn("FPS inference thấp", gui.capture_hint_var.get())
        self.assertIn("0.8 FPS", gui.auto_status_var.get())

    def test_auto_timeout_requires_an_explicit_manual_mode_selection(self):
        class _Widget:
            def configure(self, **values):
                self.values = values

        gui = AI1Gui.__new__(AI1Gui)
        gui.active_operation = "enrollment"
        gui.enrollment = {"mode": "AUTO", "auto_paused": True,
                          "fallback_reason": "per-pose timeout", "requests": queue.Queue()}
        gui.enrollment_mode_var = _Var()
        gui.enrollment_mode_var.value = "AUTO"
        gui.register_button = _Widget()
        gui.retake_button = _Widget()
        gui._sync_enrollment_start_button()
        self.assertEqual(gui.enrollment["mode"], "AUTO")
        self.assertTrue(gui.enrollment["requests"].empty())

        gui.enrollment_mode_var.value = "MANUAL"
        gui._sync_enrollment_start_button()
        self.assertEqual(gui.enrollment["mode"], "MANUAL")
        self.assertEqual(gui.enrollment["requests"].get_nowait(), {"action": "select_manual"})

    def test_full_five_pose_auto_run_keeps_one_512d_embedding_per_pose(self):
        tracker = GuidedPoseTracker(stable_frames=3)
        enrollment = EnrollmentCaptureState(same_person_threshold=0.45)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        sequence = 0
        now = 90.0
        for expected in POSES:
            for index in range(3):
                sequence += 1
                timestamp = now + index * 0.2
                result = tracker.observe(
                    expected, valid_outcome(POSE_ROTATIONS[expected], sharpness=20 + index),
                    frame, sequence, timestamp, now=timestamp,
                )
            self.assertEqual(result["status"], "CAPTURE_READY")
            enrollment.capture(result["candidate"]["outcome"])
            tracker.capture_result(True, enrollment.current_pose, now=timestamp)
            now = timestamp + 0.2
        self.assertEqual(set(enrollment.embeddings), set(POSES))
        self.assertEqual(len(enrollment.embeddings), 5)
        for vector in enrollment.embeddings.values():
            self.assertEqual(vector.shape, (512,))
            self.assertTrue(np.all(np.isfinite(vector)))
            self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)

    def test_bad_quality_stale_and_unreliable_pose_do_not_auto_capture(self):
        tracker = GuidedPoseTracker(stable_frames=2, unreliable_frame_limit=3)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        now = 100.0
        bad_quality = tracker.observe(
            "frontal", {"status": "RETRY", "reason": "TOO BLURRY"},
            frame, 1, now, now=now,
        )
        self.assertEqual(bad_quality["status"], "QUALITY_REJECTED")
        stale = tracker.observe(
            "frontal", valid_outcome(FRONTAL_ROTATION), frame, 2,
            now - 2.0, now=now,
        )
        self.assertEqual(stale["status"], "STALE_FRAME")
        missing_pose = {"status": "OK", "face": {"head_pose": None},
                        "embedding": np.eye(1, 512, 0, dtype=np.float32).reshape(-1),
                        "face_count": 1, "quality": {"sharpness": 40.0}}
        self.assertEqual(tracker.observe("frontal", missing_pose, frame, 3, now,
                                         now=now)["status"], "POSE_UNRELIABLE")
        self.assertEqual(tracker.observe("frontal", missing_pose, frame, 4, now,
                                         now=now)["status"], "POSE_UNRELIABLE")
        fallback = tracker.observe("frontal", missing_pose, frame, 5, now, now=now)
        self.assertEqual(fallback["status"], "AUTO_PAUSED")

    def test_complete_auto_sequence_captures_exactly_five_compatible_samples(self):
        tracker = GuidedPoseTracker(stable_frames=3)
        enrollment = EnrollmentCaptureState(same_person_threshold=0.45)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        sequence = 0
        now = 200.0
        for expected in POSES:
            rotation = POSE_ROTATIONS[expected]
            for index in range(3):
                sequence += 1
                captured_at = now + index * 0.1
                result = tracker.observe(
                    expected, valid_outcome(rotation, sharpness=10 + index),
                    frame, sequence, captured_at, now=captured_at,
                )
            self.assertEqual(result["status"], "CAPTURE_READY", (expected, result))
            capture = enrollment.capture(result["candidate"]["outcome"])
            tracker.capture_result(True, enrollment.current_pose, now=captured_at)
            self.assertEqual(capture["pose"], expected)
            now = captured_at + 0.1
        self.assertTrue(enrollment.complete)
        self.assertTrue(enrollment.validate_complete()["valid"])
        self.assertEqual(set(enrollment.embeddings), set(POSES))

    def test_space_is_ignored_in_auto_and_queues_one_manual_capture_after_fallback(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.active_operation = "enrollment"
        gui.enrollment = {"mode": "AUTO", "ready_to_save": False,
                          "requests": queue.Queue()}
        gui.space_is_down = False
        gui.space_capture_pending = False
        gui.capture_feedback = None
        gui.state_var = _Var()

        self.assertEqual(gui._on_space_press(), "break")
        self.assertTrue(gui.space_is_down)
        self.assertTrue(gui.enrollment["requests"].empty())
        gui._on_space_release()
        gui.enrollment["mode"] = "MANUAL"
        self.assertEqual(gui._on_space_press(), "break")
        self.assertEqual(gui.enrollment["requests"].get_nowait(), {"action": "capture"})
        self.assertEqual(gui._on_space_press(), "break")
        self.assertTrue(gui.enrollment["requests"].empty())

    def test_manual_fallback_reason_stays_visible_on_later_manual_progress(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.enrollment = {
            "mode": "MANUAL", "fallback_reason": "reprojection=24.2px, positive_depth=True",
            "state": EnrollmentCaptureState(),
        }
        gui.pose_var = _Var()
        gui.detected_pose_var = _Var()
        gui.enrollment_mode_var = _Var()
        gui.quality_var = _Var()
        gui.auto_status_var = _Var()
        gui.capture_hint_var = _Var()
        gui.capture_feedback = None
        gui.state_var = _Var()
        gui.preview_hint = _Var()
        gui.sharpness_var = _Var()
        gui.progress_var = _Var()
        gui.enrollment_progress_var = _Var()
        gui.latest_analysis = {}
        gui._update_pose_ring = lambda *_args: None
        gui._show_enrollment_progress({
            "mode": "MANUAL", "current_pose": "frontal", "captured": 0,
            "detected_pose": "between", "expected_pose": "frontal",
            "code": "OK", "reason": "Quality checks passed.",
            "quality_status": "PASS", "diagnostics": {"quality_result": "PASS"},
        })
        self.assertIn("reprojection=24.2px", gui.auto_status_var.get())

    def test_camera_preview_unicode_overlay_renders_vietnamese_with_true_type_font(self):
        frame = np.zeros((80, 320, 3), dtype=np.uint8)
        rendered = _draw_unicode_runs(
            frame, [("Nhìn thẳng · xoay trái · ngẩng lên", 8, 8, (245, 245, 245), 15)]
        )
        self.assertEqual(rendered.shape, frame.shape)
        self.assertTrue(np.any(rendered != frame))

    def test_auto_preview_scan_ring_tracks_live_face_bbox(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        gui = AI1Gui.__new__(AI1Gui)
        gui.latest_analysis = {
            "bbox": [100.0, 100.0, 300.0, 400.0],
            "bboxes": [[100.0, 100.0, 300.0, 400.0]],
            "frame_shape": [480, 640], "observed_at": time.monotonic(),
            "detection_scores": [0.98], "detection_score": 0.98,
            "quality_status": "PASS", "code": "OK", "expected_pose": "left",
            "detected_pose": "left", "auto_status": "STABILIZING",
            "stable_count": 4, "mode": "AUTO", "captured": 1,
            "diagnostics": {"face_count": 1, "bbox": [100, 100, 300, 400],
                            "quality_result": "PASS", "quality_code": "PASS"},
        }
        gui.active_operation = "enrollment"
        gui.enrollment = {"mode": "AUTO"}
        gui.progress_var = _Var()
        gui.progress_var.value = "Tiến độ: 1/5"
        gui.captured_pose_order = ["frontal"]
        original_ellipse = cv2.ellipse
        with patch("ai1_gui_core.gui.cv2.ellipse", wraps=original_ellipse) as ellipse:
            rendered = gui._draw_preview(frame, packet=None)
        centers = [call.args[1] for call in ellipse.call_args_list]
        self.assertIn((200, 250), centers)
        self.assertEqual(rendered.shape, frame.shape)
        self.assertTrue(np.any(rendered != frame))

    def test_auto_gui_worker_captures_five_poses_without_space_requests(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        class FakeController:
            engine = object()

            def __init__(self):
                self.sequence = 0
                self.last_capture_at = 0.0

            def get_packet(self):
                self.sequence += 1
                self.last_capture_at = max(time.monotonic(), self.last_capture_at + 1e-6)
                return SimpleNamespace(sequence=self.sequence,
                                       captured_at=self.last_capture_at, frame=frame)

            @staticmethod
            def find_duplicate_employee(*_args, **_kwargs):
                return None

        gui = AI1Gui.__new__(AI1Gui)
        gui.events = queue.Queue()
        gui.controller = FakeController()
        gui.enrollment = None
        vector = np.zeros(512, dtype=np.float32)
        vector[0] = 1.0
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temp:
            stage = Path(temp) / "stage"
            stage.mkdir()
            state = EnrollmentCaptureState(same_person_threshold=0.45)
            session = {
                "identity": "TEST_1", "name": "Test", "overwrite": False,
                "stage": stage, "frames": {}, "state": state,
                "requests": queue.Queue(), "ready_to_save": False, "saved": False,
                "session_id": "test", "captured_order_ui": [], "mode": "AUTO",
                "capture_pending": False,
            }
            session["requests"].put({"action": "reset_all", "mode": "AUTO"})
            gui.enrollment = session

            def fake_validate(_engine, _frame, pose, **_kwargs):
                return valid_outcome(POSE_ROTATIONS[pose], sharpness=20 + POSES.index(pose),
                                     embedding=vector)

            def fake_pose_validate(_engine, _frame, pose):
                return pose_only_outcome(POSE_ROTATIONS[pose],
                                         sharpness=20 + POSES.index(pose))

            with patch("ai1_gui_core.gui.validate_enrollment_frame", side_effect=fake_validate), \
                    patch("ai1_gui_core.gui.validate_enrollment_pose_frame",
                          side_effect=fake_pose_validate), \
                    patch("ai1_gui_core.gui._atomic_write_jpeg"):
                result = gui._enrollment_worker("test", __import__("threading").Event())

        self.assertEqual(result["status"], "READY_TO_SAVE")
        self.assertTrue(result["state"].complete)
        self.assertEqual(set(result["state"].embeddings), set(POSES))
        self.assertEqual(gui.controller.sequence, len(POSES) * 5)
        captured_events = []
        reset_events = 0
        progress_counts = []
        captured_so_far = 0
        while not gui.events.empty():
            item = gui.events.get_nowait()
            if item[0] == "enrollment_captured":
                captured_events.append(item[2]["pose"])
                captured_so_far += 1
            elif item[0] == "enrollment_reset":
                reset_events += 1
            elif item[0] == "enrollment_progress":
                count = item[2]["captured"]
                progress_counts.append(count)
                self.assertEqual(count, captured_so_far)
        self.assertEqual(captured_events, list(POSES))
        self.assertEqual(reset_events, 1)
        self.assertEqual(progress_counts[-1], 4)


if __name__ == "__main__":
    unittest.main()
