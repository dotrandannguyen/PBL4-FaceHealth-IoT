"""Camera preview and explicitly requested, durable attendance scans.

The camera stays live while the existing engine performs one scan per request.
Identity/state inference only runs for that scan, never for idle preview frames.
"""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
from queue import Empty, Queue
import threading
import time

import numpy as np

BASE = Path(__file__).resolve().parents[1]


def normalized_embedding(face):
    vector = getattr(face, 'embedding', None)
    if vector is None:
        return None
    vector = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(vector))
    if vector.shape != (512,) or not np.isfinite(vector).all() or not np.isfinite(norm) or norm <= 0:
        return None
    return vector / norm


class LockedFaceEngine:
    """Serialize access to the existing InsightFace instance across workers."""
    def __init__(self, engine):
        self.engine = engine
        self.lock = threading.Lock()

    def detect(self, frame):
        with self.lock:
            return self.engine.detect(frame)

    def embed(self, frame):
        with self.lock:
            return self.engine.embed(frame)


class LiveFaceAnalyzer:
    """Give each tracked face its own temporal state; never share face buffers."""
    def __init__(self, face_engine, predictor_factory=None, identify_func=None, clock=time.monotonic):
        if predictor_factory is None:
            from src.predict_status import StatusPredictor
            predictor_factory = StatusPredictor
        if identify_func is None:
            from src.verify import identify
            identify_func = identify
        self.face_engine = face_engine
        self.predictor_factory, self.identify = predictor_factory, identify_func
        self.clock = clock
        self.tracks = {}
        self.next_track = 1

    def _expire(self, now, active=()):
        for key, track in list(self.tracks.items()):
            # A disappeared face must start a fresh three-observation sequence.
            if key not in active or now - track['seen'] > .75:
                track['predictor'].close()
                del self.tracks[key]

    def _track(self, embedding, bbox, now, used):
        best, similarity = None, .60
        if embedding is not None:
            for key, track in self.tracks.items():
                if key in used or now - track['seen'] > .75:
                    continue
                score = float(np.dot(embedding, track['embedding']))
                if score > similarity:
                    best, similarity = key, score
        if best is None:
            best = self.next_track
            self.next_track += 1
            self.tracks[best] = {'predictor': self.predictor_factory()}
        track = self.tracks[best]
        track.update(embedding=embedding, bbox=bbox, seen=now)
        used.add(best)
        return best, track['predictor']

    @staticmethod
    def _features(predictor, frame, bbox):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        margin = .22 * max(x2 - x1, y2 - y1)
        left, top = max(0, int(x1 - margin)), max(0, int(y1 - margin))
        right, bottom = min(w, int(x2 + margin)), min(h, int(y2 + margin))
        if right <= left or bottom <= top:
            return None
        features = predictor.extractor.extract_features(frame[top:bottom, left:right])
        if features is None:
            return None
        features = dict(features)
        pts = features.get('pts')
        if pts is not None:
            pts = np.asarray(pts, dtype=float) + np.array([left, top])
            if not np.isfinite(pts).all():
                return None
            center = pts.mean(axis=0)
            if not (x1 <= center[0] <= x2 and y1 <= center[1] <= y2):
                return None
            features['pts'] = pts
            # Restore full-frame geometry, matching the existing training extractor.
            pose = getattr(predictor.extractor, '_calculate_head_pose', None)
            if pose is not None:
                features['pitch'], features['yaw'], features['roll'] = pose(pts, w, h)
        return features

    def analyze(self, frame, captured_at=None):
        now = self.clock() if captured_at is None else captured_at
        faces = self.face_engine.detect(frame)
        self._expire(now, self.tracks.keys())
        output, used = [], set()
        for face in faces:
            bbox = np.asarray(face.bbox, dtype=float)
            if bbox.shape != (4,) or not np.isfinite(bbox).all():
                continue
            embedding = normalized_embedding(face)
            if embedding is None:
                continue
            track_id, predictor = self._track(embedding, bbox, now, used)
            identity = self.identify(self.face_engine, frame, probe_embedding=embedding)
            try:
                features = self._features(predictor, frame, bbox)
                state = predictor.predict_features(features, captured_at=now)
            except Exception as error:
                predictor.reset()
                state = {'status': 'Unknown', 'confidence': 0.0, 'is_valid': False,
                         'message': 'Không phân tích được mặt: ' + str(error), 'metrics': {}}
            output.append(dict(identity, bbox=bbox.tolist(), track_id=track_id, state=state))
        self._expire(now, used)
        return output

    def reset(self):
        for track in self.tracks.values():
            track['predictor'].reset()

    def close(self):
        self._expire(self.clock(), ())


