import unittest
from unittest.mock import patch

import numpy as np

import face_engine
import face_evaluation
import face_matching
import services
import app as flask_app


class MatchingTests(unittest.TestCase):
    def test_normalization_and_cosine(self):
        first = np.zeros(512, dtype=np.float32)
        first[0] = 4
        second = np.zeros(512, dtype=np.float32)
        second[0] = 2
        self.assertAlmostEqual(float(np.linalg.norm(face_matching.normalize_embedding(first))), 1.0)
        self.assertAlmostEqual(face_matching.cosine_similarity(first, second), 1.0)

    def test_gallery_identify_verify_unknown(self):
        a = np.zeros(512, dtype="<f4"); a[0] = 1
        b = np.zeros(512, dtype="<f4"); b[1] = 1
        rows = [(1, 10, a.tobytes(), 512, "An"), (2, 20, b.tobytes(), 512, "Binh")]
        gallery, invalid = face_matching.aggregate_gallery(rows)
        self.assertFalse(invalid)
        self.assertEqual(face_matching.identify_embedding(a, gallery, 0.45)["MaNV"], 10)
        self.assertEqual(face_matching.verify_embedding(a, 10, gallery, 0.45)["status"], "MATCH")
        orthogonal = np.zeros(512, dtype=np.float32); orthogonal[2] = 1
        self.assertEqual(face_matching.identify_embedding(orthogonal, gallery, 0.45)["status"], "UNKNOWN")

    def test_no_face_and_largest_face_recognition(self):
        class Engine:
            def __init__(self, faces): self.faces = faces
            def initialize(self): pass
            def detect_embeddings(self, frame): return self.faces
        with patch.object(face_engine, "face_engine", Engine([])):
            self.assertEqual(services.identify_face_frame(np.zeros((1, 1, 3)))["status"], "NO_FACE")
        small = np.zeros(512, dtype=np.float32); small[0] = 1
        large = np.zeros(512, dtype=np.float32); large[1] = 1
        faces = [
            {"embedding": small, "bbox": [0, 0, 10, 10]},
            {"embedding": large, "bbox": [0, 0, 20, 20]},
        ]
        with patch.object(face_engine, "face_engine", Engine(faces)), \
             patch.object(services, "identify_face_embedding", side_effect=lambda vector, threshold=None: {"selected": vector[1]}):
            result = services.identify_face_frame(np.zeros((1, 1, 3)))
            self.assertEqual(result["selected"], 1)
        with self.assertRaises(ValueError): face_matching.normalize_embedding(np.zeros(512))

    def test_evaluation_metrics(self):
        result = face_evaluation.evaluate_scores([0.9, 0.95], [0.1, 0.2])
        self.assertEqual(result["far"], 0.0)
        self.assertEqual(result["frr"], 0.0)
        self.assertEqual(result["eer"], 0.0)
        self.assertEqual(result["genuine_count"], 2)


