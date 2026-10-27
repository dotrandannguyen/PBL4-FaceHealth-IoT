"""Native Tk/Pillow status window checks using synthetic frames and no camera."""
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'pbl4-face-ai'
sys.path.insert(0, str(ROOT))
import numpy as np
from gui_status import StatusTestApp


class FakeWorker:
    def __init__(self):
        self.closed = False
        self.thread = types.SimpleNamespace(is_alive=lambda: not self.closed)
        self.result = dict(status='Normal', confidence=.91, is_valid=True, valid_count=3,
                           metrics=dict(ear=.31, mar=.08, pitch=179., yaw=2., roll=1.),
                           bounding_box=(50, 40, 270, 230), pts=np.array([[70, 80], [100, 100]]))
        self.state = 'running'
    def snapshot(self):
        return dict(state=self.state, frame=np.zeros((240, 320, 3), dtype=np.uint8) if self.state == 'running' else None,
                    result=self.result, inference_ms=12.4, message='Synthetic error')
    def close(self):
        self.closed = True


class StatusWindowRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.workers = []
        def factory():
            worker = FakeWorker()
            self.workers.append(worker)
            return worker
        self.app = StatusTestApp(worker_factory=factory)
        self.app.withdraw()
        self.app.update_idletasks()
        self.app.update()
        self.addCleanup(self.app.destroy)

    def poll_once(self):
        if self.app.timer is not None:
            self.app.after_cancel(self.app.timer)
            self.app.timer = None
        self.app._poll()

    def test_real_widgets_and_image_follow_inference_and_pose_rule(self):
        self.poll_once()
        self.assertIn('Bình thường', self.app.status_label.cget('text'))
        self.assertEqual(self.app.confidence_label.cget('text'), 'Độ tự tin: 91.0%')
        self.assertEqual(self.app.metric_labels['ear'].cget('text'), '0.310')
        self.assertEqual(self.app.metric_labels['roll'].cget('text'), '1.0°')
        self.assertIsNotNone(self.app.photo)
        self.assertEqual(self.app.canvas.itemcget(self.app.notice_item, 'state'), 'hidden')
        self.workers[0].result.update(status='Distracted', confidence=None, is_valid=False,
                                       rule_based=True, valid_count=0)
        self.poll_once()
        self.assertIn('Mất tập trung', self.app.status_label.cget('text'))
        self.assertIn('quy tắc', self.app.confidence_label.cget('text'))
        self.assertEqual(float(self.app.progress['value']), 0)

    def test_pause_restart_and_close_release_the_worker(self):
        self.app.pause()
        self.assertTrue(self.workers[0].closed)
        self.assertIsNone(self.app.worker)
        self.assertEqual(self.app.metric_labels['ear'].cget('text'), '—')
        self.assertEqual(self.app.canvas.itemcget(self.app.camera_item, 'state'), 'hidden')
        self.app.start()
        self.assertEqual(len(self.workers), 2)
        self.app.destroy()
        self.assertTrue(self.workers[1].closed)

    def test_model_error_is_actionable_and_clears_the_old_image(self):
        worker = self.workers[0]
        worker.state = 'error'
        worker.result = {}
        self.poll_once()
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')
        self.assertEqual(self.app.canvas.itemcget(self.app.camera_item, 'state'), 'hidden')
        self.assertEqual(self.app.canvas.itemcget(self.app.notice_item, 'text'), 'Synthetic error')
        self.assertEqual(self.app.metric_labels['yaw'].cget('text'), '—')

    def test_minimum_window_keeps_metrics_progress_and_camera_controls_visible(self):
        self.app.geometry('980x660')
        self.app.deiconify()
        self.app.update_idletasks()
        self.app.update()
        self.workers[0].result.update(status='Distracted', confidence=None, is_valid=False,
                                       rule_based=True, valid_count=0)
        self.poll_once()
        self.app.update_idletasks()
        widgets = list(self.app.metric_labels.values()) + [self.app.status_label,
            self.app.confidence_label, self.app.progress_label, self.app.start_button, self.app.pause_button]
        for widget in widgets:
            self.assertTrue(widget.winfo_ismapped())
            self.assertEqual(widget.winfo_height(), widget.winfo_reqheight())


if __name__ == '__main__':
    unittest.main()
