"""Validated status inference sharing timing/features with the collector."""
import math
import sys
import time
from collections import deque
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0,str(BASE))
from src.sequence_features import calculate_sequence_features, usable_observation, SNAPSHOT_INTERVAL, MAX_SNAPSHOT_GAP, LABELS


def probabilities(model, vector, classes):
    values=list(model.predict_proba([vector])[0])
    if len(values)!=len(classes) or set(classes)!=set(LABELS):
        raise ValueError('Invalid probability/class dimensions')
    values=[float(value) for value in values]
    if not all(math.isfinite(value) and 0<=value<=1 for value in values) or abs(sum(values)-1)>1e-5:
        raise ValueError('Invalid model probability vector')
    return {str(label):value for label,value in zip(classes,values)}


class StatusPredictor:
    def __init__(self,smoothing_window=5,max_yaw_deg=25.0,max_pitch_deg=35.0,*,model_path=None,extractor=None,clock=None):
        from src.status_model import load_status_model
        if type(smoothing_window) is not int or not 1<=smoothing_window<=100:
            raise ValueError('Invalid smoothing window')
        if not all(math.isfinite(value) and 0<value<=180 for value in (max_yaw_deg,max_pitch_deg)):
            raise ValueError('Invalid pose configuration')
        self.model,self.model_metadata=load_status_model(model_path or BASE/'data/rf_status_model.pkl')
        self.classes_=list(self.model.classes_)
        if extractor is None:
            from src.status_features import StatusFeatureExtractor
            extractor=StatusFeatureExtractor()
        self.extractor=extractor
        self.max_yaw_deg,self.max_pitch_deg=max_yaw_deg,max_pitch_deg
        self.smoothing_window=smoothing_window
        self.feature_buffer=deque(maxlen=3)
        self.history_probs=deque(maxlen=smoothing_window)
        self.clock=clock or time.monotonic
        self.reset()

    def reset(self):
        self.feature_buffer.clear()
        self.history_probs.clear()
        self.last_valid_status='Unknown'
        self.last_sample_time=None

    def _values(self,features):
        return usable_observation(features,self.max_yaw_deg,self.max_pitch_deg)

    @staticmethod
    def _invalid(message,count=0,status='Unknown'):
        return dict(status=status,confidence=0.0,is_valid=False,message=message,valid_count=count,
                    metrics=dict(ear=0.0,mar=0.0,pitch=0.0,yaw=0.0))

    def predict_frame(self,frame):
        if frame is None:
            self.reset()
            return self._invalid('Frame unavailable',status='No_Face')
        now=self.clock()
        features=self.extractor.extract_features(frame)
        values=self._values(features)
        if values is None or not math.isfinite(now):
            self.reset()
            return self._invalid('Need one usable frontal face',status='No_Face' if features is None else 'Unknown')
        if self.last_sample_time is not None:
            gap=now-self.last_sample_time
            if gap<0 or gap>MAX_SNAPSHOT_GAP+1e-9:
                self.reset()
            elif gap<SNAPSHOT_INTERVAL-1e-9:
                return dict(self._invalid('Waiting for next snapshot',len(self.feature_buffer),status='Buffering'),**values,pts=features.get('pts'))
        self.feature_buffer.append(values)
        self.last_sample_time=now
        if len(self.feature_buffer)<3:
            return dict(self._invalid('Need three snapshots',len(self.feature_buffer),status='Buffering'),**values,pts=features.get('pts'))
        vector=calculate_sequence_features(list(self.feature_buffer))
        try:
            current=probabilities(self.model,vector,self.classes_)
        except Exception:
            self.reset()
            return self._invalid('Model probability contract failed')
        self.history_probs.append(current)
        averaged={label:sum(p[label] for p in self.history_probs)/len(self.history_probs) for label in self.classes_}
        label=max(averaged,key=averaged.get)
        self.last_valid_status=label
        return dict(status=label,raw_status=max(current,key=current.get),confidence=averaged[label],
                    probabilities=averaged,is_valid=True,valid_count=3,**values,pts=features.get('pts'))

    def predict_status_detailed(self,frames):
        if not isinstance(frames,(list,tuple)) or len(frames)!=3:
            return self._invalid('Need exactly three snapshots')
        features=[]
        for frame in frames:
            if frame is None:
                return self._invalid('Missing snapshot',len(features))
            values=self._values(self.extractor.extract_features(frame))
            if values is None:
                return self._invalid('Need three usable frontal observations',len(features))
            features.append(values)
        vector=calculate_sequence_features(features)
        try:
            probs=probabilities(self.model,vector,self.classes_)
        except Exception:
            return self._invalid('Model probability contract failed',3)
        label=max(probs,key=probs.get)
        return dict(status=label,confidence=probs[label],probabilities=probs,is_valid=True,valid_count=3,vector=vector,
                    metrics={key:round(sum(f[key] for f in features)/3,3) for key in ('ear','mar','pitch','yaw')})

    def predict_status(self,frames):
        return self.predict_status_detailed(frames)['status']

    def close(self):
        self.extractor.close()


def to_serializable(result):
    def native(value):
        if isinstance(value,dict):
            return {key:native(item) for key,item in value.items() if key!='pts'}
        if isinstance(value,(list,tuple)):
            return [native(item) for item in value]
        if hasattr(value,'item'):
            value=value.item()
        if isinstance(value,float) and not math.isfinite(value):
            return None
        return value
    return native(result)


def main():
    import cv2
    from contextlib import ExitStack
    from src.camera_source import open_camera
    try:
        with ExitStack() as resources:
            predictor=StatusPredictor()
            resources.callback(predictor.close)
            camera=open_camera(0)
            resources.callback(camera.release)
            resources.callback(cv2.destroyAllWindows)
            while True:
                ok,frame=camera.read()
                if not ok or frame is None:
                    raise RuntimeError('Camera unavailable')
                result=predictor.predict_frame(frame)
                display=frame.copy()
                cv2.putText(display,result['status'],(20,40),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,220,220),2)
                cv2.imshow('Status inference',display)
                if cv2.waitKey(1)&0xff==ord('q'):
                    break
        return 0
    except Exception as error:
        print('Status inference stopped:',str(error),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