def read_history(path, limit=300):
    """Read the existing JSONL format, tolerating a partial trailing write."""
    records = deque(maxlen=limit)
    try:
        with Path(path).open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(record, dict) and 'student_id' in record and 'timestamp' in record:
                    records.append(record)
    except FileNotFoundError:
        pass
    return list(records)


class AttendanceWorker:
    """Single owner of camera lifecycle; public methods never wait for inference."""
    def __init__(self, *, engine_factory=None, camera_factory=None, analyzer_factory=None,
                 logs_dir=None, clock=time.monotonic):
        self.engine_factory = engine_factory
        self.camera_factory = camera_factory
        self.analyzer_factory = analyzer_factory
        self.logs_dir = Path(logs_dir) if logs_dir is not None else BASE / 'logs'
        self.clock = clock
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.commands = Queue(maxsize=1)
        self.request_pending = False
        self.loading, self.error = True, ''
        self.latest = {'frame': None, 'faces': [], 'info': {}, 'seq': 0,
                       'captured_at': None, 'result_frame': None}
        self.records = []
        self.thread = threading.Thread(target=self._run, name='attendance-camera', daemon=True)
        self.thread.start()

    def snapshot(self):
        with self.lock:
            snapshot = dict(self.latest)
        if self.stop.is_set() or self.error:
            snapshot.update(frame=None, faces=[], captured_at=None, result_frame=None)
        return snapshot

    def history(self):
        with self.lock:
            return list(self.records)

    def start_session(self):
        from queue import Full
        with self.lock:
            state = self.latest['info'].get('state')
            state = getattr(state, 'value', state)
            if (self.loading or self.error or self.stop.is_set() or self.request_pending
                    or state != 'IDLE' or self.latest['frame'] is None):
                return False
            try:
                self.commands.put_nowait('start')
            except Full:
                return False
            self.request_pending = True
            return True

    def close(self):
        self.stop.set()

    def _run(self):
        from src.camera_source import FramePump, open_camera
        engine = pump = None
        try:
            records = read_history(self.logs_dir / 'attendance_logs.jsonl')
            with self.lock:
                self.records = records
            if self.engine_factory is None:
                from unified_engine import UnifiedAttendanceEngine
                engine = UnifiedAttendanceEngine(logs_dir=self.logs_dir, camera_only=True)
            else:
                engine = self.engine_factory()
            pump = FramePump(self.camera_factory or (lambda: open_camera(0)), lambda: None)
            self.loading = False
            last_frame_time, last_event = None, None
            seq = 0
            had_frame = False
            while not self.stop.is_set():
                frame, _, captured_at = pump.snapshot_with_timestamp()
                try:
                    command = self.commands.get_nowait()
                except Empty:
                    command = None
                if command == 'start':
                    # An accepted press always starts an attempt. If the camera
                    # disconnects now, the engine reports its normal timeout.
                    engine.start_session()
                fresh = captured_at is not None and captured_at != last_frame_time
                # update(None) still polls inference/finalization and timeouts.
                info = engine.update(frame if fresh else None)
                if fresh:
                    last_frame_time = captured_at
                    seq += 1
                if had_frame and frame is None:
                    seq += 1
                had_frame = frame is not None
                state = getattr(info.get('state'), 'value', info.get('state'))
                result_frame = getattr(engine, 'best_frame_bgr', None) if state == 'COMPLETED' else None
                record = info.get('completed_record')
                if record and record.get('event_id') != last_event:
                    last_event = record.get('event_id')
                    with self.lock:
                        self.records = (self.records + [record])[-300:]
                with self.lock:
                    self.latest = {'frame': frame, 'faces': [], 'info': info, 'seq': seq,
                                   'captured_at': captured_at, 'result_frame': result_frame}
                    if command == 'start':
                        self.request_pending = False
                self.stop.wait(.015)
        except Exception as error:
            self.error = str(error)
            self.loading = False
        finally:
            # Release camera before waiting for durable network writes to finish.
            if pump is not None:
                pump.close()
                pump.thread.join()
            if engine is not None:
                engine.close()
