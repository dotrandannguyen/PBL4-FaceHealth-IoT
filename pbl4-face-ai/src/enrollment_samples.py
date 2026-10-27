"""Validate paired enrollment samples without loading an inference model."""
import io
import math
import os

from .enrollment_pose import POSES, estimate_pose, check_pose_match


def normalize(vector):
    import numpy as np
    value = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(value))
    if value.shape != (512,) or not np.isfinite(value).all() or not math.isfinite(norm) or norm <= 0:
        raise ValueError('Invalid 512D face vector')
    return (value / norm).astype('<f4')


def same_identity(reference, vector):
    import numpy as np
    threshold = float(os.environ.get('PBL4_ENROLLMENT_THRESHOLD', '.45'))
    if not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError('Invalid enrollment threshold')
    if float(np.dot(normalize(reference), normalize(vector))) < threshold:
        raise ValueError('Khuôn mặt không khớp mẫu đầu tiên')


def sample_from_frame(frame, faces, expected_pose, reference=None):
    if len(faces) != 1:
        raise ValueError('Chỉ cho phép một khuôn mặt')
    face = faces[0]
    pose, metrics = estimate_pose(face.kps)
    if not check_pose_match(expected_pose, pose, metrics):
        raise ValueError('Giữ đúng hướng: ' + expected_pose)
    vector = normalize(face.embedding)  # Same detection as the pose check.
    if reference is not None:
        same_identity(reference, vector)
    import cv2
    ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise ValueError('Không mã hóa được ảnh')
    return {'pose': pose, 'vector': vector, 'image': encoded.tobytes()}


def prepare_samples(samples):
    from PIL import Image
    if len(samples) != 5:
        raise ValueError('Cần đủ năm mẫu theo thứ tự frontal/left/right/up/down')
    prepared = []
    for pose, sample in zip(POSES, samples):
        if sample.get('pose') != pose:
            raise ValueError('Sai thứ tự năm tư thế')
        vector = normalize(sample['vector'])
        if prepared:
            same_identity(prepared[0]['vector'], vector)
        image = sample.get('image')
        if not isinstance(image, bytes) or not 0 < len(image) <= 5 * 1024 * 1024:
            raise ValueError('Invalid enrollment image')
        try:
            with Image.open(io.BytesIO(image)) as source:
                if source.format not in ('JPEG', 'PNG') or source.width * source.height > 16000000:
                    raise ValueError('Invalid enrollment image format/dimensions')
                mime = 'image/jpeg' if source.format == 'JPEG' else 'image/png'
                source.verify()
        except Exception as exc:
            raise ValueError('Invalid enrollment image') from exc
        prepared.append(dict(pose=pose, vector=vector, image=image, mime=mime))
    return prepared
