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

METRIC_NAMES = ('ear', 'mar', 'pitch', 'yaw', 'roll')


def observation_metrics(features):
    """Read measured values before applying the RF's frontal-pose gate."""
    if not isinstance(features, dict):
        return None
    try:
        if any(isinstance(features[key], bool) for key in METRIC_NAMES):
            return None
        values = {key: float(features[key]) for key in METRIC_NAMES}
    except (TypeError, KeyError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(value) for value in values.values()) or values['ear'] < 0 or values['mar'] < 0:
        return None
    return values


def attach_observation(result, features, values=None):
    """Keep current geometry visible when a pose cannot enter the RF model."""
    result = dict(result)
    values = values if values is not None else observation_metrics(features)
    if values is not None:
        result.update(values)
        result['metrics'] = dict(values)
    points = features.get('pts') if isinstance(features, dict) else None
    result['pts'] = points
    if points is not None:
        try:
            coordinates = [(float(point[0]), float(point[1])) for point in points]
            if coordinates and all(math.isfinite(value) for point in coordinates for value in point):
                xs, ys = zip(*coordinates)
                result['bounding_box'] = (min(xs), min(ys), max(xs), max(ys))
        except (TypeError, ValueError, IndexError, OverflowError):
            pass
    return result


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
        self.last_prediction=None

    def _values(self,features):
        return usable_observation(features,self.max_yaw_deg,self.max_pitch_deg)

    @staticmethod
    def _invalid(message,count=0,status='Unknown'):
        return dict(status=status,confidence=0.0,is_valid=False,message=message,valid_count=count,
                    source='unavailable',metrics={key:None for key in METRIC_NAMES})

    def predict_frame(self,frame):
        if frame is None:
            self.reset()
            return self._invalid('Frame unavailable',status='No_Face')
        return self.predict_features(self.extractor.extract_features(frame))

    def predict_features(self,features,captured_at=None):
        """Consume one face's features; use one predictor per tracked face.

        ``captured_at`` is monotonic. A caller sharing the extractor can avoid
        running MediaPipe twice on the same face crop through this method.
        """
        now=self.clock() if captured_at is None else captured_at
        values=observation_metrics(features)
        if values is None or not isinstance(now,(int,float)) or not math.isfinite(now):
            self.reset()
            return attach_observation(self._invalid('Need one usable face',status='No_Face' if features is None else 'Unknown'),features)
        if self._values(features) is None:
            self.reset()
            return attach_observation(dict(status='Distracted',confidence=None,probabilities={},
                is_valid=False,pose_valid=False,is_observed=True,rule_based=True,source='pose_rule',valid_count=0,
                message='Head turn exceeds frontal model limits; pose rule, no RF probability'),features,values)
        if self.last_sample_time is not None:
            gap=now-self.last_sample_time
            if gap<0 or gap>MAX_SNAPSHOT_GAP+1e-9:
                self.reset()
            elif gap<SNAPSHOT_INTERVAL-1e-9:
                if self.last_prediction is not None:
                    result=dict(self.last_prediction,sampled=False,message='Waiting for next snapshot')
                else:
                    result=self._invalid('Waiting for next snapshot',len(self.feature_buffer),status='Buffering')
                return attach_observation(result,features,values)
        self.feature_buffer.append(values)
        self.last_sample_time=now
        if len(self.feature_buffer)<3:
            return attach_observation(self._invalid('Need three snapshots',len(self.feature_buffer),status='Buffering'),features,values)
        vector=calculate_sequence_features(list(self.feature_buffer))
        try:
            current=probabilities(self.model,vector,self.classes_)
        except Exception:
            self.reset()
            return attach_observation(self._invalid('Model probability contract failed'),features,values)
        self.history_probs.append(current)
        averaged={label:sum(p[label] for p in self.history_probs)/len(self.history_probs) for label in self.classes_}
        label=max(averaged,key=averaged.get)
        self.last_valid_status=label
        self.last_prediction=dict(status=label,raw_status=max(current,key=current.get),confidence=averaged[label],
                    probabilities=averaged,is_valid=True,valid_count=3,source='rf',pose_valid=True,
                    is_observed=True,rule_based=False,sampled=True)
        return attach_observation(self.last_prediction,features,values)

    def predict_status_detailed(self,frames):
        if not isinstance(frames,(list,tuple)) or len(frames)!=3:
            return self._invalid('Need exactly three snapshots')
        features=[]
        for frame in frames:
            if frame is None:
                return self._invalid('Missing snapshot',len(features))
            observation=self.extractor.extract_features(frame)
            values=self._values(observation)
            if values is None:
                return attach_observation(self._invalid('Need three usable frontal observations',len(features)),observation)
            features.append(values)
        vector=calculate_sequence_features(features)
        try:
            probs=probabilities(self.model,vector,self.classes_)
        except Exception:
            return self._invalid('Model probability contract failed',3)
        label=max(probs,key=probs.get)
        result=attach_observation(dict(status=label,confidence=probs[label],probabilities=probs,is_valid=True,
                    valid_count=3,vector=vector,source='rf',rule_based=False),observation)
        result['metrics']={key:round(sum(f[key] for f in features)/3,3) for key in METRIC_NAMES}
        return result

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


def run_status_test(*, predictor_factory, camera_factory, ui, clock=time.monotonic):
    """Preview retries transient camera loss without reusing stale observations."""
    from contextlib import ExitStack
    from src.status_preview import draw_status_frame
    with ExitStack() as resources:
        predictor=predictor_factory()
        resources.callback(predictor.close)
        camera=camera_factory()
        resources.callback(camera.release)
        resources.callback(ui.destroyAllWindows)
        missing_since=None
        while True:
            ok,frame=camera.read()
            if not ok or frame is None:
                predictor.reset()
                now=clock()
                if missing_since is None:
                    missing_since=now
                if now-missing_since>=10:
                    raise RuntimeError('Camera không trả ảnh trong 10 giây. Kiểm tra AI service và webcam rồi mở Test Trạng thái lại.')
                import numpy as np
                display=np.zeros((480,640,3),dtype=np.uint8)
                ui.putText(display,'Dang ket noi camera... Q de thoat',(10,50),ui.FONT_HERSHEY_SIMPLEX,.6,(0,220,220),1)
                delay=100
            else:
                missing_since=None
                result=predictor.predict_frame(frame)
                display=draw_status_frame(frame,result,ui=ui)
                ui.putText(display,'Q de thoat',(20,100),ui.FONT_HERSHEY_SIMPLEX,.5,(220,220,220),1)
                delay=1
            ui.imshow('Status inference',display)
            if ui.waitKey(delay)&0xff==ord('q'):
                break
            visible=getattr(ui,'getWindowProperty',None)
            if visible is not None and visible('Status inference',ui.WND_PROP_VISIBLE)<1:
                break


def main():
    from src.runtime_config import load_environment
    load_environment()
    import cv2
    from src.camera_source import open_camera
    try:
        run_status_test(predictor_factory=StatusPredictor,camera_factory=lambda:open_camera(0),ui=cv2)
        return 0
    except Exception as error:
        print('Status inference stopped:',str(error),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
