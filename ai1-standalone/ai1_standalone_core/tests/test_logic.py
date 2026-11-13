"""Deterministic logic and persistence tests; these never open a camera."""

import json
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import face_matching
from ai1_standalone_core.config import EMBEDDING_DIMENSIONS, POSES, PROJECT_ROOT
from ai1_standalone_core.app import StandaloneApplication
from ai1_standalone_core.data_store import StandaloneStore
from ai1_standalone_core.enrollment import five_pose_consistency
from ai1_standalone_core.recognition import (check_three_frame_consistency, face_sharpness,
                                             identify_embedding, recognize_three_embeddings,
                                             recognize_three_snapshots)
from ai1_standalone_core.utils import safe_identity_path, validate_employee_id


def basis(index):
    vector = np.zeros(EMBEDDING_DIMENSIONS, dtype=np.float32)
    vector[index] = 1.0
    return vector


def create_employee(store, identity="MaNV_1", name="Nguyen Van A"):
    stage = store.root / f".test-stage-{identity}"
    stage.mkdir(parents=True, exist_ok=True)
    for pose in POSES:
        (stage / f"{pose}.jpg").write_bytes(b"test-only image fixture")
    vectors = {pose: basis(index) for index, pose in enumerate(POSES)}
    return store.add_employee(identity, name, vectors, stage)


