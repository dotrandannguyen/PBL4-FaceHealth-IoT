"""Face embedding validation, gallery aggregation, and cosine matching."""

from collections import defaultdict

import numpy as np


EMBEDDING_DIMENSIONS = 512


def normalize_embedding(value, dimensions=EMBEDDING_DIMENSIONS):
    vector = np.asarray(value, dtype=np.float32).reshape(-1)
    if vector.size != dimensions:
        raise ValueError(f"Expected {dimensions} dimensions, received {vector.size}.")
    if not np.all(np.isfinite(vector)):
        raise ValueError("Embedding contains non-finite values.")
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError("Embedding has zero norm.")
    return np.asarray(vector / norm, dtype=np.float32)


def decode_stored_embedding(vector_data, dimensions):
    if int(dimensions or 0) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Unsupported stored embedding dimension: {dimensions}.")
    raw = bytes(vector_data)
    expected_bytes = EMBEDDING_DIMENSIONS * np.dtype("<f4").itemsize
    if len(raw) != expected_bytes:
        raise ValueError(f"Expected {expected_bytes} bytes, received {len(raw)}.")
    return normalize_embedding(np.frombuffer(raw, dtype="<f4"))


def cosine_similarity(first, second):
    left = normalize_embedding(first)
    right = normalize_embedding(second)
    return float(np.clip(np.dot(left, right), -1.0, 1.0))


def aggregate_gallery(rows):
    """Decode FaceEmbedding rows and make one normalized centroid per employee."""
    grouped = defaultdict(list)
    names = {}
    invalid_rows = []

    for row in rows:
        embedding_id, ma_nv, vector_data, dimensions, ho_ten = row
        try:
            grouped[int(ma_nv)].append(decode_stored_embedding(vector_data, dimensions))
            names[int(ma_nv)] = str(ho_ten or "")
        except (TypeError, ValueError, OverflowError) as exc:
            invalid_rows.append({"MaEmbedding": embedding_id, "error": str(exc)})

    gallery = {}
    for ma_nv, vectors in grouped.items():
        centroid = normalize_embedding(np.mean(np.stack(vectors), axis=0))
        gallery[ma_nv] = {"HoTen": names[ma_nv], "embedding": centroid}
    return gallery, invalid_rows


def _validate_threshold(threshold):
    try:
        value = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("Threshold must be a number between -1 and 1.") from exc
    if not np.isfinite(value) or value < -1.0 or value > 1.0:
        raise ValueError("Threshold must be a number between -1 and 1.")
    return value


def identify_embedding(probe, gallery, threshold):
    threshold = _validate_threshold(threshold)
    if not gallery:
        return {
            "status": "UNKNOWN",
            "match": False,
            "MaNV": None,
            "HoTen": "UNKNOWN",
            "similarity": None,
            "threshold": threshold,
        }

    best_ma_nv = None
    best_score = -1.0
    for ma_nv, person in gallery.items():
        score = cosine_similarity(probe, person["embedding"])
        if score > best_score:
            best_ma_nv = ma_nv
            best_score = score

    matched = best_score >= threshold
    person = gallery[best_ma_nv]
    return {
        "status": "MATCH" if matched else "UNKNOWN",
        "match": matched,
        "MaNV": best_ma_nv if matched else None,
        "HoTen": person["HoTen"] if matched else "UNKNOWN",
        "similarity": best_score,
        "threshold": threshold,
    }


def verify_embedding(probe, ma_nv, gallery, threshold):
    threshold = _validate_threshold(threshold)
    try:
        target_id = int(ma_nv)
    except (TypeError, ValueError) as exc:
        raise ValueError("MaNV must be an integer.") from exc

    target = gallery.get(target_id)
    if target is None:
        return {
            "status": "NOT_ENROLLED",
            "match": False,
            "MaNV": None,
            "HoTen": "UNKNOWN",
            "targetMaNV": target_id,
            "similarity": None,
            "threshold": threshold,
        }

    score = cosine_similarity(probe, target["embedding"])
    matched = score >= threshold
    return {
        "status": "MATCH" if matched else "NO_MATCH",
        "match": matched,
        "MaNV": target_id if matched else None,
        "HoTen": target["HoTen"] if matched else "UNKNOWN",
        "targetMaNV": target_id,
        "targetHoTen": target["HoTen"],
        "similarity": score,
        "threshold": threshold,
    }