class FaceApiTests(unittest.TestCase):
    def setUp(self):
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()
        with self.client.session_transaction() as session:
            session["MaNV"] = 1
            session["MaVaiTro"] = 1
        flask_app._enrollment_sessions.clear()

    def test_enrollment_requires_five_captures_and_saves_once(self):
        vector = np.zeros(512, dtype=np.float32); vector[0] = 1
        with patch.object(services, "fetch_employee", return_value={"MaNV": 7}), \
             patch.object(flask_app._db, "count_face_embeddings", return_value=0), \
             patch.object(flask_app, "_decode_face_image", return_value=np.zeros((8, 8, 3), dtype=np.uint8)), \
             patch("face_engine.face_engine.initialize"), \
             patch("face_engine.face_engine.detect_embeddings", side_effect=[[
                 {"head_pose": pose, "vector_bytes": vector.astype("<f4").tobytes()}
             ] for pose in ({"yaw": 0.0, "pitch": 0.0}, {"yaw": 20.0, "pitch": 0.0},
                            {"yaw": -20.0, "pitch": 0.0}, {"yaw": 0.0, "pitch": 20.0},
                            {"yaw": 0.0, "pitch": -20.0})]), \
             patch.object(services, "save_face_embeddings", return_value={"success": True, "embeddings_saved": 5} ) as save:
            started = self.client.post("/api/employees/7/face/register", json={"action": "start"})
            self.assertEqual(started.status_code, 200)
            sid = started.json["session_id"]
            incomplete = self.client.post("/api/employees/7/face/register", json={"action": "complete", "session_id": sid})
            self.assertEqual(incomplete.status_code, 400)
            for _ in range(5):
                captured = self.client.post("/api/employees/7/face/register", json={"action": "capture", "session_id": sid, "image": "AA=="})
                self.assertEqual(captured.status_code, 200)
            completed = self.client.post("/api/employees/7/face/register", json={"action": "complete", "session_id": sid})
            self.assertEqual(completed.status_code, 200)
            self.assertEqual(save.call_count, 1)
            self.assertEqual(len(save.call_args.args[1]), 5)

    def test_identify_verify_and_bad_payload_routes(self):
        import cv2
        ok, encoded = cv2.imencode(".jpg", np.zeros((8, 8, 3), dtype=np.uint8))
        image = __import__("base64").b64encode(encoded.tobytes()).decode("ascii")
        match = {"status": "MATCH", "match": True, "MaNV": 7, "HoTen": "An", "similarity": 0.99}
        with patch.object(services, "identify_face_frame", return_value=match), \
             patch.object(services, "verify_face_frame", return_value=match):
            self.assertEqual(self.client.post("/api/face/identify", json={"image": image}).json["MaNV"], 7)
            self.assertEqual(self.client.post("/api/face/verify", json={"image": image, "MaNV": 7}).json["match"], True)
        self.assertEqual(self.client.post("/api/face/identify", json={"image": "!"}).status_code, 400)
        self.assertEqual(self.client.post("/api/face/verify", json={"image": image}).status_code, 400)

    def test_unrestricted_legacy_enrollment_is_rejected(self):
        response = self.client.post("/api/employees/7/face/register", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("pose-guided", response.json["message"])

    def test_pose_endpoint_and_server_side_capture_gate(self):
        vector = np.zeros(512, dtype="<f4"); vector[0] = 1
        face_frontal = {"head_pose": {"yaw": 0.0, "pitch": 0.0}, "vector_bytes": vector.tobytes()}
        with patch.object(services, "fetch_employee", return_value={"MaNV": 7}), \
             patch.object(flask_app._db, "count_face_embeddings", return_value=0), \
             patch("face_engine.face_engine.initialize"), \
             patch.object(flask_app, "_read_camera_frame", return_value=(True, np.zeros((8, 8, 3), dtype=np.uint8))), \
             patch("face_engine.face_engine.inspect_pose", return_value={"current_pose": "frontal", "yaw": 0.0, "pitch": 0.0}), \
             patch("face_engine.face_engine.detect_embeddings", side_effect=[[face_frontal], [face_frontal]]), \
             patch.object(services, "save_face_embeddings") as save:
            started = self.client.post("/api/employees/7/face/register", json={"action": "start"})
            sid = started.json["session_id"]
            pose = self.client.post("/api/employees/7/face/register", json={"action": "pose", "session_id": sid})
            self.assertEqual(pose.status_code, 200, pose.json)
            self.assertEqual(pose.json["current_pose"], "frontal")
            self.assertEqual(pose.json["expected_pose"], "frontal")
            self.assertTrue(pose.json["pose_ok"])
            first = self.client.post("/api/employees/7/face/register", json={"action": "capture", "session_id": sid})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json["captured"], 1)
            wrong = self.client.post("/api/employees/7/face/register", json={"action": "capture", "session_id": sid})
            self.assertEqual(wrong.status_code, 409)
            self.assertEqual(wrong.json["expected_pose"], "left")
            self.assertFalse(wrong.json["pose_ok"])
            save.assert_not_called()

    def test_enrollment_still_rejects_multiple_faces(self):
        multiple_faces = [
            {"head_pose": {"yaw": 0.0, "pitch": 0.0}, "vector_bytes": b"a"},
            {"head_pose": {"yaw": 0.0, "pitch": 0.0}, "vector_bytes": b"b"},
        ]
        with patch.object(services, "fetch_employee", return_value={"MaNV": 7}), \
             patch.object(flask_app._db, "count_face_embeddings", return_value=0), \
             patch.object(flask_app, "_decode_face_image", return_value=np.zeros((8, 8, 3), dtype=np.uint8)), \
             patch("face_engine.face_engine.initialize"), \
             patch("face_engine.face_engine.detect_embeddings", return_value=multiple_faces):
            started = self.client.post("/api/employees/7/face/register", json={"action": "start"})
            sid = started.json["session_id"]
            captured = self.client.post("/api/employees/7/face/register", json={
                "action": "capture", "session_id": sid, "image": "AA=="
            })
            self.assertEqual(captured.status_code, 409)
            self.assertEqual(flask_app._enrollment_sessions[sid]["embeddings"], [])


class HeadPoseTests(unittest.TestCase):
    def test_five_keypoint_solver_recovers_yaw_and_pitch(self):
        import cv2
        model = face_engine._POSE_MODEL_POINTS
        camera = np.asarray([[640.0, 0, 320], [0, 640.0, 240], [0, 0, 1]])
        translation = np.asarray([[0.0], [0.0], [600.0]])
        for axis_angle, expected_key in [([0, 0.35, 0], "yaw"), ([0, -0.35, 0], "yaw"),
                                         ([0.25, 0, 0], "pitch"), ([-0.25, 0, 0], "pitch")]:
            projected, _ = cv2.projectPoints(model, np.asarray(axis_angle, dtype=float),
                                             translation, camera, np.zeros((4, 1)))
            pose = face_engine.estimate_head_pose(projected.reshape(-1, 2), (480, 640, 3))
            self.assertGreater(abs(pose[expected_key]), 12.0)
            self.assertLess(abs(pose["pitch" if expected_key == "yaw" else "yaw"]), 1.0)

    def test_pose_classifier_requires_expected_direction(self):
        cases = [
            ({"yaw": 0, "pitch": 0}, "frontal"),
            ({"yaw": 20, "pitch": 0}, "left"),
            ({"yaw": -20, "pitch": 0}, "right"),
            ({"yaw": 0, "pitch": 20}, "up"),
            ({"yaw": 0, "pitch": -20}, "down"),
        ]
        for angles, expected in cases:
            with self.subTest(expected=expected):
                result = flask_app._pose_result(angles, expected)
                self.assertEqual(result["current_pose"], expected)
                self.assertEqual(result["expected_pose"], expected)
                self.assertTrue(result["pose_ok"])
                wrong = flask_app._pose_result(angles, "down" if expected != "down" else "up")
                self.assertFalse(wrong["pose_ok"])


if __name__ == "__main__":
    unittest.main()
