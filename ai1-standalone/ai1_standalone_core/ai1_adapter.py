"""Thin adapter around production face_engine and pose/matching utilities."""

import time

import cv2
import numpy as np

import face_engine as production_face_engine
import face_matching

from .config import (
    EMBEDDING_DIMENSIONS,
    ENROLLMENT_CENTER_TOLERANCE,
    ENROLLMENT_EDGE_MARGIN_RATIO,
    ENROLLMENT_MAX_SIZE_RATIO,
    POSE_FRONTAL_PITCH_MAX_DEG,
    POSE_FRONTAL_YAW_MAX_DEG,
    POSE_ENROLLMENT_HYSTERESIS_DEG,
    POSE_SIDE_PITCH_MAX_DEG,
    POSE_SIDE_YAW_MAX_DEG,
    POSE_SIDE_YAW_MIN_DEG,
    POSE_VERTICAL_PITCH_MAX_DEG,
    POSE_VERTICAL_PITCH_MIN_DEG,
    POSE_VERTICAL_YAW_MAX_DEG,
)


def initialize_ai1():
    """Initialize production buffalo_l once; it has no DB or attendance calls."""
    production_face_engine.face_engine.initialize()
    return production_face_engine.face_engine


def classify_pose(face):
    pose = face.get("head_pose") if isinstance(face, dict) else None
    if not pose:
        return "unknown"
    try:
        yaw, pitch = float(pose["yaw"]), float(pose["pitch"])
    except (KeyError, TypeError, ValueError):
        return "unknown"
    if not np.isfinite(yaw) or not np.isfinite(pitch):
        return "unknown"

    yaw_abs, pitch_abs = abs(yaw), abs(pitch)
    if yaw_abs <= POSE_FRONTAL_YAW_MAX_DEG and pitch_abs <= POSE_FRONTAL_PITCH_MAX_DEG:
        return "frontal"
    # Positive yaw is the person's left and negative yaw is their right in the
    # existing solvePnP convention (verified against the current AI1 pose tests).
    if (POSE_SIDE_YAW_MIN_DEG <= yaw <= POSE_SIDE_YAW_MAX_DEG
            and pitch_abs <= POSE_SIDE_PITCH_MAX_DEG):
        return "left"
    if (-POSE_SIDE_YAW_MAX_DEG <= yaw <= -POSE_SIDE_YAW_MIN_DEG
            and pitch_abs <= POSE_SIDE_PITCH_MAX_DEG):
        return "right"
    if (POSE_VERTICAL_PITCH_MIN_DEG <= pitch <= POSE_VERTICAL_PITCH_MAX_DEG
            and yaw_abs <= POSE_VERTICAL_YAW_MAX_DEG):
        return "up"
    if (-POSE_VERTICAL_PITCH_MAX_DEG <= pitch <= -POSE_VERTICAL_PITCH_MIN_DEG
            and yaw_abs <= POSE_VERTICAL_YAW_MAX_DEG):
        return "down"
    return "between"


def classify_enrollment_pose(face, expected_pose):
    """Apply a small expected-pose hysteresis band to absorb solvePnP jitter."""
    current = classify_pose(face)
    if current == expected_pose or expected_pose not in {"frontal", "left", "right", "up", "down"}:
        return current
    pose = face.get("head_pose") if isinstance(face, dict) else None
    if not pose:
        return current
    try:
        yaw, pitch = float(pose["yaw"]), float(pose["pitch"])
    except (KeyError, TypeError, ValueError):
        return current
    if not np.isfinite(yaw) or not np.isfinite(pitch):
        return current

    margin = POSE_ENROLLMENT_HYSTERESIS_DEG
    yaw_abs, pitch_abs = abs(yaw), abs(pitch)
    if (expected_pose == "frontal"
            and yaw_abs <= POSE_FRONTAL_YAW_MAX_DEG + margin
            and pitch_abs <= POSE_FRONTAL_PITCH_MAX_DEG + margin):
        return "frontal"
    if (expected_pose == "left"
            and max(0.0, POSE_SIDE_YAW_MIN_DEG - margin) <= yaw <= POSE_SIDE_YAW_MAX_DEG + margin
            and pitch_abs <= POSE_SIDE_PITCH_MAX_DEG + margin):
        return "left"
    if (expected_pose == "right"
            and -POSE_SIDE_YAW_MAX_DEG - margin <= yaw <= -max(0.0, POSE_SIDE_YAW_MIN_DEG - margin)
            and pitch_abs <= POSE_SIDE_PITCH_MAX_DEG + margin):
        return "right"
    if (expected_pose == "up"
            and max(0.0, POSE_VERTICAL_PITCH_MIN_DEG - margin) <= pitch <= POSE_VERTICAL_PITCH_MAX_DEG + margin
            and yaw_abs <= POSE_VERTICAL_YAW_MAX_DEG + margin):
        return "up"
    if (expected_pose == "down"
            and -POSE_VERTICAL_PITCH_MAX_DEG - margin <= pitch <= -max(0.0, POSE_VERTICAL_PITCH_MIN_DEG - margin)
            and yaw_abs <= POSE_VERTICAL_YAW_MAX_DEG + margin):
        return "down"
    return current


