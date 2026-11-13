"""Fresh-frame recognition using production ArcFace embeddings and MAX matching."""

import itertools
import time

import cv2
import numpy as np

import face_engine as production_face_engine
import face_matching

from .ai1_adapter import classify_pose, extract_single_face_embedding
from .config import (
    EMBEDDING_DIMENSIONS,
    FRAME_CONSISTENCY_THRESHOLD,
    FRAME_INTERVAL_MS,
    RECOGNITION_TIMEOUT_SECONDS,
    RECOGNITION_THRESHOLD,
    STALE_FRAME_SECONDS,
)


def check_three_frame_consistency(embeddings, threshold=FRAME_CONSISTENCY_THRESHOLD):
    """Require all three pairwise cosine scores to meet the temporal gate."""
    if len(embeddings) != 3:
        return {"valid": False, "scores": [], "min_similarity": None,
                "reason": "RETRY: exactly three valid frames are required."}
    try:
        vectors = [face_matching.normalize_embedding(item, EMBEDDING_DIMENSIONS) for item in embeddings]
        scores = [face_matching.cosine_similarity(vectors[left], vectors[right])
                  for left, right in itertools.combinations(range(3), 2)]
    except (TypeError, ValueError) as exc:
        return {"valid": False, "scores": [], "min_similarity": None,
                "reason": f"RETRY: invalid frame embedding ({exc})."}
    minimum = min(scores)
    valid = minimum >= float(threshold)
    return {"valid": valid, "scores": scores, "min_similarity": minimum,
            "reason": "Consistent frames." if valid else "RETRY: INCONSISTENT FRAMES."}


