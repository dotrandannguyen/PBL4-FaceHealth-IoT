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
                raise RuntimeError('Camera frame unavailable; completed observations remain saved/pending')
            features = extractor.extract_features(frame)
            row = collector.observe(features, observed_at)
            if row is not None:
                dataset.record(row)  # Journal first; a failed merge leaves a recoverable row.
                count += 1
                print('Saved sequence:',row['sequence_id'],row['label'])
            display = frame.copy()
            values = usable_observation(features)
            text = f"EAR={values['ear']:.3f} MAR={values['mar']:.3f}" if values else 'No usable single frontal face'
            ui.putText(display,text,(10,30),ui.FONT_HERSHEY_SIMPLEX,.6,(220,220,220),1)
            ui.putText(display,f'1 Normal | 2 Fatigue | 3 Exhausted | Q save/exit | saved={count}',
                       (10,60),ui.FONT_HERSHEY_SIMPLEX,.5,(0,220,220),1)
            state = f'Collecting {collector.label}: {len(collector.features)}/3' if collector.label else 'Press a label key to start a new sequence'
            ui.putText(display,state,(10,90),ui.FONT_HERSHEY_SIMPLEX,.5,(0,220,100),1)
            ui.imshow('Status dataset v2',display)
            key = ui.waitKey(1) & 0xff
            if key == ord('q'):
                collector.cancel()  # An incomplete sequence never becomes a row.
                break
            if key in LABEL_KEYS:
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