def _quality_failure_code(quality, face):
    if face and float(face.get("detection_score", 0.0)) < production_face_engine.ENROLLMENT_MIN_SCORE:
        return "LOW DETECTION SCORE"
    message = str(quality.get("instruction", "")).lower()
    if "quá xa" in message:
        return "FACE TOO SMALL"
    if "quá gần" in message:
        return "FACE TOO LARGE"
    if "toàn bộ" in message or "cắt" in message:
        return "FACE CROPPED"
    if "mép khung" in message:
        return "FACE TOO CLOSE TO EDGE"
    if "ánh sáng" in message:
        return "BAD LIGHTING"
    if "nét" in message or "chưa rõ" in message:
        return "TOO BLURRY"
    if "trung tâm" in message or "giữa" in message or "khung hình" in message:
        return "FACE POSITION"
    return "QUALITY CHECK"


def enrollment_debug_metrics(frame, face, expected_pose, quality=None, face_count=None):
    """Collect per-frame UI diagnostics without logging biometric embeddings."""
    quality = quality if isinstance(quality, dict) else {}
    diagnostics = {
        "detection_score": None,
        "bbox": None,
        "bbox_width_frame_ratio": None,
        "bbox_height_frame_ratio": None,
        "center_offset_x_px": None,
        "center_offset_y_px": None,
        "center_offset_x_ratio": None,
        "center_offset_y_ratio": None,
        "brightness": None,
        "sharpness": None,
        "yaw": None,
        "pitch": None,
        "raw_yaw": None,
        "raw_pitch": None,
        "reprojection_error_px": None,
        "detected_pose": classify_pose(face) if face else "no_face",
        "expected_pose": expected_pose,
        "face_count": face_count,
        "quality_result": "PASS" if quality.get("ready") else "FAIL",
        "quality_code": "PASS" if quality.get("ready") else _quality_failure_code(quality, face),
        "quality_reason": quality.get("instruction"),
    }
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
        return diagnostics

    height, width = frame.shape[:2]
    if not face:
        return diagnostics
    try:
        box = np.asarray(face.get("bbox"), dtype=np.float64).reshape(-1)
        score = float(face.get("detection_score"))
        pose = face.get("head_pose") or {}
        yaw, pitch = float(pose["yaw"]), float(pose["pitch"])
    except (AttributeError, KeyError, TypeError, ValueError):
        box = np.empty(0, dtype=np.float64)
        score, yaw, pitch = None, None, None
    if score is not None and np.isfinite(score):
        diagnostics["detection_score"] = score
    if yaw is not None and np.isfinite(yaw):
        diagnostics["yaw"] = yaw
    if pitch is not None and np.isfinite(pitch):
        diagnostics["pitch"] = pitch
    diagnostics["raw_yaw"] = diagnostics["yaw"]
    diagnostics["raw_pitch"] = diagnostics["pitch"]
    try:
        reprojection_error = float((face.get("head_pose") or {}).get("reprojection_error_px"))
    except (AttributeError, TypeError, ValueError):
        reprojection_error = None
    if reprojection_error is not None and np.isfinite(reprojection_error):
        diagnostics["reprojection_error_px"] = reprojection_error

    if box.size != 4 or not np.all(np.isfinite(box)):
        return diagnostics
    x1, y1, x2, y2 = [float(value) for value in box]
    face_width, face_height = x2 - x1, y2 - y1
    diagnostics["bbox"] = [x1, y1, x2, y2]
    if face_width <= 0 or face_height <= 0:
        return diagnostics
    center_x, center_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    offset_x, offset_y = center_x - width * 0.5, center_y - height * 0.51
    diagnostics.update({
        "bbox_width_frame_ratio": face_width / width,
        "bbox_height_frame_ratio": face_height / height,
        "center_offset_x_px": offset_x,
        "center_offset_y_px": offset_y,
        "center_offset_x_ratio": offset_x / width,
        "center_offset_y_ratio": offset_y / height,
    })
    crop = frame[max(0, int(y1)):min(height, int(np.ceil(y2))),
                 max(0, int(x1)):min(width, int(np.ceil(x2)))]
    if crop.size:
        try:
            gray = cv2.cvtColor(cv2.resize(crop, (128, 160)), cv2.COLOR_BGR2GRAY)
            diagnostics["brightness"] = float(gray.mean())
            diagnostics["sharpness"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        except cv2.error:
            pass
    return diagnostics


def extract_single_face_embedding(engine, frame, *, include_low_confidence=False):
    """Extract one validated, L2-normalized 512D production ArcFace vector."""
    started = time.perf_counter()
    try:
        enrollment_detector = getattr(engine, "detect_enrollment_embeddings", None)
        if include_low_confidence and callable(enrollment_detector):
            faces = enrollment_detector(frame)
        else:
            faces = engine.detect_embeddings(frame)
    except Exception as exc:
        return {"status": "RETRY", "code": "AI ERROR", "reason": str(exc),
                "embedding": None, "face": None,
                "latency_ms": (time.perf_counter() - started) * 1000.0}
    latency = (time.perf_counter() - started) * 1000.0
    if len(faces) == 0:
        return {"status": "RETRY", "code": "NO FACE", "reason": "NO FACE",
                "embedding": None, "face": None, "faces": [], "face_count": 0,
                "latency_ms": latency}
    if len(faces) != 1:
        return {"status": "RETRY", "code": "MULTIPLE FACES", "reason": "MULTIPLE FACES",
                "embedding": None, "face": faces[0], "faces": faces,
                "face_count": len(faces), "latency_ms": latency}
    face = faces[0]
    try:
        detection_score = float(face.get("detection_score"))
        if not np.isfinite(detection_score) or detection_score < production_face_engine.DETECTION_MIN_SCORE:
            return {"status": "RETRY", "code": "LOW DETECTION SCORE",
                    "reason": (f"Detection confidence {detection_score:.3f} is below "
                              f"{production_face_engine.DETECTION_MIN_SCORE:.2f}."),
                    "embedding": None, "face": face, "faces": faces,
                    "face_count": 1, "latency_ms": latency}
        embedding = face_matching.normalize_embedding(face.get("embedding"), EMBEDDING_DIMENSIONS)
    except (TypeError, ValueError) as exc:
        return {"status": "RETRY", "code": "INVALID EMBEDDING", "reason": str(exc),
                "embedding": None, "face": face, "faces": faces,
                "face_count": 1, "latency_ms": latency}
    return {"status": "OK", "code": "OK", "reason": "Valid ArcFace embedding.",
            "embedding": embedding, "face": face, "faces": faces,
            "face_count": 1, "latency_ms": latency}


def validate_enrollment_frame(engine, frame, expected_pose, *, enforce_pose=True):
    """Validate enrollment image quality while keeping pose data diagnostic-only.

    The desktop GUI can disable the pose gate for manual capture because
    solvePnP can be noisy on ordinary webcams. The default keeps the legacy
    pose check for other standalone callers.
    """
    extracted = extract_single_face_embedding(engine, frame, include_low_confidence=True)
    if extracted["status"] != "OK":
        face = extracted.get("face")
        quality = {"ready": False, "instruction": extracted.get("reason", extracted.get("code"))}
        diagnostics = enrollment_debug_metrics(
            frame, face, expected_pose, quality=quality, face_count=extracted.get("face_count")
        )
        diagnostics["quality_code"] = extracted.get("code", "QUALITY CHECK")
        return {**extracted, "expected_pose": expected_pose,
                "detected_pose": classify_pose(face) if face else "no_face",
                "quality": quality, "diagnostics": diagnostics}
    face = extracted["face"]
    quality = production_face_engine.assess_capture_quality(
        frame, face, center_tolerance=ENROLLMENT_CENTER_TOLERANCE,
        max_size_ratio=ENROLLMENT_MAX_SIZE_RATIO,
        edge_margin_ratio=ENROLLMENT_EDGE_MARGIN_RATIO,
    )
    raw_pose = classify_pose(face)
    detected_pose = classify_enrollment_pose(face, expected_pose)
    diagnostics = enrollment_debug_metrics(
        frame, face, expected_pose, quality=quality, face_count=1
    )
    diagnostics["raw_pose_classification"] = raw_pose
    diagnostics["detected_pose"] = detected_pose
    if not quality.get("ready"):
        message = str(quality.get("instruction", "Enrollment image quality failed."))
        code = _quality_failure_code(quality, face)
        diagnostics["quality_code"] = code
        return {**extracted, "status": "RETRY", "code": code, "reason": message,
                "quality": quality, "detected_pose": detected_pose,
                "expected_pose": expected_pose, "diagnostics": diagnostics}
    if enforce_pose and detected_pose != expected_pose:
        pose = face.get("head_pose") or {}
        reason = (f"WRONG POSE: expected {expected_pose}, detected {detected_pose}; "
                  f"yaw={pose.get('yaw', '—')}, pitch={pose.get('pitch', '—')}.")
        diagnostics["quality_code"] = "PASS"
        return {**extracted, "status": "RETRY", "code": "WRONG POSE",
                "reason": reason, "quality": quality, "detected_pose": detected_pose,
                "expected_pose": expected_pose, "diagnostics": diagnostics}
    diagnostics["quality_code"] = "PASS"
    return {**extracted, "reason": "Quality checks passed.", "quality": quality,
            "detected_pose": detected_pose, "expected_pose": expected_pose,
            "diagnostics": diagnostics}


def validate_enrollment_pose_frame(engine, frame, expected_pose):
    """Validate one AUTO tracking frame with SCRFD/quality only, no ArcFace.

    The same strict detection-count, confidence, bounds, centering, size,
    brightness and sharpness gates used for enrollment remain active. The
    selected frame is later passed through ``validate_enrollment_frame`` to
    produce its 512D embedding and repeat those gates before capture.
    """
    started = time.perf_counter()
    try:
        detector = getattr(engine, "detect_pose_faces", None)
        if not callable(detector):
            return {"status": "RETRY", "code": "POSE DETECTOR UNAVAILABLE",
                    "reason": "SCRFD pose-only interface is unavailable; AUTO tracking stopped.",
                    "embedding": None, "face": None, "faces": [], "face_count": 0,
                    "expected_pose": expected_pose,
                    "latency_ms": (time.perf_counter() - started) * 1000.0}
        faces = detector(frame, detection_threshold=production_face_engine.ENROLLMENT_DETECTION_FLOOR)
    except Exception as exc:
        return {"status": "RETRY", "code": "AI ERROR", "reason": str(exc),
                "embedding": None, "face": None, "faces": [], "face_count": 0,
                "expected_pose": expected_pose,
                "latency_ms": (time.perf_counter() - started) * 1000.0}
    latency = (time.perf_counter() - started) * 1000.0
    if len(faces) == 0:
        return {"status": "RETRY", "code": "NO FACE", "reason": "NO FACE",
                "embedding": None, "face": None, "faces": [], "face_count": 0,
                "expected_pose": expected_pose, "latency_ms": latency,
                "diagnostics": {"face_count": 0, "quality_result": "FAIL",
                                "quality_code": "NO FACE"}}
    if len(faces) != 1:
        return {"status": "RETRY", "code": "MULTIPLE FACES",
                "reason": "Chỉ được có đúng một khuôn mặt trong khung.",
                "embedding": None, "face": faces[0], "faces": faces,
                "face_count": len(faces), "expected_pose": expected_pose,
                "latency_ms": latency,
                "diagnostics": {"face_count": len(faces), "quality_result": "FAIL",
                                "quality_code": "MULTIPLE FACES"}}

    face = faces[0]
    quality = production_face_engine.assess_capture_quality(
        frame, face, center_tolerance=ENROLLMENT_CENTER_TOLERANCE,
        max_size_ratio=ENROLLMENT_MAX_SIZE_RATIO,
        edge_margin_ratio=ENROLLMENT_EDGE_MARGIN_RATIO,
    )
    diagnostics = enrollment_debug_metrics(frame, face, expected_pose,
                                           quality=quality, face_count=1)
    diagnostics["quality_code"] = "PASS" if quality.get("ready") else _quality_failure_code(quality, face)
    diagnostics["detected_pose"] = classify_enrollment_pose(face, expected_pose)
    code = "OK" if quality.get("ready") else diagnostics["quality_code"]
    return {
        "status": "OK" if quality.get("ready") else "RETRY",
        "code": code,
        "reason": ("Pose tracking quality checks passed." if quality.get("ready")
                   else str(quality.get("instruction", code))),
        "embedding": None,
        "face": face,
        "faces": faces,
        "face_count": 1,
        "quality": quality,
        "diagnostics": diagnostics,
        "detected_pose": diagnostics["detected_pose"],
        "expected_pose": expected_pose,
        "latency_ms": latency,
    }