class StandaloneLogicTests(unittest.TestCase):
    def test_l2_normalize_and_dimension_512(self):
        normalized = face_matching.normalize_embedding(np.full(512, 2.0, dtype=np.float32))
        self.assertEqual(normalized.shape, (512,))
        self.assertAlmostEqual(float(np.linalg.norm(normalized)), 1.0, places=6)

    def test_cosine_similarity(self):
        self.assertAlmostEqual(face_matching.cosine_similarity(basis(0), basis(0)), 1.0, places=6)
        self.assertAlmostEqual(face_matching.cosine_similarity(basis(0), basis(1)), 0.0, places=6)

    def test_production_multi_sample_max(self):
        score = face_matching.max_sample_similarity(basis(2), [basis(0), basis(2), basis(3)])
        self.assertAlmostEqual(score, 1.0, places=6)

    def test_gallery_save_and_load(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp:
            store = StandaloneStore(temp)
            store.ensure()
            employees, gallery = create_employee(store)
            recreated_store = StandaloneStore(temp)
            loaded_employees, loaded_gallery = recreated_store.load()
        self.assertEqual(loaded_employees, employees)
        self.assertEqual(len(loaded_gallery["MaNV_1"]["embeddings"]), 5)
        self.assertEqual(set(loaded_gallery["MaNV_1"]["poses"]), set(POSES))

    def test_employee_one_thang_persists_after_store_recreation(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp:
            store = StandaloneStore(temp)
            create_employee(store, identity="1", name="thang")

            employees, gallery = StandaloneStore(temp).load()

        self.assertEqual([(item["MaNV"], item["HoTen"]) for item in employees], [("1", "thang")])
        self.assertEqual(len(gallery["1"]["embeddings"]), 5)

    def test_default_store_root_is_project_absolute_independent_of_working_directory(self):
        old_cwd = Path.cwd()
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as alternate_cwd:
            try:
                os.chdir(alternate_cwd)
                store = StandaloneStore()
                self.assertEqual(store.root, (PROJECT_ROOT / "ai1_standalone_data").resolve())
                self.assertEqual(store.employees_path, store.root / "employees.json")
                self.assertEqual(store.embeddings_path, store.root / "embeddings.npz")
                self.assertEqual(store.images_root, store.root / "images")
            finally:
                os.chdir(old_cwd)

    def test_employee_add_persists_metadata_images_and_five_embeddings(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp:
            store = StandaloneStore(temp)
            employees, gallery = create_employee(store)
            metadata = json.loads(store.employees_path.read_text(encoding="utf-8"))
            image_dir = Path(temp) / "images" / "MaNV_1"
            self.assertEqual(metadata[0]["MaNV"], "MaNV_1")
            self.assertEqual(metadata[0]["HoTen"], "Nguyen Van A")
            self.assertTrue(metadata[0]["created_at"])
            self.assertEqual(len(list(image_dir.glob("*.jpg"))), 5)
            self.assertEqual(len(gallery["MaNV_1"]["embeddings"]), 5)
            with np.load(store.embeddings_path, allow_pickle=False) as data:
                self.assertEqual(data["embeddings"].shape, (5, 512))

    def test_duplicate_employee_is_not_overwritten_without_confirmation(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp:
            store = StandaloneStore(temp)
            create_employee(store)
            stage = Path(temp) / ".replacement-stage"
            stage.mkdir()
            for pose in POSES:
                (stage / f"{pose}.jpg").write_bytes(b"replacement fixture")
            replacements = {pose: basis(index + 8) for index, pose in enumerate(POSES)}
            with self.assertRaises(FileExistsError):
                store.add_employee("MaNV_1", "Different Name", replacements, stage, overwrite=False)
            employees, gallery = store.load()
            self.assertEqual(employees[0]["HoTen"], "Nguyen Van A")
            self.assertAlmostEqual(face_matching.cosine_similarity(
                gallery["MaNV_1"]["embeddings"][0], basis(0)), 1.0, places=6)

    def test_reenroll_same_employee_replaces_all_five_samples_after_confirmation(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp:
            store = StandaloneStore(temp)
            create_employee(store, identity="1", name="thang")
            stage = Path(temp) / ".replacement-stage"
            stage.mkdir()
            for pose in POSES:
                (stage / f"{pose}.jpg").write_bytes(b"replacement image fixture")
            replacements = {pose: basis(index + 20) for index, pose in enumerate(POSES)}

            employees, gallery = store.add_employee(
                "1", "thang updated", replacements, stage, overwrite=True
            )

        self.assertEqual([(item["MaNV"], item["HoTen"]) for item in employees],
                         [("1", "thang updated")])
        self.assertEqual(len(gallery["1"]["embeddings"]), 5)
        self.assertAlmostEqual(
            face_matching.cosine_similarity(gallery["1"]["embeddings"][0], basis(20)), 1.0
        )

    def test_employee_delete_requires_confirmation_and_removes_local_data(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp:
            store = StandaloneStore(temp)
            create_employee(store)
            with self.assertRaises(PermissionError):
                store.delete_employee("MaNV_1")
            employees, gallery = store.delete_employee("MaNV_1", confirmed=True)
            self.assertEqual(employees, [])
            self.assertEqual(gallery, {})
            self.assertFalse((Path(temp) / "images" / "MaNV_1").exists())
            with np.load(store.embeddings_path, allow_pickle=False) as data:
                self.assertEqual(data["embeddings"].shape, (0, 512))

    def test_recognition_uses_sharpest_snapshot_embedding_without_averaging(self):
        angle = np.deg2rad(20.0)
        first = np.zeros(512, dtype=np.float32)
        first[:2] = (np.cos(angle), np.sin(angle))
        best = basis(0)
        third = np.zeros(512, dtype=np.float32)
        third[[0, 2]] = (np.cos(angle), np.sin(angle))
        gallery = {"MaNV_1": {"HoTen": "Nguyen Van A", "embeddings": (best,)}}
        result = recognize_three_embeddings(
            [first, best, third], gallery, threshold=0.99, sharpnesses=(40.0, 100.0, 50.0)
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["selected_frame_index"], 1)
        self.assertAlmostEqual(result["sharpness"], 100.0)

    def test_three_snapshot_helper_returns_only_best_frame(self):
        vector = basis(0)
        frames = [np.full((24, 24, 3), value, dtype=np.uint8) for value in (10, 20, 30)]
        snapshots = [
            {"embedding": vector, "sharpness": sharpness, "frame": frame,
             "bbox": [1, 1, 20, 20], "sequence": index + 10}
            for index, (sharpness, frame) in enumerate(zip((5.0, 25.0, 8.0), frames))
        ]
        result = recognize_three_snapshots(
            snapshots, {"MaNV_1": {"HoTen": "Nguyen Van A", "embeddings": (vector,)}},
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["selected_frame_index"], 1)
        np.testing.assert_array_equal(result["best_frame"], frames[1])

    def test_consistency_accepts_similar_and_rejects_different_frames(self):
        self.assertTrue(check_three_frame_consistency([basis(4), basis(4), basis(4)])['valid'])
        self.assertFalse(check_three_frame_consistency([basis(4), basis(4), basis(5)])['valid'])

    def test_incomplete_sequence_retries(self):
        result = recognize_three_embeddings([basis(0), basis(0)], {})
        self.assertEqual(result["status"], "RETRY")
        self.assertFalse(check_three_frame_consistency([basis(0), basis(0)])['valid'])

    def test_unknown_when_best_score_is_below_threshold(self):
        gallery = {"MaNV_1": {"HoTen": "Nguyen Van A", "embeddings": (basis(0), basis(1))}}
        result = identify_embedding(basis(20), gallery, threshold=0.45)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["predicted_id"], "UNKNOWN")
        self.assertLess(result["score"], result["threshold"])

    def test_invalid_id_and_path_traversal_rejected(self):
        for value in ("../outside", "..\\outside", "C:\\outside", "/outside", "UNKNOWN"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_employee_id(value)
        safe_path = safe_identity_path(Path(PROJECT_ROOT) / "ai1_standalone_data" / "images", "MaNV_1")
        self.assertEqual(safe_path.name, "MaNV_1")

    def test_wrong_dimension_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            face_matching.normalize_embedding(np.zeros(511, dtype=np.float32))
        invalid = basis(0)
        invalid[2] = np.nan
        with self.assertRaises(ValueError):
            face_matching.normalize_embedding(invalid)

    def test_five_pose_consistency_reports_outlier_poses(self):
        vectors = {pose: basis(0) for pose in POSES}
        vectors["down"] = basis(6)
        result = five_pose_consistency(vectors, threshold=0.45)
        self.assertFalse(result["valid"])
        self.assertEqual(result["bad_poses"], ["down"])

    def test_menu_can_list_employees_without_camera_or_model_load(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp:
            store = StandaloneStore(temp)
            with patch("ai1_standalone_core.app.initialize_ai1", return_value=object()), \
                 patch("builtins.input", side_effect=["3", "0"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as output:
                StandaloneApplication(store).run()
            self.assertIn("3. List registered employees", output.getvalue())
            self.assertIn("No registered employees.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
