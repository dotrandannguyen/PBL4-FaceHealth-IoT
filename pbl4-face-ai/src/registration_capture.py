"""Registration preview validation, independent of Tk and model loading.

The guide uses normalized image coordinates so the same checks apply to every
camera resolution. Saved samples still use the existing enrollment sample API.
"""
from dataclasses import dataclass
import base64
import io
import math

import cv2
import numpy as np

from .enrollment_pose import estimate_pose, check_pose_match


@dataclass(frozen=True)
class CaptureReadiness:
    ready: bool
    message: str
    short_message: str
    bbox: tuple | None = None
    pose: str | None = None
    sharpness: float = 0.0
    brightness: float = 0.0


def guide_bounds(shape):
    """Centered portrait guide, with room for small left/right head turns."""
    height, width = shape[:2]
    guide_height = min(height * .72, width * .86)
    guide_width = guide_height * .78
    center_x, center_y = width * .5, height * .51
    return (int(center_x - guide_width / 2), int(center_y - guide_height / 2),
            int(center_x + guide_width / 2), int(center_y + guide_height / 2))


def assess_frame(frame, faces, expected_pose=None):
    """Gate auto and manual capture on one aligned, usable, expected-pose face."""
    if len(faces) != 1:
        return CaptureReadiness(False,
            'Đưa khuôn mặt vào giữa khung hướng dẫn.' if not faces else
            'Chỉ để một người trong khung hình.',
            'No face - move into guide' if not faces else 'One person only')
    height, width = frame.shape[:2]
    face = faces[0]
    try:
        box = tuple(float(value) for value in face.bbox)
        if len(box) != 4 or not all(math.isfinite(value) for value in box):
            raise ValueError('Invalid face box')
        x1, y1, x2, y2 = box
        if x2 <= x1 or y2 <= y1:
            raise ValueError('Empty face box')
        score = float(getattr(face, 'det_score', 1.0))
        if not math.isfinite(score) or score < .65:
            return CaptureReadiness(False, 'Khuôn mặt chưa rõ. Nhìn vào camera và tăng ánh sáng.',
                                    'Face detection uncertain', box)
        gx1, gy1, gx2, gy2 = guide_bounds(frame.shape)
        guide_width, guide_height = gx2 - gx1, gy2 - gy1
        face_width, face_height = x2 - x1, y2 - y1
        if face_width < guide_width * .48 or face_height < guide_height * .5:
            return CaptureReadiness(False, 'Mặt quá xa. Tiến gần camera hơn.', 'Move closer', box)
        if face_width > guide_width * 1.15 or face_height > guide_height * 1.08:
            return CaptureReadiness(False, 'Mặt quá gần. Lùi nhẹ để thấy toàn bộ khuôn mặt.',
                                    'Move back', box)
        dx = abs((x1 + x2) / 2 - (gx1 + gx2) / 2) / guide_width
        dy = abs((y1 + y2) / 2 - (gy1 + gy2) / 2) / guide_height
        if (dx > .18 or dy > .16 or x1 < 0 or y1 < 0 or x2 > width or y2 > height):
            return CaptureReadiness(False, 'Đặt khuôn mặt ở chính giữa khung hướng dẫn.',
                                    'Center your face', box)
        crop = frame[max(0, int(y1)):min(height, int(y2)),
                     max(0, int(x1)):min(width, int(x2))]
        if not crop.size:
            raise ValueError('Empty face crop')
        # Normalize the quality check so high-resolution inputs do not get an
        # unfair advantage and work remains bounded on the preview thread.
        gray = cv2.cvtColor(cv2.resize(crop, (128, 160)), cv2.COLOR_BGR2GRAY)
        sharpness, brightness = float(cv2.Laplacian(gray, cv2.CV_64F).var()), float(gray.mean())
        if brightness < 40 or brightness > 225:
            return CaptureReadiness(False, 'Ánh sáng chưa phù hợp. Chiếu sáng đều khuôn mặt.',
                                    'Adjust face lighting', box, sharpness=sharpness, brightness=brightness)
        if sharpness < 20:
            return CaptureReadiness(False, 'Ảnh chưa rõ. Giữ yên và kiểm tra nét camera.',
                                    'Hold still - image blurred', box,
                                    sharpness=sharpness, brightness=brightness)
        pose, metrics = estimate_pose(face.kps)
        if expected_pose is not None and not check_pose_match(expected_pose, pose, metrics):
            return CaptureReadiness(False, 'Hãy làm theo hướng dẫn góc mặt rồi giữ yên.',
                                    'Follow the requested pose', box, pose, sharpness, brightness)
        return CaptureReadiness(True, 'Vị trí hợp lệ. Giữ yên để chụp tự động.',
                                'Ready - hold still', box, pose, sharpness, brightness)
    except (ValueError, TypeError, AttributeError, cv2.error):
        return CaptureReadiness(False, 'Chưa trích xuất được khuôn mặt rõ nét.',
                                'Face landmarks unavailable')


