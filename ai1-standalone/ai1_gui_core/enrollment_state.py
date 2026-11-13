"""Deterministic five-pose manual-capture state used by the desktop GUI."""

import numpy as np

import face_matching

from ai1_standalone_core.config import (
    EMBEDDING_DIMENSIONS,
    ENROLLMENT_IDENTITY_THRESHOLD,
    POSES,
)


class EnrollmentCaptureState:
    def __init__(self, same_person_threshold=ENROLLMENT_IDENTITY_THRESHOLD):
        self.same_person_threshold = float(same_person_threshold)
        if not np.isfinite(self.same_person_threshold) or not -1.0 <= self.same_person_threshold <= 1.0:
            raise ValueError("same_person_threshold must be between -1 and 1.")
        self.current_pose_index = 0
        self.embeddings = {}

    @property
    def current_pose(self):
        if self.current_pose_index >= len(POSES):
            return None
        return POSES[self.current_pose_index]

    @property
    def complete(self):
        return set(self.embeddings) == set(POSES)

    def capture(self, outcome):
        """Commit one quality-valid 512D sample for the expected pose slot.

        Pose estimates are intentionally not a capture gate; they remain visible
        in the GUI for the user to follow the requested direction.
        """
        pose = self.current_pose
        if pose is None:
            raise RuntimeError("All five enrollment poses have already been captured.")
        if not isinstance(outcome, dict) or outcome.get("status") != "OK":
            code = outcome.get("code", "QUALITY CHECK") if isinstance(outcome, dict) else "QUALITY CHECK"
            raise ValueError(f"Only a quality-valid enrollment result can be captured: {code}.")
        embedding = face_matching.normalize_embedding(outcome.get("embedding"), EMBEDDING_DIMENSIONS)
        if pose != POSES[0]:
            reference = self.embeddings.get(POSES[0])
            if reference is None or face_matching.cosine_similarity(reference, embedding) < self.same_person_threshold:
                raise ValueError("The pose sample does not match the frontal reference.")
        self.embeddings[pose] = embedding
        self.current_pose_index = next(
            (index for index, candidate in enumerate(POSES) if candidate not in self.embeddings),
            len(POSES),
        )
        return {"pose": pose, "captured": len(self.embeddings), "complete": self.complete}

    def clear_pose(self, pose):
        if pose not in POSES:
            raise ValueError("Unknown enrollment pose.")
        self.embeddings.pop(pose, None)
        self.current_pose_index = next(
            (index for index, candidate in enumerate(POSES) if candidate not in self.embeddings),
            len(POSES),
        )

    def validate_complete(self):
        """Revalidate all five 512D vectors, frontal identity, and pairwise consistency."""
        if not self.complete:
            return {"valid": False, "bad_poses": list(POSES),
                    "reason": "All five enrollment poses are required."}
        normalized = {}
        try:
            for pose in POSES:
                normalized[pose] = face_matching.normalize_embedding(
                    self.embeddings[pose], EMBEDDING_DIMENSIONS
                )
        except (TypeError, ValueError) as exc:
            return {"valid": False, "bad_poses": list(POSES), "reason": str(exc)}
        reference = normalized[POSES[0]]
        bad_poses = [pose for pose in POSES[1:]
                     if face_matching.cosine_similarity(reference, normalized[pose])
                     < self.same_person_threshold]
        if bad_poses:
            return {"valid": False, "bad_poses": bad_poses,
                    "reason": "A pose does not match the frontal sample."}
        from ai1_standalone_core.enrollment import five_pose_consistency

        consistency = five_pose_consistency(normalized, self.same_person_threshold)
        if not consistency["valid"]:
            return consistency
        self.embeddings = normalized
        return consistency
