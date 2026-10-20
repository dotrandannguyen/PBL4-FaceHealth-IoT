"""Versioned observations, durable collection, and group-safe dataset handling."""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
from uuid import UUID, uuid4

from .atomic_storage import atomic_write
from .gallery_store import gallery_lock as artifact_lock
from .sequence_features import (FEATURE_NAMES, FEATURE_SCHEMA, LABELS, SNAPSHOT_INTERVAL,
                                MAX_SNAPSHOT_GAP, calculate_sequence_features, usable_observation)

COLUMNS = FEATURE_NAMES + ['label', 'subject_id', 'session_id', 'sequence_id', 'captured_at',
                          'interval_ms', 'gap_1_ms', 'gap_2_ms', 'feature_schema', 'label_source']


def subject_id(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value)
            or value.casefold() in ('anonymous', 'legacy', 'unknown', 'none', 'nan')):
        raise ValueError('Cần mã người ổn định (1–64 ký tự), không dùng anonymous/legacy')
    return value


def _uuid(value):
    result = UUID(str(value))
    if result.version != 4 or str(result) != value:
        raise ValueError('Invalid observation UUID')


def validate_row(row):
    if set(row) != set(COLUMNS):
        raise ValueError('Dataset không đúng schema; giữ dữ liệu cũ và thu vào file v2 riêng')
    result = dict(row)
    for key in FEATURE_NAMES + ['interval_ms', 'gap_1_ms', 'gap_2_ms']:
        if isinstance(row[key], bool):
            raise ValueError('Boolean feature is invalid')
        value = float(row[key])
        if not math.isfinite(value):
            raise ValueError('Dataset contains missing/non-finite features')
        result[key] = value
    if (result['min_ear'] < 0 or result['min_ear'] > result['mean_ear'] + 1e-9
            or result['mean_mar'] < 0 or result['mean_mar'] > result['max_mar'] + 1e-9
            or result['delta_pitch'] < 0 or result['delta_roll'] < 0 or abs(result['mean_pitch']) > 35 + 1e-9):
        raise ValueError('Inconsistent observation features')
    if row['feature_schema'] != FEATURE_SCHEMA or row['label'] not in LABELS or row['label_source'] != 'operator_manual':
        raise ValueError('Unsupported feature/label contract')
    if abs(result['interval_ms'] - SNAPSHOT_INTERVAL * 1000) > 1e-6:
        raise ValueError('Snapshot interval does not match inference')
    for key in ('gap_1_ms', 'gap_2_ms'):
        if not SNAPSHOT_INTERVAL * 1000 - 1e-6 <= result[key] <= MAX_SNAPSHOT_GAP * 1000 + 1e-6:
            raise ValueError('Observation gap does not match inference')
    subject_id(row['subject_id'])
    _uuid(row['session_id'])
    _uuid(row['sequence_id'])
    instant = datetime.fromisoformat(row['captured_at'])
    if instant.utcoffset() is None:
        raise ValueError('Capture timestamp requires timezone')
    result['captured_at'] = instant.astimezone(timezone.utc).isoformat()
    return result


def decode_dataset(raw):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    if reader.fieldnames != COLUMNS:
        raise ValueError('Dataset schema/order is invalid; legacy data is not independent training data')
    rows, sequences, sessions = [], set(), {}
    for row in reader:
        row = validate_row(row)
        if row['sequence_id'] in sequences:
            raise ValueError('Duplicate sequence_id in dataset')
        owner = sessions.setdefault(row['session_id'], row['subject_id'])
        if owner != row['subject_id']:
            raise ValueError('One session cannot belong to multiple subjects')
        rows.append(row)
        sequences.add(row['sequence_id'])
    return rows


def encode_dataset(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


class StatusDataset:
    def __init__(self, path):
        self.path = Path(path)
        self.pending = self.path.with_name(self.path.stem + '.pending')

    def inspect(self):
        return decode_dataset(self.path.read_bytes()) if self.path.exists() else []

    def _merge(self, row):
        with artifact_lock(self.path):
            rows = self.inspect()
            existing = next((saved for saved in rows if saved['sequence_id'] == row['sequence_id']), None)
            if existing is not None:
                if existing != row:
                    raise ValueError('Sequence replay has different contents')
                return
            # Validate session ownership across old and new rows before replacement.
            payload = encode_dataset(rows + [row])
            decode_dataset(payload)
            atomic_write(self.path, payload)

    def record(self, row):
        row = validate_row(row)
        path = self.pending / (row['sequence_id'] + '.json')
        with artifact_lock(path):
            payload = json.dumps(row, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if path.exists() and path.read_bytes() != payload:
                raise ValueError('Pending observation conflict')
            atomic_write(path, payload)
            self._merge(row)
            path.unlink()

    def recover(self):
        count = 0
        for path in sorted(self.pending.glob('*.json')):
            with artifact_lock(path):
                if not path.exists():  # Another collector already merged this journal.
                    continue
                row = validate_row(json.loads(path.read_text(encoding='utf-8')))
                if path.stem != row['sequence_id']:
                    raise ValueError('Pending observation filename mismatch')
                self._merge(row)
                path.unlink()
                count += 1
        return count


class SequenceCollector:
    def __init__(self, subject, session_id=None):
        self.subject = subject_id(subject)
        self.session = session_id or str(uuid4())
        _uuid(self.session)
        self.cancel()

    def cancel(self):
        self.label, self.features, self.times = None, [], []

    def start(self, label):
        if label not in LABELS:
            raise ValueError('Unsupported label')
        self.cancel()
        self.label = label
        self.sequence = str(uuid4())

    def observe(self, features, now, captured_at=None):
        if self.label is None:
            return None
        values = usable_observation(features)
        if values is None or not math.isfinite(now) or (self.times and now < self.times[-1]):
            self.cancel()
            return None
        if self.times:
            gap = now - self.times[-1]
            if gap > MAX_SNAPSHOT_GAP + 1e-9:
                self.cancel()
                return None
            if gap < SNAPSHOT_INTERVAL - 1e-9:
                return None
        else:
            self.captured_at = captured_at or datetime.now(timezone.utc).isoformat()
        self.features.append(values)
        self.times.append(now)
        if len(self.features) < 3:
            return None
        vector = calculate_sequence_features(self.features)
        if vector is None:
            self.cancel()
            return None
        row = dict(zip(FEATURE_NAMES, vector))
        row.update(label=self.label, subject_id=self.subject, session_id=self.session, sequence_id=self.sequence,
                   captured_at=self.captured_at, interval_ms=SNAPSHOT_INTERVAL * 1000,
                   gap_1_ms=(self.times[1]-self.times[0])*1000, gap_2_ms=(self.times[2]-self.times[1])*1000,
                   feature_schema=FEATURE_SCHEMA, label_source='operator_manual')
        self.cancel()
        return validate_row(row)