def face_sharpness(frame, bbox):
    """Return Laplacian variance on the face crop, matching AI1's frame gate."""
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        return 0.0
    try:
        if len(bbox) != 4:
            return 0.0
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return 0.0
        gray = cv2.cvtColor(cv2.resize(crop, (128, 160)), cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except (TypeError, ValueError, cv2.error):
        return 0.0


def assess_recognition_face_quality(frame, face):
    """Apply a frame-relative size/crop/sharpness gate without an enrollment guide."""
    def rejected(code, reason):
        return {"ready": False, "code": code, "reason": reason, "sharpness": 0.0}

    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
        return rejected("INVALID FRAME", "Khung hình camera không hợp lệ.")
    height, width = frame.shape[:2]
    try:
        box = np.asarray(face.get("bbox"), dtype=np.float64).reshape(-1)
        score = float(face.get("detection_score"))
    except (AttributeError, TypeError, ValueError):
        return rejected("INVALID BBOX", "Không đọc được vùng khuôn mặt.")
    if box.size != 4 or not np.all(np.isfinite(box)) or not np.isfinite(score):
        return rejected("INVALID BBOX", "Vùng khuôn mặt không hợp lệ.")
    if score < production_face_engine.DETECTION_MIN_SCORE:
        return rejected("LOW DETECTION SCORE", "Khuôn mặt chưa được phát hiện đủ rõ.")

    x1, y1, x2, y2 = [float(value) for value in box]
    face_width, face_height = x2 - x1, y2 - y1
    if face_width <= 0 or face_height <= 0:
        return rejected("INVALID BBOX", "Vùng khuôn mặt không hợp lệ.")
    if face_width < max(48.0, width * 0.10) or face_height < max(48.0, height * 0.12):
        return rejected("FACE TOO SMALL", "Mặt quá xa — tiến gần camera hơn.")
    if face_width > width * 0.90 or face_height > height * 0.90:
        return rejected("FACE TOO LARGE", "Mặt quá gần — lùi nhẹ khỏi camera.")

    clipped_x1, clipped_y1 = max(0.0, x1), max(0.0, y1)
    clipped_x2, clipped_y2 = min(float(width), x2), min(float(height), y2)
    visible_area = max(0.0, clipped_x2 - clipped_x1) * max(0.0, clipped_y2 - clipped_y1)
    if visible_area / (face_width * face_height) < 0.94:
        return rejected("FACE CROPPED", "Khuôn mặt bị cắt ở mép khung hình.")

    edge_x, edge_y = max(2.0, face_width * 0.02), max(2.0, face_height * 0.02)
    if (x1 < edge_x or y1 < edge_y
            or width - x2 < edge_x or height - y2 < edge_y):
        return rejected("FACE TOO CLOSE TO EDGE", "Đưa khuôn mặt xa mép khung hình hơn.")

    sharpness = face_sharpness(frame, box)
    if not np.isfinite(sharpness) or sharpness < 20.0:
        return rejected("TOO BLURRY", "Ảnh bị mờ — giữ yên và kiểm tra camera.")
    return {"ready": True, "code": "OK", "reason": "Khuôn mặt sẵn sàng.",
            "sharpness": sharpness}


def _notify_frame_callback(callback, payload):
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:
        # A preview update must never interrupt the recognition worker.
        return


def identify_embedding(embedding, gallery, threshold=RECOGNITION_THRESHOLD):
    """Run the existing normalized cosine / five-sample MAX matcher."""
    try:
        query = face_matching.normalize_embedding(embedding, EMBEDDING_DIMENSIONS)
        if not gallery:
            return {"status": "UNKNOWN", "predicted_id": "UNKNOWN", "score": 0.0,
                    "threshold": float(threshold), "reason": "EMPTY GALLERY", "latency_ms": 0.0}
        production_result = face_matching.identify_embedding(query, gallery, threshold)
    except (TypeError, ValueError) as exc:
        return {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "threshold": float(threshold), "reason": f"INVALID EMBEDDING: {exc}", "latency_ms": 0.0}
    matched = bool(production_result["match"])
    return {
        "status": "MATCH" if matched else "UNKNOWN",
        "predicted_id": production_result["MaNV"] if matched else "UNKNOWN",
        "score": float(production_result["similarity"] or 0.0),
        "threshold": float(threshold),
        "reason": "MAX SIMILARITY MATCH" if matched else "BELOW THRESHOLD",
        "latency_ms": 0.0,
    }


def recognize_three_embeddings(embeddings, gallery, threshold=RECOGNITION_THRESHOLD,
                               consistency_threshold=FRAME_CONSISTENCY_THRESHOLD,
                               sharpnesses=None):
    """Select one sharpest-frame embedding after consistency; never average vectors."""
    consistency = check_three_frame_consistency(embeddings, consistency_threshold)
    if not consistency["valid"]:
        return {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "threshold": float(threshold), "reason": consistency["reason"], "latency_ms": 0.0,
                "consistency_scores": consistency["scores"]}
    if sharpnesses is None:
        sharpnesses = (0.0, 0.0, 0.0)
    if len(sharpnesses) != 3:
        return {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "threshold": float(threshold), "reason": "RETRY: three sharpness scores are required.",
                "latency_ms": 0.0, "consistency_scores": consistency["scores"]}
    try:
        sharpnesses = [float(value) for value in sharpnesses]
        if not np.all(np.isfinite(sharpnesses)):
            raise ValueError("Sharpness scores must be finite.")
        vectors = [face_matching.normalize_embedding(item, EMBEDDING_DIMENSIONS) for item in embeddings]
    except (TypeError, ValueError) as exc:
        return {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "threshold": float(threshold), "reason": f"RETRY: invalid snapshot ({exc}).",
                "latency_ms": 0.0, "consistency_scores": consistency["scores"]}

    selected_index = int(np.argmax(np.asarray(sharpnesses, dtype=np.float64)))
    result = identify_embedding(vectors[selected_index], gallery, threshold)
    result.update({
        "selected_frame_index": selected_index,
        "sharpness": sharpnesses[selected_index],
        "consistency_scores": consistency["scores"],
        "temporal_consistency_min": consistency["min_similarity"],
    })
    return result


def recognize_three_snapshots(snapshots, gallery, threshold=RECOGNITION_THRESHOLD,
                              consistency_threshold=FRAME_CONSISTENCY_THRESHOLD):
    """Match the best frame from exactly three validated snapshot records."""
    if len(snapshots) != 3:
        return {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "threshold": float(threshold), "reason": "RETRY: exactly three snapshots are required.",
                "latency_ms": 0.0}
    result = recognize_three_embeddings(
        [item["embedding"] for item in snapshots], gallery, threshold,
        consistency_threshold, [item["sharpness"] for item in snapshots],
    )
    result["latency_ms"] = max(0.0, float(result.get("latency_ms", 0.0)))
    if result["status"] in {"MATCH", "UNKNOWN"}:
        best = snapshots[result["selected_frame_index"]]
        result.update({
            "best_frame": best["frame"].copy(),
            "bbox": list(best["bbox"]),
            "sequence": int(best["sequence"]),
        })
    return result


def _snapshot_fields(packet, fallback_sequence):
    """Normalize FramePacket sources while retaining compatibility with the CLI source."""
    if isinstance(packet, np.ndarray):
        return packet, fallback_sequence, time.monotonic()
    frame = getattr(packet, "frame", None)
    sequence = getattr(packet, "sequence", None)
    captured_at = getattr(packet, "captured_at", None)
    if (not isinstance(frame, np.ndarray) or not isinstance(sequence, int)
            or not isinstance(captured_at, (int, float))):
        return None
    return frame, sequence, float(captured_at)


def _retry_result(reason, threshold, started, captured_frames):
    return {
        "status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
        "threshold": float(threshold), "reason": f"RETRY: {reason}",
        "latency_ms": (time.perf_counter() - started) * 1000.0,
        "captured_frames": captured_frames,
    }


def recognize_sequence_from_source(engine, source, gallery, stop_event,
                                   threshold=RECOGNITION_THRESHOLD,
                                   consistency_threshold=FRAME_CONSISTENCY_THRESHOLD,
                                   interval_ms=FRAME_INTERVAL_MS,
                                   stale_seconds=STALE_FRAME_SECONDS,
                                   timeout_seconds=RECOGNITION_TIMEOUT_SECONDS,
                                   progress_callback=None, frame_callback=None):
    """Capture three fresh snapshots, verify identity consistency and match the sharpest."""
    started = time.perf_counter()
    deadline = time.monotonic() + float(timeout_seconds)
    snapshots = []
    last_sequence = -1
    last_capture_time = 0.0
    fallback_sequence = 0
    last_failure = "CAMERA_TIMEOUT"

    while len(snapshots) < 3 and time.monotonic() < deadline:
        if stop_event.is_set():
            return None
        packet = source.get_frame()
        fields = _snapshot_fields(packet, fallback_sequence + 1) if packet is not None else None
        if fields is None:
            last_failure = "CAMERA_DISCONNECTED"
            stop_event.wait(0.02)
            continue
        frame, sequence, captured_at = fields
        if isinstance(packet, np.ndarray):
            fallback_sequence += 1
        age = time.monotonic() - captured_at
        if age < -0.1 or age > float(stale_seconds):
            last_failure = "STALE_FRAME"
            stop_event.wait(0.02)
            continue
        if sequence <= last_sequence:
            last_failure = "STALE_FRAME"
            stop_event.wait(0.02)
            continue
        if snapshots and captured_at - last_capture_time < float(interval_ms) / 1000.0:
            stop_event.wait(0.01)
            continue

        extracted = extract_single_face_embedding(engine, frame)
        if extracted["status"] != "OK":
            face = extracted.get("face")
            _notify_frame_callback(frame_callback, {
                "sequence": sequence,
                "frame_shape": list(frame.shape[:2]),
                "observed_at": time.monotonic(),
                "bbox": list(face["bbox"]) if isinstance(face, dict) and face.get("bbox") else None,
                "detection_score": face.get("detection_score") if isinstance(face, dict) else None,
                "detected_pose": classify_pose(face) if isinstance(face, dict) else "—",
                "quality_status": "RETRY",
                "code": extracted["code"],
                "reason": extracted.get("reason", extracted["code"]),
            })
            return _retry_result(extracted["code"], threshold, started, len(snapshots))
        face = extracted["face"]
        quality = assess_recognition_face_quality(frame, face)
        _notify_frame_callback(frame_callback, {
            "sequence": sequence,
            "frame_shape": list(frame.shape[:2]),
            "observed_at": time.monotonic(),
            "bbox": list(face["bbox"]),
            "detection_score": float(face["detection_score"]),
            "detected_pose": classify_pose(face),
            "quality_status": "READY" if quality["ready"] else "RETRY",
            "code": quality["code"],
            "reason": quality["reason"],
            "sharpness": quality["sharpness"],
        })
        if not quality["ready"]:
            return _retry_result(quality["code"], threshold, started, len(snapshots))
        sharpness = quality["sharpness"]
        snapshots.append({
            "frame": frame.copy(),
            "embedding": extracted["embedding"],
            "bbox": list(face["bbox"]),
            "sharpness": sharpness,
            "sequence": sequence,
            "captured_at": captured_at,
        })
        last_sequence = sequence
        last_capture_time = captured_at
        if progress_callback is not None:
            progress_callback(len(snapshots), 3)

    if stop_event.is_set():
        return None
    if len(snapshots) != 3:
        return _retry_result(last_failure if last_failure else "TIMEOUT", threshold,
                             started, len(snapshots))

    result = recognize_three_snapshots(snapshots, gallery, threshold, consistency_threshold)
    result["latency_ms"] = (time.perf_counter() - started) * 1000.0
    result["captured_frames"] = 3
    return result
