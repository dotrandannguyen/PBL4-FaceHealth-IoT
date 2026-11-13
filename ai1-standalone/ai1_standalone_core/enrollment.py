"""Five-pose interactive enrollment and same-person consistency validation."""

import itertools
from pathlib import Path
import shutil
import tempfile

import cv2
import numpy as np

import face_matching

from .ai1_adapter import validate_enrollment_frame
from .config import ENROLLMENT_IDENTITY_THRESHOLD, POSES


def five_pose_consistency(embeddings_by_pose, threshold=ENROLLMENT_IDENTITY_THRESHOLD):
    if set(embeddings_by_pose) != set(POSES):
        return {"valid": False, "scores": [], "bad_poses": list(POSES),
                "reason": "All five enrollment poses are required."}
    scores = []
    per_pose = {pose: [] for pose in POSES}
    for first, second in itertools.combinations(POSES, 2):
        score = face_matching.cosine_similarity(embeddings_by_pose[first], embeddings_by_pose[second])
        scores.append({"first": first, "second": second, "similarity": score})
        per_pose[first].append(score)
        per_pose[second].append(score)
    mean_similarity = {pose: float(sum(values) / len(values)) for pose, values in per_pose.items()}
    inconsistent = any(item["similarity"] < float(threshold) for item in scores)
    bad_poses = []
    if inconsistent:
        lowest = min(mean_similarity.values())
        bad_poses = [pose for pose in POSES if mean_similarity[pose] <= lowest + 1e-6]
    return {"valid": not bad_poses, "scores": scores,
            "mean_similarity": mean_similarity, "bad_poses": bad_poses,
            "reason": "Five samples are consistent." if not bad_poses else
                      f"SAMPLES DIFFER TOO MUCH: retake {', '.join(bad_poses)}."}


def _preview_text(frame, identity, pose, captured, message):
    preview = frame.copy()
    lines = [f"Employee: {identity}", f"Pose: {pose.upper()}", f"Captured: {captured}/5",
             "SPACE capture | R retake current | Q/ESC cancel", message[:88]]
    for index, line in enumerate(lines):
        color = (40, 240, 240) if index < 4 else (50, 210, 255)
        cv2.putText(preview, line, (12, 28 + index * 28), cv2.FONT_HERSHEY_SIMPLEX,
                    0.58, color, 2, cv2.LINE_AA)
    return preview


def capture_five_pose_enrollment(engine, source, identity, data_root):
    """Capture into a hidden staging folder; return it only after all checks pass."""
    root = Path(data_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".pending-{identity}-", dir=root))
    embeddings = {}
    captured = set()
    queue = list(POSES)
    index = 0
    message = "Face the requested direction, then press SPACE."
    try:
        while True:
            frame = source.get_frame()
            if frame is None:
                message = "RETRY: NO FACE / NO FRAME"
                blank = cv2.putText(
                    np.zeros((480, 640, 3), dtype=np.uint8), message, (12, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 40, 255), 2, cv2.LINE_AA,
                )
                cv2.imshow("AI1 standalone enrollment", blank)
                key = cv2.waitKey(30) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    return None
                continue
            current_pose = queue[index]
            cv2.imshow("AI1 standalone enrollment", _preview_text(
                frame, identity, current_pose, len(captured), message
            ))
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                return None
            if key not in (ord(" "), ord("r"), ord("R")):
                continue
            retake = key in (ord("r"), ord("R"))
            outcome = validate_enrollment_frame(engine, frame, current_pose)
            if outcome["status"] != "OK":
                message = f"{outcome['code']}: {outcome['reason']}"
                print(message)
                continue
            image_path = stage / f"{current_pose}.jpg"
            if image_path.exists() and not retake:
                message = f"RETAKE {current_pose}: press R to replace this staged pose."
                continue
            if not cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                message = "RETRY: COULD NOT SAVE IMAGE"
                continue
            embeddings[current_pose] = outcome["embedding"]
            captured.add(current_pose)
            message = f"Captured {current_pose}."
            index += 1
            if index < len(queue):
                continue

            consistency = five_pose_consistency(embeddings)
            if consistency["valid"]:
                return {"stage": stage, "embeddings": embeddings}
            queue = consistency["bad_poses"]
            index = 0
            message = f"{consistency['reason']} Press R to replace the current staged pose."
            print(message)
    finally:
        try:
            cv2.destroyWindow("AI1 standalone enrollment")
        except cv2.error:
            pass
        if stage.exists():
            # The successful caller moves this folder to images/<ID>; cancellation cleans it up.
            if not embeddings or len(embeddings) != len(POSES) or not five_pose_consistency(embeddings)["valid"]:
                shutil.rmtree(stage, ignore_errors=True)
