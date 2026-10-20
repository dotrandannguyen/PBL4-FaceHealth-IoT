"""Shared feature contract for collection, training and inference."""

import math

SNAPSHOT_INTERVAL = 0.30
MAX_SNAPSHOT_GAP = 0.60
FEATURE_SCHEMA = 'status_sequence_v2'
LABELS = ('Normal', 'Fatigue', 'Exhausted')
FEATURE_NAMES = [
    "min_ear", "mean_ear", "max_mar", "mean_mar",
    "delta_pitch", "delta_roll", "mean_pitch",
]


def usable_observation(features, max_yaw=25.0, max_pitch=35.0):
    try:
        if any(isinstance(features[key], bool) for key in ('ear', 'mar', 'pitch', 'yaw', 'roll')):
            return None
        values = {key: float(features[key]) for key in ('ear', 'mar', 'pitch', 'yaw', 'roll')}
    except (TypeError, KeyError, ValueError):
        return None
    if (not all(math.isfinite(x) for x in values.values()) or values['ear'] < 0 or values['mar'] < 0
            or abs(values['yaw']) > max_yaw or abs(abs(values['pitch']) - 180) > max_pitch):
        return None
    return values


def _angles(values, center=0):
    wrapped = [((value - center + 180) % 360) - 180 for value in values]
    unwrapped = [wrapped[0]]
    for value in wrapped[1:]:
        unwrapped.append(unwrapped[-1] + ((value - unwrapped[-1] + 180) % 360) - 180)
    return unwrapped


def calculate_sequence_features(features):
    if not isinstance(features, (list, tuple)) or len(features) != 3:
        return None
    try:
        if any(isinstance(f[k], bool) for f in features for k in ('ear', 'mar', 'pitch', 'roll')):
            return None
        values = [[float(f[k]) for f in features] for k in ("ear", "mar", "pitch", "roll")]
    except (TypeError, KeyError, ValueError):
        return None
    if not all(math.isfinite(x) for group in values for x in group):
        return None
    ears, mars, pitches, rolls = values
    if min(ears) < 0 or min(mars) < 0:
        return None
    pitches, rolls = _angles(pitches, 180), _angles(rolls)
    result = [min(ears), sum(ears) / 3, max(mars), sum(mars) / 3,
              max(pitches) - min(pitches), max(rolls) - min(rolls), sum(pitches) / 3]
    return result if all(math.isfinite(value) for value in result) else None
