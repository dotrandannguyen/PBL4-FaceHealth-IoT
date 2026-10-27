"""Camera-only attendance contracts without camera, models or data writes."""
import sys
import tkinter as tk
import types
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui_attendance import AttendanceApp, GREEN, AMBER, RED, result_presentation


class FakeWorker:
    loading = False
    error = ""

    def __init__(self):
        self.alive = True
        self.thread = types.SimpleNamespace(is_alive=lambda: self.alive)
        self.starts = 0
        self.closed = False
        self.accept = True
        self.current = {"seq": 1, "frame": np.zeros((480, 640, 3), dtype=np.uint8),
                        "info": {"state": "IDLE", "captured_count": 0}}

    def start_session(self):
        self.starts += 1
        return self.accept

    def snapshot(self):
        return self.current

    def close(self):
        self.closed = True


class AttendanceResultsTests(unittest.TestCase):
    def test_confirmed_actions_are_distinct(self):
        expected = {"CHECK-IN": ("CHECK-IN THÀNH CÔNG", GREEN),
                    "CHECK-OUT": ("CHECK-OUT THÀNH CÔNG", GREEN),
                    "DA_CHECK_OUT": ("HÔM NAY ĐÃ CHECK-OUT", AMBER)}
        for action, (title, color) in expected.items():
            with self.subTest(action=action):
                result = result_presentation({"attendance_action": action})
                self.assertEqual((result[0], result[2]), (title, color))

    def test_pending_and_failed_attempts_never_claim_success(self):
        for action in ("PENDING", "NOT_RECORDED", None):
            with self.subTest(action=action):
                title, _, color = result_presentation({"attendance_action": action})
                self.assertNotIn("THÀNH CÔNG", title)
                self.assertIn(color, (AMBER, RED))


class AttendanceWindowTests(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        try:
            self.app = AttendanceApp(worker=self.worker)
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")
        self.app.after_cancel(self.app._timer)
        self.app._timer = None
        self.app.update()
        self.app._snapshot = self.worker.current
        self.addCleanup(self.destroy_window)

    def destroy_window(self):
        try:
            for name in ("_timer", "_close_timer", "_space_release_timer"):
                timer = getattr(self.app, name)
                if timer is not None:
                    self.app.after_cancel(timer)
                    setattr(self.app, name, None)
            self.app.destroy()
        except tk.TclError:
            pass

    def messages(self):
        return "\n".join(self.app.canvas.itemcget(item, "text") for item in self.app.canvas.find_withtag("message"))

    def release_space(self):
        self.app._on_space_release()
        self.app.update_idletasks()

    def poll_once(self):
        if self.app._timer is not None:
            self.app.after_cancel(self.app._timer)
            self.app._timer = None
        self.app._poll()

    def test_idle_contains_only_camera_and_space_instruction(self):
        self.app._render(self.worker.current)
        self.assertEqual(self.app.winfo_children(), [self.app.canvas])
        self.assertEqual(self.messages(), "Nhấn Space để chấm công")
        self.assertEqual(len(self.app.canvas.find_withtag("camera")), 1)
        self.assertEqual(self.worker.starts, 0)

    def test_holding_space_does_not_repeat_after_result_returns_to_idle(self):
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 1)
        self.worker.current["info"] = {"state": "CAPTURING"}
        self.poll_once()
        self.worker.current["info"] = {"state": "IDLE"}
        self.poll_once()
        for _ in range(20):
            self.app._on_space_press()
        self.assertEqual(self.worker.starts, 1)
        self.release_space()
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 2)

    def test_repress_before_worker_acceptance_does_not_queue_duplicate(self):
        self.app._on_space_press()
        self.release_space()
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 1)

    def test_press_during_scan_is_ignored_without_queueing_for_later(self):
        self.worker.current["info"] = {"state": "PROCESSING"}
        self.app._on_space_press()
        self.worker.current["info"] = {"state": "IDLE"}
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 0)
        self.release_space()
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 1)

    def test_repeat_release_press_pair_before_idle_keeps_latch(self):
        self.app._defer_space_release = True
        self.app._on_space_press()
        self.app._on_space_release()
        self.app._on_space_press()
        self.assertTrue(self.app._space_down)
        self.assertIsNone(self.app._space_release_timer)
        self.assertEqual(self.worker.starts, 1)

    def test_windows_keyup_rearms_immediately_for_next_physical_press(self):
        self.app._defer_space_release = False
        self.app._on_space_press()
        self.worker.current["info"] = {"state": "CAPTURING"}
        self.poll_once()
        self.worker.current["info"] = {"state": "IDLE"}
        self.poll_once()
        self.app._on_space_release()
        self.assertFalse(self.app._space_down)
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 2)

    def test_failed_queue_request_requires_another_physical_press(self):
        self.worker.accept = False
        self.app._on_space_press()
        self.worker.accept = True
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 1)
        self.release_space()
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 2)

    def test_result_uses_frozen_frame_and_idle_restores_camera_instruction(self):
        frozen = np.full((480, 640, 3), 90, dtype=np.uint8)
        snapshot = dict(self.worker.current, result_frame=frozen, info={
            "state": "COMPLETED", "elapsed_in_state": 0,
            "completed_record": {"student_id": "NV001", "student_name": "Nguyễn Văn An", "attendance_action": "CHECK-OUT"}})
        self.app._render(snapshot)
        self.assertIn("CHECK-OUT THÀNH CÔNG", self.messages())
        self.assertIn("Nguyễn Văn An", self.messages())
        self.assertIn("5 giây", self.messages())
        snapshot["info"]["elapsed_in_state"] = 4.2
        self.app._render(snapshot)
        self.assertIn("1 giây", self.messages())
        snapshot["info"] = {"state": "IDLE"}
        self.app._render(snapshot)
        self.assertEqual(self.messages(), "Nhấn Space để chấm công")

    def test_lost_camera_clears_old_frame_with_same_sequence(self):
        self.app._render(self.worker.current)
        self.worker.current["frame"] = None
        self.app._render(self.worker.current)
        self.assertEqual(len(self.app.canvas.find_withtag("camera")), 0)
        self.assertIn("Đang kết nối camera", self.messages())
        self.app._on_space_press()
        self.assertEqual(self.worker.starts, 0)

    def test_minimum_size_keeps_result_inside_canvas(self):
        self.app.geometry("800x560")
        self.app.update()
        self.worker.current["info"] = {"state": "COMPLETED", "elapsed_in_state": 0,
            "completed_record": {"student_id": "NV001", "student_name": "Nguyễn Văn An", "attendance_action": "DA_CHECK_OUT"}}
        self.app._render(self.worker.current)
        for item in self.app.canvas.find_withtag("message"):
            x0, y0, x1, y1 = self.app.canvas.bbox(item)
            self.assertGreaterEqual(x0, 0)
            self.assertGreaterEqual(y0, 0)
            self.assertLessEqual(x1, self.app.canvas.winfo_width())
            self.assertLessEqual(y1, self.app.canvas.winfo_height())

    def test_close_releases_worker_and_waits_before_destroying_tk(self):
        self.app._on_space_release()
        self.app._on_close()
        self.assertTrue(self.worker.closed)
        self.assertIsNone(self.app._space_release_timer)
        self.assertTrue(self.app.winfo_exists())
        self.worker.alive = False
        self.app._wait_for_close()
        with self.assertRaises(tk.TclError):
            self.app.winfo_exists()


if __name__ == "__main__":
    unittest.main()
