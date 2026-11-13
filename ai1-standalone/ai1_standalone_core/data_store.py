"""Atomic JSON/NPZ/image persistence owned only by the standalone app."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import uuid

import numpy as np

import face_matching

from .config import DATA_ROOT, EMBEDDING_DIMENSIONS, IMAGES_ROOT, POSES
from .utils import safe_identity_path, validate_employee_id


class StandaloneStore:
    def __init__(self, root=DATA_ROOT):
        self.root = Path(root).resolve()
        self.employees_path = self.root / "employees.json"
        self.embeddings_path = self.root / "embeddings.npz"
        self.images_root = self.root / "images"
        self._lock = threading.RLock()

    def ensure(self):
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            self.images_root.mkdir(parents=True, exist_ok=True)
            if not self.employees_path.exists():
                self._atomic_bytes(self.employees_path, b"[]\n")
            if not self.embeddings_path.exists():
                self._write_embedding_arrays([], [], np.empty((0, EMBEDDING_DIMENSIONS), dtype=np.float32))

    def _atomic_bytes(self, destination, content):
        destination = Path(destination)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".ai1-", suffix=".tmp",
                                             dir=self.root, delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, destination)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _write_embedding_arrays(self, identities, poses, vectors):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w+b", prefix=".ai1-gallery-", suffix=".npz",
                                             dir=self.root, delete=False) as stream:
                temp_path = Path(stream.name)
                np.savez_compressed(
                    stream,
                    MaNV=np.asarray(identities, dtype=np.str_),
                    poses=np.asarray(poses, dtype=np.str_),
                    embeddings=np.asarray(vectors, dtype=np.float32).reshape(-1, EMBEDDING_DIMENSIONS),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.embeddings_path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _write_employees(self, employees):
        payload = (json.dumps(employees, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self._atomic_bytes(self.employees_path, payload)

    def _move_directory(self, source, destination):
        source, destination = Path(source), Path(destination)
        for candidate in (source.resolve(), destination.parent.resolve()):
            try:
                candidate.relative_to(self.root)
            except ValueError as exc:
                raise ValueError("Standalone directory operation escaped ai1_standalone_data.") from exc
        if destination.exists():
            raise FileExistsError(f"Standalone destination already exists: {destination}")
        # shutil.move falls back to a copy/remove when Windows denies a directory rename.
        shutil.move(str(source), str(destination))

    def _read_arrays(self):
        try:
            with np.load(self.embeddings_path, allow_pickle=False) as saved:
                identities = np.asarray(saved["MaNV"])
                poses = np.asarray(saved["poses"])
                vectors = np.asarray(saved["embeddings"], dtype=np.float32)
        except (OSError, ValueError, KeyError) as exc:
            raise ValueError(f"Standalone embeddings file is invalid: {exc}") from exc
        if identities.ndim != 1 or poses.ndim != 1:
            raise ValueError("Standalone embedding IDs and poses must be one-dimensional.")
        if vectors.ndim != 2 or vectors.shape[1:] != (EMBEDDING_DIMENSIONS,):
            raise ValueError(f"Standalone embeddings must have {EMBEDDING_DIMENSIONS} dimensions.")
        if len(identities) != len(vectors) or len(poses) != len(vectors):
            raise ValueError("Standalone IDs, poses, and embedding counts differ.")
        return identities.astype(str), poses.astype(str), vectors

    def load(self):
        """Load and validate employee metadata and the full multi-sample gallery."""
        self.ensure()
        with self._lock:
            try:
                employees = json.loads(self.employees_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Standalone employee metadata is invalid: {exc}") from exc
            if not isinstance(employees, list):
                raise ValueError("employees.json must contain a list.")
            employee_map = {}
            for person in employees:
                if not isinstance(person, dict):
                    raise ValueError("employees.json contains an invalid employee record.")
                identity = validate_employee_id(person.get("MaNV"))
                name = str(person.get("HoTen", "")).strip()
                created_at = str(person.get("created_at", ""))
                if not name or not created_at or identity in employee_map:
                    raise ValueError(f"Invalid or duplicate employee record: {identity}.")
                employee_map[identity] = {"MaNV": identity, "HoTen": name, "created_at": created_at}

            identities, poses, vectors = self._read_arrays()
            gallery = {identity: {"HoTen": employee_map[identity]["HoTen"], "embeddings": [], "poses": []}
                       for identity in employee_map}
            for identity, pose, vector in zip(identities, poses, vectors):
                if identity not in employee_map:
                    raise ValueError(f"Embedding exists for unregistered employee {identity}.")
                if pose not in POSES:
                    raise ValueError(f"Invalid enrollment pose {pose} for {identity}.")
                if not np.all(np.isfinite(vector)):
                    raise ValueError(f"Embedding for {identity}/{pose} contains non-finite values.")
                norm = float(np.linalg.norm(vector))
                if not np.isfinite(norm) or not np.isclose(norm, 1.0, atol=1e-3):
                    raise ValueError(f"Embedding for {identity}/{pose} is not L2-normalized.")
                gallery[identity]["embeddings"].append(vector.copy())
                gallery[identity]["poses"].append(pose)

            if set(employee_map) != {key for key, person in gallery.items() if person["embeddings"]}:
                raise ValueError("Employee metadata and standalone gallery are out of sync.")
            for identity, person in gallery.items():
                if len(person["embeddings"]) != len(POSES) or set(person["poses"]) != set(POSES):
                    raise ValueError(f"{identity} must have exactly one sample for each of the five poses.")
                if len(set(person["poses"])) != len(POSES):
                    raise ValueError(f"{identity} has duplicate enrollment poses.")
                image_dir = safe_identity_path(self.images_root, identity)
                image_names = {path.name for path in image_dir.iterdir() if path.is_file()} if image_dir.is_dir() else set()
                if image_names != {f"{pose}.jpg" for pose in POSES}:
                    raise ValueError(f"{identity} must have all five standalone enrollment images.")
                person["embeddings"] = tuple(person["embeddings"])
                person["poses"] = tuple(person["poses"])
                person["n_samples"] = len(person["embeddings"])
            return sorted(employee_map.values(), key=lambda item: item["MaNV"].casefold()), gallery

    def add_employee(self, identity, name, embeddings_by_pose, staged_images, overwrite=False):
        identity = validate_employee_id(identity)
        name = str(name).strip()
        if not name:
            raise ValueError("Employee Name is required.")
        if not isinstance(embeddings_by_pose, dict) or set(embeddings_by_pose) != set(POSES):
            raise ValueError("Enrollment requires exactly one embedding for each of the five poses.")
        normalized = {pose: face_matching.normalize_embedding(embeddings_by_pose[pose], EMBEDDING_DIMENSIONS)
                      for pose in POSES}

        self.ensure()
        employees, existing_gallery = self.load()
        employee_map = {person["MaNV"]: person for person in employees}
        exists = identity in employee_map
        if exists and not overwrite:
            raise FileExistsError(f"Employee {identity} is already registered.")

        stage = Path(staged_images).resolve()
        try:
            stage.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Staged enrollment images must be inside ai1_standalone_data.") from exc
        if not stage.is_dir():
            raise FileNotFoundError("Staged enrollment image folder is missing.")
        image_files = {path.name for path in stage.iterdir() if path.is_file()}
        expected_files = {f"{pose}.jpg" for pose in POSES}
        if image_files != expected_files:
            raise ValueError("Staged enrollment folder must contain exactly five pose JPEGs.")

        destination = safe_identity_path(self.images_root, identity)
        if destination.exists() and not exists:
            raise FileExistsError("An image folder already exists for this ID without employee metadata.")
        new_employees = [person for person in employees if person["MaNV"] != identity]
        new_employees.append({
            "MaNV": identity,
            "HoTen": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        old_ids, old_poses, old_vectors = self._read_arrays()
        keep = old_ids != identity
        ids_out = old_ids[keep].tolist()
        poses_out = old_poses[keep].tolist()
        vectors_out = [vector for vector in old_vectors[keep]]
        for pose in POSES:
            ids_out.append(identity)
            poses_out.append(pose)
            vectors_out.append(normalized[pose])
        vector_array = np.stack(vectors_out).astype(np.float32) if vectors_out else np.empty((0, 512), dtype=np.float32)

        old_employee_bytes = self.employees_path.read_bytes()
        old_embedding_bytes = self.embeddings_path.read_bytes()
        backup = self.root / f".backup-{identity}-{uuid.uuid4().hex}"
        moved_old = False
        moved_stage = False
        try:
            if destination.exists():
                self._move_directory(destination, backup)
                moved_old = True
            self._move_directory(stage, destination)
            moved_stage = True
            self._write_embedding_arrays(ids_out, poses_out, vector_array)
            self._write_employees(new_employees)
        except Exception:
            if moved_stage and destination.exists():
                shutil.rmtree(destination)
            self._atomic_bytes(self.embeddings_path, old_embedding_bytes)
            self._atomic_bytes(self.employees_path, old_employee_bytes)
            if moved_old and backup.exists():
                self._move_directory(backup, destination)
            raise
        if moved_old and backup.exists():
            shutil.rmtree(backup)
        return self.load()

    def delete_employee(self, identity, confirmed=False):
        identity = validate_employee_id(identity)
        if not confirmed:
            raise PermissionError("Delete requires explicit confirmation.")
        self.ensure()
        employees, _gallery = self.load()
        if identity not in {person["MaNV"] for person in employees}:
            raise KeyError(f"Employee {identity} is not registered.")
        new_employees = [person for person in employees if person["MaNV"] != identity]
        old_ids, old_poses, old_vectors = self._read_arrays()
        keep = old_ids != identity
        ids_out = old_ids[keep].tolist()
        poses_out = old_poses[keep].tolist()
        vectors_out = old_vectors[keep].astype(np.float32)

        destination = safe_identity_path(self.images_root, identity)
        backup = self.root / f".deleted-{identity}-{uuid.uuid4().hex}"
        moved_images = False
        old_employee_bytes = self.employees_path.read_bytes()
        old_embedding_bytes = self.embeddings_path.read_bytes()
        try:
            if destination.exists():
                self._move_directory(destination, backup)
                moved_images = True
            self._write_embedding_arrays(ids_out, poses_out, vectors_out)
            self._write_employees(new_employees)
        except Exception:
            self._atomic_bytes(self.embeddings_path, old_embedding_bytes)
            self._atomic_bytes(self.employees_path, old_employee_bytes)
            if moved_images and backup.exists():
                self._move_directory(backup, destination)
            raise
        if moved_images and backup.exists():
            shutil.rmtree(backup)
        return self.load()
