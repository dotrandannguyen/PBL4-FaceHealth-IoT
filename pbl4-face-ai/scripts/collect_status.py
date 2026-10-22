"""Collect manually labelled three-snapshot sequences with durable metadata."""
import argparse
from contextlib import ExitStack
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from src.status_dataset import SequenceCollector, StatusDataset, subject_id
from src.sequence_features import usable_observation

LABEL_KEYS = {ord('1'):'Normal', ord('2'):'Fatigue', ord('3'):'Exhausted'}


def run_collection(subject, output, *, camera_factory, extractor_factory, ui, clock=time.monotonic):
    collector, dataset = SequenceCollector(subject), StatusDataset(output)
    dataset.inspect()  # Fail before opening hardware when schema is incompatible.
    recovered = dataset.recover()
    count = 0
    missing_since = None
    note = 'Nhan 1/2/3 mot lan va tha phim; giu mat chinh dien'
    with ExitStack() as resources:
        camera = camera_factory()
        resources.callback(camera.release)
        extractor = extractor_factory()
        resources.callback(extractor.close)
        resources.callback(ui.destroyAllWindows)
        while True:
            ok, frame = camera.read()
            observed_at = clock()
            if not ok or frame is None:
                collector.cancel()
                if missing_since is None:
                    missing_since = observed_at
                if observed_at - missing_since >= 10:
                    raise RuntimeError('Camera không trả ảnh trong 10 giây. Kiểm tra AI service và webcam; mẫu đã lưu được giữ nguyên.')
                import numpy as np
                waiting = np.zeros((480, 640, 3), dtype=np.uint8)
                ui.putText(waiting, 'Dang ket noi camera... Q de thoat', (10, 50), ui.FONT_HERSHEY_SIMPLEX, .6, (0, 220, 220), 1)
                ui.imshow('Status dataset v2', waiting)
                if ui.waitKey(100) & 0xff == ord('q'):
                    break
                visible = getattr(ui, 'getWindowProperty', None)
                if visible is not None and visible('Status dataset v2', ui.WND_PROP_VISIBLE) < 1:
                    break
                continue
            missing_since = None
            features = extractor.extract_features(frame)
            active_label = collector.label
            row = collector.observe(features, observed_at)
            if row is not None:
                dataset.record(row)  # Journal first; a failed merge leaves a recoverable row.
                count += 1
                print('Saved sequence:',row['sequence_id'],row['label'])
                note = f'Da luu {count} chuoi. Nhan nhan de thu chuoi tiep theo'
            elif active_label is not None and collector.label is None:
                note = 'Chuoi bi ngat (mat/goc mat/nhip anh). Nhan lai 1/2/3'
                print('Incomplete sequence cancelled; need one usable frontal face and 300-600 ms snapshot gaps.')
            display = frame.copy()
            values = usable_observation(features)
            text = f"EAR={values['ear']:.3f} MAR={values['mar']:.3f}" if values else 'Can 1 khuon mat hop le. Nhin thang camera'
            ui.putText(display,text,(10,30),ui.FONT_HERSHEY_SIMPLEX,.6,(220,220,220),1)
            ui.putText(display,f'1 Normal | 2 Fatigue | 3 Exhausted | Q save/exit | saved={count}',
                       (10,60),ui.FONT_HERSHEY_SIMPLEX,.5,(0,220,220),1)
            state = f'Collecting {collector.label}: {len(collector.features)}/3' if collector.label else 'Press a label key to start a new sequence'
            ui.putText(display,state,(10,90),ui.FONT_HERSHEY_SIMPLEX,.5,(0,220,100),1)
            ui.putText(display,note,(10,120),ui.FONT_HERSHEY_SIMPLEX,.45,(220,220,100),1)
            ui.imshow('Status dataset v2',display)
            key = ui.waitKey(1) & 0xff
            if key == ord('q'):
                collector.cancel()  # An incomplete sequence never becomes a row.
                break
            visible = getattr(ui, 'getWindowProperty', None)
            if visible is not None and visible('Status dataset v2', ui.WND_PROP_VISIBLE) < 1:
                collector.cancel()
                break
            if key in LABEL_KEYS and collector.label != LABEL_KEYS[key]:
                collector.start(LABEL_KEYS[key])
    return dict(saved=count,recovered=recovered)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', required=True, type=subject_id, help='Stable pseudonymous participant ID')
    parser.add_argument('--output',type=Path,default=BASE/'data/status_dataset_v2.csv')
    parser.add_argument('--recover',action='store_true',help='Recover completed pending rows without opening a camera')
    args=parser.parse_args(argv)
    try:
        if args.recover:
            print('Recovered observations:',StatusDataset(args.output).recover())
            return 0
        import cv2
        from src.camera_source import open_camera
        from src.status_features import StatusFeatureExtractor
        print('Labels are entered by the operator; EAR does not automatically define a label.')
        result=run_collection(args.subject,args.output,camera_factory=lambda:open_camera(0),
                              extractor_factory=StatusFeatureExtractor,ui=cv2)
        print('New sequences:',result['saved'],'Recovered:',result['recovered'])
        return 0 if result['saved'] else 2
    except Exception as error:
        print('Collection stopped; existing CSV/pending rows preserved:',str(error),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
