"""Face embedding validation, gallery aggregation, and cosine matching."""

from collections import defaultdict

import numpy as np


EMBEDDING_DIMENSIONS = 512
ENROLLMENT_IDENTITY_THRESHOLD = 0.45


def normalize_embedding(value, dimensions=EMBEDDING_DIMENSIONS):
    """Validate an embedding's shape and return its L2-normalized float32 vector."""
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
    """Decode a stored little-endian float32 vector after checking its dimension/size."""
    if int(dimensions or 0) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Unsupported stored embedding dimension: {dimensions}.")
    raw = bytes(vector_data)
    expected_bytes = EMBEDDING_DIMENSIONS * np.dtype("<f4").itemsize
    if len(raw) != expected_bytes:
        raise ValueError(f"Expected {expected_bytes} bytes, received {len(raw)}.")
    return normalize_embedding(np.frombuffer(raw, dtype="<f4"))


def cosine_similarity(first, second):
    """Compute cosine similarity after normalizing both input vectors."""
    left = normalize_embedding(first)
    right = normalize_embedding(second)
    return float(np.clip(np.dot(left, right), -1.0, 1.0))


def max_sample_similarity(probe, samples):
    """Return the highest cosine score across one person's original samples."""
    if not samples:
        raise ValueError("At least one face sample is required.")
    probe_vector = normalize_embedding(probe)
    return max(float(np.clip(np.dot(probe_vector, normalize_embedding(sample)), -1.0, 1.0))
               for sample in samples)


def aggregate_gallery(rows):
    """Keep every valid FaceEmbedding sample for multi-sample matching."""
    grouped = defaultdict(list)
    names = {}
    invalid_rows = []

    for row in rows:
        embedding_id, ma_nv, vector_data, dimensions, ho_ten = row
        try:
            employee_id = int(ma_nv)
            vector = decode_stored_embedding(vector_data, dimensions)
            name = str(ho_ten or "")
            if employee_id in names and names[employee_id] != name:
                raise ValueError("Inconsistent employee name in face gallery.")
            grouped[employee_id].append(vector)
            names[employee_id] = name
        except (TypeError, ValueError, OverflowError) as exc:
            invalid_rows.append({"MaEmbedding": embedding_id, "error": str(exc)})

    gallery = {
        ma_nv: {"HoTen": names[ma_nv], "embeddings": tuple(vectors), "n_samples": len(vectors)}
        for ma_nv, vectors in grouped.items()
    }
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
    """
    Match a probe against every enrolled sample and return the best person.

    A below-threshold best candidate is reported as UNKNOWN with no MaNV identity.
    """
    threshold = _validate_threshold(threshold)
    probe_vector = normalize_embedding(probe)
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
        samples = person["embeddings"]
        if not samples:
            continue
        score = max_sample_similarity(probe_vector, samples)
        if score > best_score:
            best_ma_nv = ma_nv
            best_score = score

    if best_ma_nv is None:
        return {"status": "UNKNOWN", "match": False, "MaNV": None,
                "HoTen": "UNKNOWN", "similarity": None, "threshold": threshold}

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
    """Verify against the best of a MaNV's enrollment samples."""
    threshold = _validate_threshold(threshold)
    probe_vector = normalize_embedding(probe)
    try:
        target_id = int(ma_nv)
    except (TypeError, ValueError) as exc:
        raise ValueError("MaNV must be an integer.") from exc

    target = gallery.get(target_id)
    if target is None or not target["embeddings"]:
        return {
            "status": "NOT_ENROLLED",
            "match": False,
            "MaNV": None,
            "HoTen": "UNKNOWN",
            "targetMaNV": target_id,
            "similarity": None,
            "threshold": threshold,
        }

    score = max_sample_similarity(probe_vector, target["embeddings"])
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
