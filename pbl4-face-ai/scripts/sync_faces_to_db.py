"""Import offline faces explicitly; preserve attendance and health history."""
import argparse
from pathlib import Path
import pickle
import sys
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from src.face_sync import employee_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write validated samples; default is read-only')
    args = parser.parse_args()
    path = BASE_DIR / 'data/embeddings.pkl'
    if not path.is_file():
        parser.error('Missing local gallery; no data was changed')
    with path.open('rb') as stream:
        gallery = pickle.load(stream)
    planned = {}
    for sid, info in gallery.items():
        identity = employee_id(sid)
        if identity in planned:
            parser.error('Duplicate local aliases for one employee; refresh gallery first')
        planned[identity] = (sid, info)
    print('Employees to synchronize:', len(planned), '(attendance and health history are preserved)')
    if not args.apply:
        print('Read-only plan. Add --apply to synchronize face samples.')
        return
    from src.face_engine import FaceEngine
    from src.register import collect_folder_samples
    from src.desktop_enrollment import DesktopEnrollment
    engine = FaceEngine()
    store = DesktopEnrollment()
    store.refresh()
    revisions = {sid: store.revision(sid) for sid, info in planned.values()}
    prepared = [(sid, info, collect_folder_samples(engine, BASE_DIR / 'data/registered' / sid)) for sid, info in planned.values()]
    for sid, info, samples in prepared:
        store.stage(sid, info['name'], samples, revisions[sid])
    result = store.retry()
    print('Completed:', result['completed'], 'Pending:', result['pending'])
    for message in result['errors']:
        print(message)
    if result['pending']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