def render_guide(frame, faces, readiness, step_text='', stability=0.0):
    """Draw overlays only; callers own all widget and capture state updates."""
    canvas = frame.copy()
    height, width = canvas.shape[:2]
    x1, y1, x2, y2 = guide_bounds(frame.shape)
    color = (90, 220, 80) if readiness.ready else (70, 70, 245)
    center, axes = ((x1 + x2) // 2, (y1 + y2) // 2), ((x2 - x1) // 2, (y2 - y1) // 2)
    shade = canvas.copy()
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
    shade[mask == 0] = (shade[mask == 0] * .48).astype(np.uint8)
    cv2.ellipse(shade, center, axes, 0, 0, 360, color, max(2, int(width / 250)))
    for face in faces:
        try:
            bx1, by1, bx2, by2 = [int(value) for value in face.bbox]
            cv2.rectangle(shade, (bx1, by1), (bx2, by2), color, 1)
            for point in face.kps if face.kps is not None else []:
                cv2.circle(shade, tuple(int(value) for value in point), 2, (255, 210, 80), -1)
        except (ValueError, TypeError, AttributeError):
            continue
    cv2.putText(shade, step_text, (16, 30), cv2.FONT_HERSHEY_SIMPLEX,
                min(.65, width / 1000), (245, 245, 245), 2, cv2.LINE_AA)
    cv2.rectangle(shade, (0, height - 45), (width, height), (20, 25, 30), -1)
    cv2.putText(shade, readiness.short_message, (16, height - 17), cv2.FONT_HERSHEY_SIMPLEX,
                min(.58, width / 1050), color, 1, cv2.LINE_AA)
    if stability > 0:
        cv2.rectangle(shade, (0, height - 4), (int(width * min(1., stability)), height), color, -1)
    return shade


def capture_sample(frame, faces, expected_pose, reference=None):
    """Run on a worker: repeat gates, validate paired vector, encode original."""
    from .enrollment_samples import sample_from_frame
    readiness = assess_frame(frame, faces, expected_pose)
    if not readiness.ready:
        raise ValueError(readiness.message)
    sample = sample_from_frame(frame, faces, expected_pose, reference)
    x1, y1, x2, y2 = [int(value) for value in readiness.bbox]
    return sample, frame[y1:y2, x1:x2].copy()


def restore_pending_samples(serialized):
    """Decode a durable outbox batch on an IO worker, leaving its bytes intact."""
    from PIL import Image
    from .enrollment_samples import prepare_samples
    samples = [dict(pose=sample['pose'],
                    vector=np.frombuffer(base64.b64decode(sample['vector'], validate=True), dtype='<f4').copy(),
                    image=base64.b64decode(sample['image'], validate=True))
               for sample in serialized]
    prepare_samples(samples)
    crops = []
    for sample in samples:
        with Image.open(io.BytesIO(sample['image'])) as image:
            frame = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2BGR)
        x1, y1, x2, y2 = guide_bounds(frame.shape)
        crops.append(frame[y1:y2, x1:x2].copy())
    return samples, crops
