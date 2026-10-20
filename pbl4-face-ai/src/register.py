"""Register five paired poses; DB-confirmed galleries remain authoritative."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from src.runtime_config import load_environment
from src.enrollment_pose import POSES, estimate_pose
from src.enrollment_samples import sample_from_frame, prepare_samples
from src.desktop_enrollment import DesktopEnrollment
from src.gallery_store import GalleryCache

EMBEDDINGS_PATH = BASE / 'data/embeddings.pkl'
REGISTERED_DIR = BASE / 'data/registered'


def load_db():
    return GalleryCache().load(EMBEDDINGS_PATH)


def collect_folder_samples(engine, folder):
    import cv2
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in ('.jpg','.jpeg','.png','.bmp','.webp'))
    if len(files) != 5:
        raise ValueError('Folder cần đúng năm ảnh, mỗi hướng một ảnh; không dùng embedding trung bình thay mẫu gốc')
    samples = {}
    reference = None
    for path in files:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError('Không đọc được ảnh: ' + path.name)
        faces = engine.detect(image)
        if len(faces) != 1:
            raise ValueError('Ảnh phải có đúng một mặt: ' + path.name)
        pose, _ = estimate_pose(faces[0].kps)
        if pose in samples:
            raise ValueError('Trùng hướng khuôn mặt: ' + pose)
        sample = sample_from_frame(image, faces, pose, reference)
        reference = sample['vector'] if reference is None else reference
        samples[pose] = sample
    return prepare_samples([samples[pose] for pose in POSES])


def _submit(student_id, student_name, samples, expected_revision):
    store = DesktopEnrollment(gallery_path=EMBEDDINGS_PATH)
    job = store.stage(student_id, student_name, samples, expected_revision)
    result = store.retry()
    print('Batch:', job, '| Completed:', result['completed'], '| Pending:', result['pending'])
    for message in result['errors']:
        print(message)
    return result['pending'] == 0


def register_from_folder(engine, student_id, student_name, folder):
    revision = DesktopEnrollment(gallery_path=EMBEDDINGS_PATH).revision(student_id)
    return _submit(student_id, student_name, collect_folder_samples(engine, folder), revision)


def register_from_webcam(engine, student_id, student_name, n_samples=5):
    if n_samples != 5:
        raise ValueError('Enrollment yêu cầu đúng năm tư thế')
    revision = DesktopEnrollment(gallery_path=EMBEDDINGS_PATH).revision(student_id)
    import cv2
    from src.camera_source import open_camera
    camera = open_camera(0)
    samples = []
    stable_since = None
    try:
        while len(samples) < 5:
            ok, frame = camera.read()
            if not ok or frame is None:
                print('Camera chưa sẵn sàng. Batch chưa đủ không được lưu.')
                return False
            faces = engine.detect(frame)
            pose = POSES[len(samples)]
            valid = False
            if len(faces) == 1:
                try:
                    valid = estimate_pose(faces[0].kps)[0] == pose
                except (ValueError, TypeError):
                    pass
            stable_since = (stable_since or time.monotonic()) if valid else None
            display = frame.copy()
            cv2.putText(display, f'{len(samples)+1}/5: {pose} | SPACE=capture Q=cancel', (10,30),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, (0,220,100), 2)
            cv2.imshow('Enrollment: ' + str(student_id), display)
            key = cv2.waitKey(30) & 0xff
            if key == ord('q'):
                return False
            if (key == ord(' ') or (stable_since is not None and time.monotonic()-stable_since >= 1)) and valid:
                try:
                    samples.append(sample_from_frame(frame, faces, pose, samples[0]['vector'] if samples else None))
                    stable_since = None
                except (ValueError, TypeError) as error:
                    print(str(error))
                    stable_since = None
    finally:
        camera.release()
        cv2.destroyAllWindows()
    return _submit(student_id, student_name, samples, revision)


def list_db():
    for sid, info in load_db().items():
        print(sid, info['name'], info.get('n_images', '?'))


def main():
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('list')
    sub.add_parser('refresh', help='Read confirmed samples from DB')
    sub.add_parser('retry', help='Retry durable pending batches')
    for command in ('folder', 'webcam'):
        option = sub.add_parser(command)
        option.add_argument('--id', required=True)
        option.add_argument('--name', required=True)
        if command == 'folder':
            option.add_argument('--images', required=True, type=Path)
        else:
            option.add_argument('--samples', type=int, default=5, choices=[5])
    args = parser.parse_args()
    if args.command in (None, 'list'):
        list_db()
        return 0
    if args.command == 'refresh':
        print('Confirmed employees:', len(DesktopEnrollment().refresh()))
        return 0
    if args.command == 'retry':
        result = DesktopEnrollment().retry()
        print(result)
        return 0 if result['pending'] == 0 else 2
    from src.face_engine import FaceEngine
    engine = FaceEngine()
    success = register_from_folder(engine, args.id, args.name, args.images) if args.command == 'folder' else register_from_webcam(engine, args.id, args.name, args.samples)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(main())
