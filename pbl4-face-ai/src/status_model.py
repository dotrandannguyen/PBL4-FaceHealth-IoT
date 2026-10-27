"""Validate the training/inference contract of the single model artifact."""
from .sequence_features import FEATURE_NAMES, FEATURE_SCHEMA, LABELS, SNAPSHOT_INTERVAL, MAX_SNAPSHOT_GAP


def load_status_model(path):
    import joblib
    import sklearn
    artifact = joblib.load(path)
    if not isinstance(artifact, dict) or artifact.get('format') != 'pbl4-status-rf' or artifact.get('format_version') != 1:
        raise ValueError('Model cũ thiếu contract metadata. Giữ file cũ và train artifact mới bằng dataset v2.')
    model, metadata = artifact.get('model'), artifact.get('metadata')
    if (not isinstance(metadata, dict) or metadata.get('feature_schema') != FEATURE_SCHEMA
            or metadata.get('feature_names') != FEATURE_NAMES or metadata.get('snapshot_count') != 3
            or metadata.get('interval_ms') != SNAPSHOT_INTERVAL*1000 or metadata.get('max_gap_ms') != MAX_SNAPSHOT_GAP*1000
            or metadata.get('label_source') != 'operator_manual'
            or metadata.get('versions',{}).get('sklearn') != sklearn.__version__
            or getattr(model,'n_features_in_',None) != len(FEATURE_NAMES)
            or list(getattr(model,'classes_',[])) != metadata.get('classes')
            or set(metadata.get('classes',[])) != set(LABELS)
            or not callable(getattr(model,'predict_proba',None))):
        raise ValueError('Model không tương thích feature/timing/classes/scikit-learn; cần train lại với môi trường hiện tại.')
    return model, metadata
