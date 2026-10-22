"""Threaded status camera pipeline and display helpers, without Tk dependencies."""
import math
import threading
import time


STATUS_LABELS = {
    'Normal': 'Bình thường / tập trung',
    'Fatigue': 'Mệt mỏi / buồn ngủ',
    'Exhausted': 'Kiệt sức / buồn ngủ',
    'Distracted': 'Mất tập trung / quay đầu',
    'Buffering': 'Đang thu thập 3 mẫu',
    'No_Face': 'Chưa có một khuôn mặt rõ',
    'Unknown': 'Chưa đủ dữ liệu phân tích',
}
ABNORMAL_STATES = frozenset(('Fatigue', 'Exhausted', 'Distracted'))


def state_label(status):
    return STATUS_LABELS.get(status, str(status or 'Chưa có kết quả'))


def confidence_text(result):
    if result.get('rule_based'):
        return 'N/A · quy tắc góc đầu'
    confidence = result.get('confidence')
    if result.get('is_valid') and isinstance(confidence, (int, float)) and math.isfinite(confidence):
        return f'{confidence * 100:.1f}%'
    return '—'


def draw_status_frame(frame, result, *, ui=None, show_text=True):
    """Draw on a copy; model input and shared camera snapshots stay untouched."""
    if ui is None:
        import cv2 as ui
    display = frame.copy()
    status = result.get('status', 'Unknown')
    color = (75, 75, 240) if status in ABNORMAL_STATES else ((95, 210, 90) if result.get('is_valid') else (0, 200, 240))
    rectangle = getattr(ui, 'rectangle', None)
    box = result.get('bounding_box')
    if callable(rectangle) and box is not None and len(box) == 4:
        try:
            h, w = display.shape[:2]
            x1, y1, x2, y2 = [int(value) for value in box]
            rectangle(display, (max(0, x1), max(0, y1)), (min(w-1, x2), min(h-1, y2)), color, 2)
        except (TypeError, ValueError, OverflowError):
            pass
    circle = getattr(ui, 'circle', None)
    points = result.get('pts')
    if callable(circle) and points is not None:
        try:
            h, w = display.shape[:2]
            # A sparse face mesh remains readable at normal webcam resolution.
            indices = set(range(0, min(len(points), 468), 6)) | {13, 14, 33, 78, 133, 152, 263, 308, 362}
            for index in sorted(indices):
                if index >= len(points):
                    continue
                x, y = int(points[index][0]), int(points[index][1])
                if 0 <= x < w and 0 <= y < h:
                    circle(display, (x, y), 1, color, -1)
        except (TypeError, ValueError, OverflowError, IndexError):
            pass
    if show_text:
        confidence = result.get('confidence')
        suffix = ' (pose rule)' if result.get('rule_based') else (
            f' ({confidence * 100:.1f}%)' if result.get('is_valid') and isinstance(confidence, (int, float)) else '')
        ui.putText(display, str(status) + suffix, (20, 35), ui.FONT_HERSHEY_SIMPLEX, .7, color, 2)
        metrics = result.get('metrics', {})
        parts = []
        for key in ('ear', 'mar', 'pitch', 'yaw', 'roll'):
            value = metrics.get(key, result.get(key))
            if isinstance(value, (int, float)) and math.isfinite(value):
                parts.append(f'{key.upper()} {value:.3f}' if key in ('ear', 'mar') else f'{key.title()} {value:.1f}')
        if parts:
            ui.putText(display, ' | '.join(parts), (20, 65), ui.FONT_HERSHEY_SIMPLEX, .46, color, 1)
    return display


class StatusPreviewWorker:
    """One camera reader and inference worker publishing only the newest frame.

    Models and camera are created and disposed on the same worker thread. Close
    returns immediately; ``thread`` may be joined outside the Tk event loop.
    """
    def __init__(self, predictor_factory=None, camera_factory=None, *, clock=time.monotonic, interval=.03):
        if predictor_factory is None:
            from src.predict_status import StatusPredictor
            predictor_factory = StatusPredictor
        if camera_factory is None:
            from src.camera_source import open_camera
            camera_factory = lambda: open_camera(0)
        self.predictor_factory = predictor_factory
        self.camera_factory = camera_factory
        self.clock, self.interval = clock, interval
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = dict(state='loading', frame=None, result={}, message='Đang tải model trạng thái…', captured_at=None)
        self.thread = threading.Thread(target=self._run, name='status-camera-inference', daemon=False)
        self.thread.start()

    def _publish(self, **values):
        with self.lock:
            self.latest = values

    def snapshot(self, max_age=.8):
        with self.lock:
            latest = dict(self.latest)
        captured_at = latest.get('captured_at')
        if self.stop.is_set():
            return dict(state='closed', frame=None, result={}, message='Đã dừng camera', captured_at=None)
        if captured_at is not None and self.clock() - captured_at > max_age:
            latest.update(state='waiting', frame=None, result={}, message='Đang chờ ảnh camera mới…')
        return latest

    def _run(self):
        predictor = camera = None
        try:
            predictor = self.predictor_factory()
            if self.stop.is_set():
                return
            camera = self.camera_factory()
            missing_since = None
            while not self.stop.is_set():
                ok, frame = camera.read()
                now = self.clock()
                if self.stop.is_set():
                    break
                if not ok or frame is None:
                    if missing_since is None:
                        predictor.reset()
                        missing_since = now
                    if now - missing_since >= 10:
                        raise RuntimeError('Camera không trả ảnh trong 10 giây. Kiểm tra AI Service và webcam rồi thử lại.')
                    self._publish(state='waiting', frame=None, result={}, message='Đang kết nối camera…', captured_at=None)
                    self.stop.wait(.1)
                    continue
                missing_since = None
                started = self.clock()
                result = predictor.predict_frame(frame)
                elapsed = max(0, self.clock() - started)
                self._publish(state='running', frame=frame, result=result, message='',
                              captured_at=now, inference_ms=elapsed * 1000)
                self.stop.wait(self.interval)
        except Exception as error:
            self._publish(state='error', frame=None, result={}, message=str(error), captured_at=None)
        finally:
            if camera is not None:
                try:
                    camera.release()
                except Exception:
                    pass
            if predictor is not None:
                try:
                    predictor.close()
                except Exception:
                    pass

    def close(self):
        self.stop.set()
