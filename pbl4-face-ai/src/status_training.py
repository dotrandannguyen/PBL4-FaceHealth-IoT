"""Train from one immutable dataset snapshot, with no row-wise split fallback."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import math
from pathlib import Path
import platform
import random

from .atomic_storage import atomic_write
from .sequence_features import FEATURE_NAMES, FEATURE_SCHEMA, LABELS, SNAPSHOT_INTERVAL, MAX_SNAPSHOT_GAP
from .status_dataset import decode_dataset
from .gallery_store import gallery_lock as artifact_lock


def split_rows(rows, mode='subject', seed=42, test_size=.2):
    if mode not in ('subject', 'session') or not 0 < test_size < .5:
        raise ValueError('Split must hold out subjects/sessions with 0 < test_size < .5')
    if len(rows) < 18 or set(row['label'] for row in rows) != set(LABELS):
        raise ValueError('Cần ít nhất 18 chuỗi hợp lệ và đủ ba nhãn')
    key = 'subject_id' if mode == 'subject' else 'session_id'
    groups = sorted({row[key] for row in rows})
    if len(groups) < 2:
        raise ValueError('Cần ít nhất hai người độc lập; --split session chỉ đánh giá phiên khác của cùng người')
    count = max(1, min(len(groups)-1, math.ceil(len(groups)*test_size)))
    rng = random.Random(seed)
    best = None
    seen = set()
    for _ in range(512):
        test_groups = frozenset(rng.sample(groups, count))
        if test_groups in seen:
            continue
        seen.add(test_groups)
        train = [i for i,row in enumerate(rows) if row[key] not in test_groups]
        test = [i for i,row in enumerate(rows) if row[key] in test_groups]
        train_counts = Counter(rows[i]['label'] for i in train)
        test_counts = Counter(rows[i]['label'] for i in test)
        if any(train_counts[label] < 2 or test_counts[label] < 1 for label in LABELS):
            continue
        score = abs(len(test)/len(rows) - test_size) + sum(abs(test_counts[label]/len(test) -
                    sum(row['label']==label for row in rows)/len(rows)) for label in LABELS)
        candidate = (score, tuple(sorted(test_groups)), train, test)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        raise ValueError('Không có split nhóm đủ ba nhãn ở cả train/test; cần thu thêm người/phiên có đủ nhãn')
    return best[2], best[3]


def train(dataset_path, model_path, *, split='subject', seed=42, test_size=.2):
    with artifact_lock(model_path):
        return _train(dataset_path, model_path, split=split, seed=seed, test_size=test_size)


def _train(dataset_path, model_path, *, split, seed, test_size):
    import joblib
    import numpy as np
    import sklearn
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, confusion_matrix, classification_report
    dataset_path, model_path = Path(dataset_path), Path(model_path)
    if dataset_path.resolve() == model_path.resolve():
        raise ValueError('Model output cannot overwrite the dataset')
    raw = dataset_path.read_bytes()
    rows = decode_dataset(raw)
    train_index, test_index = split_rows(rows, split, seed, test_size)
    X = np.array([[row[name] for name in FEATURE_NAMES] for row in rows], dtype=np.float64)
    y = np.array([row['label'] for row in rows])
    model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=seed, n_jobs=1)
    model.fit(X[train_index], y[train_index])
    predicted = model.predict(X[test_index])
    def values(indices, key):
        return sorted({rows[i][key] for i in indices})
    metadata = dict(trained_at=datetime.now(timezone.utc).isoformat(), dataset_sha256=hashlib.sha256(raw).hexdigest(),
        feature_schema=FEATURE_SCHEMA, feature_names=list(FEATURE_NAMES), classes=list(model.classes_),
        snapshot_count=3, interval_ms=SNAPSHOT_INTERVAL*1000, max_gap_ms=MAX_SNAPSHOT_GAP*1000,
        label_source='operator_manual', evaluation_scope='held_out_subjects' if split=='subject' else 'held_out_sessions_not_new_people',
        split=split, random_seed=seed, requested_test_size=test_size, train_rows=len(train_index), test_rows=len(test_index),
        train_subjects=values(train_index,'subject_id'), test_subjects=values(test_index,'subject_id'),
        train_sessions=values(train_index,'session_id'), test_sessions=values(test_index,'session_id'),
        train_class_counts=dict(Counter(y[train_index])), test_class_counts=dict(Counter(y[test_index])),
        accuracy=float(accuracy_score(y[test_index],predicted)), balanced_accuracy=float(balanced_accuracy_score(y[test_index],predicted)),
        macro_f1=float(f1_score(y[test_index],predicted,labels=list(LABELS),average='macro',zero_division=0)),
        confusion_matrix=confusion_matrix(y[test_index],predicted,labels=list(LABELS)).tolist(),
        confusion_matrix_labels=list(LABELS), report=classification_report(y[test_index],predicted,labels=list(LABELS),output_dict=True,zero_division=0),
        versions=dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__,joblib=joblib.__version__),
        model_parameters=model.get_params())
    artifact = dict(format='pbl4-status-rf', format_version=1, model=model, metadata=metadata)
    # Metadata and model become visible together; no second sidecar write.
    buffer = io.BytesIO()
    joblib.dump(artifact, buffer, compress=3)
    atomic_write(model_path, buffer.getvalue())
    return metadata
