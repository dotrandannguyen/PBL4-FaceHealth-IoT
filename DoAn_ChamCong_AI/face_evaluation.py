"""Threshold evaluation helpers for genuine and impostor cosine scores."""

import numpy as np


def _find_equal_error_point(thresholds, far, frr):
    differences = far - frr
    crossing = np.flatnonzero(differences[:-1] * differences[1:] <= 0)

    if not crossing.size:
        index = int(np.argmin(np.abs(differences)))
        return float(thresholds[index]), float((far[index] + frr[index]) / 2)

    index = int(crossing[0])
    left_diff, right_diff = differences[index:index + 2]
    if right_diff == left_diff:
        threshold = float((thresholds[index] + thresholds[index + 1]) / 2)
    else:
        fraction = float(-left_diff / (right_diff - left_diff))
        threshold = float(thresholds[index] + fraction * (thresholds[index + 1] - thresholds[index]))
    eer = float((np.interp(threshold, thresholds, far) + np.interp(threshold, thresholds, frr)) / 2)
    return threshold, eer


def evaluate_scores(genuine_scores, impostor_scores, thresholds=None):
    genuine = np.asarray(genuine_scores, dtype=np.float64).reshape(-1)
    impostor = np.asarray(impostor_scores, dtype=np.float64).reshape(-1)
    if genuine.size == 0 or impostor.size == 0:
        raise ValueError("Evaluation requires genuine and impostor scores.")
    if not np.all(np.isfinite(genuine)) or not np.all(np.isfinite(impostor)):
        raise ValueError("Scores must be finite numbers.")
    if np.any(genuine < -1) or np.any(genuine > 1) or np.any(impostor < -1) or np.any(impostor > 1):
        raise ValueError("Cosine scores must be between -1 and 1.")

    if thresholds is None:
        thresholds = np.linspace(-1.0, 1.0, 2001, dtype=np.float64)
    thresholds = np.asarray(thresholds, dtype=np.float64).reshape(-1)
    if thresholds.size == 0 or not np.all(np.isfinite(thresholds)):
        raise ValueError("At least one finite threshold is required.")

    far = np.asarray([np.mean(impostor >= threshold) for threshold in thresholds])
    frr = np.asarray([np.mean(genuine < threshold) for threshold in thresholds])
    threshold, eer = _find_equal_error_point(thresholds, far, frr)

    operating_index = int(np.argmin(np.abs(thresholds - threshold)))
    return {
        "genuine_count": int(genuine.size),
        "impostor_count": int(impostor.size),
        "genuine_mean": float(np.mean(genuine)),
        "impostor_mean": float(np.mean(impostor)),
        "threshold": threshold,
        "far": float(far[operating_index]),
        "frr": float(frr[operating_index]),
        "eer": eer,
        "thresholds": thresholds,
        "far_curve": far,
        "frr_curve": frr,
    }
