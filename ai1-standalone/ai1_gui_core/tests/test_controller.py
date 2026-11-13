"""Hardware-free checks for GUI controller wiring."""

import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np

from ai1_gui_core.controller import AI1GuiController, DuplicateFaceError


class FakeCamera:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.employee = {"MaNV": "MaNV_1", "HoTen": "Employee One", "created_at": "now"}
        self.gallery = {"MaNV_1": {"HoTen": "Employee One", "embeddings": (np.eye(1, 512, 0)[0],)}}
        self.store = Mock()
        self.store.load.return_value = ([self.employee], self.gallery)
        self.store.add_employee.return_value = ([self.employee], self.gallery)
        self.store.delete_employee.return_value = ([], {})

    def test_startup_initializes_arcface_loads_local_gallery_and_opens_camera(self):
        camera = FakeCamera()
        controller = AI1GuiController(store=self.store, camera_factory=lambda: camera)
        with patch("ai1_gui_core.controller.initialize_ai1", return_value=object()) as initialize:
            result = controller.startup(threading.Event())
        initialize.assert_called_once_with()
        self.store.ensure.assert_called_once_with()
        self.store.load.assert_called_once_with()
        self.assertTrue(result["ready"])
        self.assertTrue(result["camera_available"])
        self.assertIn("MaNV_1", result["gallery"])

    def test_startup_remains_usable_without_camera(self):
        controller = AI1GuiController(store=self.store,
                                      camera_factory=lambda: (_ for _ in ()).throw(RuntimeError("no webcam")))
        with patch("ai1_gui_core.controller.initialize_ai1", return_value=object()):
            result = controller.startup(threading.Event())
        self.assertTrue(result["ready"])
        self.assertFalse(result["camera_available"])
        self.assertEqual(result["camera_error"], "no webcam")

    def test_startup_loads_standalone_gallery_before_model_initialization(self):
        calls = []
        self.store.ensure.side_effect = lambda: calls.append("ensure")
        self.store.load.side_effect = lambda: (
            calls.append("load") or ([self.employee], self.gallery)
        )
        controller = AI1GuiController(store=self.store, camera_factory=FakeCamera)

        def initialize():
            calls.append("model")
            return object()

        with patch("ai1_gui_core.controller.initialize_ai1", side_effect=initialize):
            controller.startup(threading.Event())

        self.assertEqual(calls[:3], ["ensure", "load", "model"])
        self.assertEqual(controller.employees, [self.employee])
        self.assertIn("MaNV_1", controller.gallery)

    def test_register_and_delete_update_cached_gallery(self):
        controller = AI1GuiController(store=self.store)
        state = controller.register_employee("MaNV_1", "Employee One", {}, "stage", overwrite=True)
        self.assertEqual(state["employees"], [self.employee])
        self.store.add_employee.assert_called_once_with(
            "MaNV_1", "Employee One", {}, "stage", overwrite=True
        )
        deleted = controller.delete_employee("MaNV_1", confirmed=True)
        self.assertEqual(deleted["employees"], [])
        self.store.delete_employee.assert_called_once_with("MaNV_1", confirmed=True)

    def test_duplicate_face_detection_uses_threshold_and_excludes_same_employee(self):
        controller = AI1GuiController(store=self.store, threshold=0.45)
        controller.gallery = self.gallery
        embedding = self.gallery["MaNV_1"]["embeddings"][0]

        duplicate = controller.find_duplicate_employee(embedding, exclude_identity="MaNV_2")
        self.assertEqual(duplicate["MaNV"], "MaNV_1")
        self.assertEqual(duplicate["HoTen"], "Employee One")
        self.assertGreaterEqual(duplicate["similarity"], 0.45)
        self.assertEqual(duplicate["threshold"], 0.45)
        self.assertIsNone(controller.find_duplicate_employee(
            embedding, exclude_identity="MaNV_1"
        ))

    def test_duplicate_employee_registration_is_rejected_before_storage_write(self):
        controller = AI1GuiController(store=self.store, threshold=0.45)
        controller.gallery = self.gallery
        embedding = self.gallery["MaNV_1"]["embeddings"][0]
        with self.assertRaises(DuplicateFaceError) as raised:
            controller.register_employee(
                "MaNV_2", "Employee Two", {"frontal": embedding}, "stage"
            )
        self.assertEqual(raised.exception.duplicate["MaNV"], "MaNV_1")
        self.store.add_employee.assert_not_called()

    def test_three_embedding_recognition_uses_standalone_recognition_logic(self):
        vector = np.zeros(512, dtype=np.float32)
        vector[0] = 1.0
        gallery = {"MaNV_1": {"HoTen": "Employee One", "embeddings": (vector,)}}
        result = AI1GuiController.recognize_embeddings([vector, vector, vector], gallery, threshold=0.45)
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["predicted_id"], "MaNV_1")

    def test_three_embedding_recognition_can_return_unknown(self):
        enrolled = np.zeros(512, dtype=np.float32)
        enrolled[0] = 1.0
        unknown = np.zeros(512, dtype=np.float32)
        unknown[1] = 1.0
        gallery = {"MaNV_1": {"HoTen": "Employee One", "embeddings": (enrolled,)}}
        result = AI1GuiController.recognize_embeddings([unknown, unknown, unknown], gallery,
                                                       threshold=0.45)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["predicted_id"], "UNKNOWN")

    def test_session_overlap_is_rejected_until_current_session_ends(self):
        controller = AI1GuiController(store=self.store)
        first = controller.begin_session("session-one")
        self.assertEqual(first, "session-one")
        self.assertIsNone(controller.begin_session("session-two"))
        self.assertTrue(controller.end_session(first))
        self.assertEqual(controller.begin_session("session-two"), "session-two")
        self.assertTrue(controller.end_session("session-two"))


if __name__ == "__main__":
    unittest.main()
