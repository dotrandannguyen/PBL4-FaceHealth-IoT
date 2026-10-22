"""Registration gates and UI state without a model, camera, Web or database."""
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.registration_capture import assess_frame, capture_sample, render_guide, guide_bounds

with patch.dict(sys.modules, {'src.face_engine': types.SimpleNamespace(FaceEngine=object)}):
    import gui_register


class Variable:
    def __init__(self, value=None):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


def sample_face(pose='frontal', bbox=(220, 105, 420, 385)):
    nose = {'frontal': (320, 224), 'left': (310, 224), 'right': (330, 224),
            'up': (320, 210), 'down': (320, 240)}[pose]
    return types.SimpleNamespace(
        bbox=np.array(bbox), kps=np.array([(280, 180), (360, 180), nose, (290, 260), (350, 260)]),
        det_score=.99, embedding=np.ones(512, dtype=np.float32))


class CaptureGateTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.random.default_rng(123).integers(65, 195, (480, 640, 3), dtype=np.uint8)

    def test_all_five_valid_poses_pass_but_wrong_pose_is_red(self):
        for pose in ('frontal', 'left', 'right', 'up', 'down'):
            self.assertTrue(assess_frame(self.frame, [sample_face(pose)], pose).ready, pose)
        self.assertFalse(assess_frame(self.frame, [sample_face()], 'left').ready)

    def test_capture_requires_one_centered_face_at_the_right_distance(self):
        cases = [([], 'No face'), ([sample_face(), sample_face()], 'One person'),
                 ([sample_face(bbox=(290, 200, 350, 290))], 'Move closer'),
                 ([sample_face(bbox=(160, 40, 480, 470))], 'Move back'),
                 ([sample_face(bbox=(20, 105, 220, 385))], 'Center')]
        for faces, reason in cases:
            result = assess_frame(self.frame, faces, 'frontal')
            self.assertFalse(result.ready)
            self.assertIn(reason, result.short_message)

    def test_blur_darkness_bad_confidence_and_bad_landmarks_block_capture(self):
        face = sample_face()
        self.assertFalse(assess_frame(np.zeros_like(self.frame), [face]).ready)
        self.assertFalse(assess_frame(np.full_like(self.frame, 128), [face]).ready)
        face.det_score = float('nan')
        self.assertFalse(assess_frame(self.frame, [face]).ready)
        face.det_score = .99
        face.kps = None
        self.assertFalse(assess_frame(self.frame, [face]).ready)

    def test_manual_and_auto_capture_share_gate_and_keep_original_storage_format(self):
        with patch('src.enrollment_samples.sample_from_frame') as encode:
            with self.assertRaises(ValueError):
                capture_sample(self.frame, [sample_face(bbox=(0, 0, 10, 10))], 'frontal')
            encode.assert_not_called()
        sample, crop = capture_sample(self.frame, [sample_face()], 'frontal')
        self.assertEqual(set(sample), {'pose', 'image', 'vector'})
        self.assertEqual(sample['vector'].shape, (512,))
        self.assertAlmostEqual(float(np.linalg.norm(sample['vector'])), 1., places=5)
        self.assertEqual(crop.shape, (280, 200, 3))
        with Image.open(io.BytesIO(sample['image'])) as original:
            self.assertEqual(original.size, (640, 480))

    def test_guide_is_centered_and_rendering_does_not_mutate_input(self):
        original = self.frame.copy()
        x1, y1, x2, y2 = guide_bounds(self.frame.shape)
        self.assertAlmostEqual((x1 + x2) / 2, 320, delta=1)
        rendered = render_guide(self.frame, [sample_face()], assess_frame(self.frame, [sample_face()]))
        self.assertEqual(rendered.shape, self.frame.shape)
        np.testing.assert_array_equal(self.frame, original)
        self.assertFalse(np.array_equal(rendered, original))


def controls_owner(count=0):
    person = dict(id=1, name='Nguyễn Văn A')
    app = types.SimpleNamespace(
        sync_busy=False, is_capturing=False, sample_busy=False,
        engine=object(), camera_ready=True, employees={'selected': person},
        employee_var=Variable('selected'), id_var=Variable('SV001'), name_var=Variable(person['name']),
        registration_conflict=False, pending_action=None, registration_job=None,
        pending_by_employee={}, capture_done=count == 5, samples_collected=[object()] * count,
        btn_start=Mock(), btn_save=Mock(), btn_capture=Mock(), employee_combo=Mock(),
        btn_refresh=Mock(), btn_reset=Mock())
    return app


class RegistrationUiStateTests(unittest.TestCase):
    def test_save_requires_all_samples_and_canonical_employee_information(self):
        for count in range(5):
            app = controls_owner(count)
            gui_register.RegisterApp._update_controls(app)
            self.assertEqual(app.btn_save.configure.call_args.kwargs['state'], 'disabled')
        app = controls_owner(5)
        gui_register.RegisterApp._update_controls(app)
        self.assertEqual(app.btn_save.configure.call_args.kwargs['state'], 'normal')
        app.name_var.set('')
        gui_register.RegisterApp._update_controls(app)
        self.assertEqual(app.btn_save.configure.call_args.kwargs['state'], 'disabled')
        app.name_var.set('Different identity')
        gui_register.RegisterApp._update_controls(app)
        self.assertEqual(app.btn_save.configure.call_args.kwargs['state'], 'disabled')

    def test_busy_deleting_or_conflicted_batch_cannot_be_saved(self):
        for key, value in [('sync_busy', True), ('is_capturing', True), ('sample_busy', True),
                           ('registration_conflict', True), ('pending_action', 'delete')]:
            app = controls_owner(5)
            setattr(app, key, value)
            gui_register.RegisterApp._update_controls(app)
            self.assertEqual(app.btn_save.configure.call_args.kwargs['state'], 'disabled', key)

    def test_fifth_capture_waits_for_explicit_save(self):
        app = controls_owner(5)
        app._save_registration = Mock()
        app._update_controls = Mock()
        app.progress_var, app.hint_var, app.status_var = Variable(80), Variable(), Variable()
        gui_register.RegisterApp._finalize_registration(app)
        self.assertFalse(app.is_capturing)
        self.assertTrue(app.capture_done)
        self.assertEqual(app.progress_var.get(), 100)
        app._save_registration.assert_not_called()

    def test_resume_uses_five_durable_samples_even_without_camera_or_model(self):
        app = controls_owner()
        app.registration_job = 'pending-batch'
        app.pending_by_employee = {1: {'samples': [{}] * 5}}
        app.camera_ready, app.engine = False, None
        gui_register.RegisterApp._update_controls(app)
        self.assertEqual(app.btn_save.configure.call_args.kwargs['state'], 'normal')
        self.assertEqual(app.btn_start.configure.call_args.kwargs['state'], 'disabled')

    def test_camera_module_switch_waits_for_writes_then_closes_without_discard_prompt(self):
        app = types.SimpleNamespace(running=True, sync_busy=True, status_var=Variable(),
            samples_collected=[object()], registration_job=None, frame_timer='preview-timer',
            after=Mock(), after_cancel=Mock(), pump=Mock(), io=Mock(), _finish_close=Mock())
        app.on_close = types.MethodType(gui_register.RegisterApp.on_close, app)
        with patch.object(gui_register.messagebox, 'askyesno') as question:
            app.on_close(from_dashboard=True)
            self.assertTrue(app.running)
            app.pump.close.assert_not_called()
            retry = app.after.call_args.args[1]
            app.sync_busy = False
            retry()
            self.assertFalse(app.running)
            app.pump.close.assert_called_once()
            app.io.close.assert_called_once()
            app._finish_close.assert_called_once()
            question.assert_not_called()

    def test_camera_release_finishes_before_destroy_without_joining_ui_thread(self):
        app = types.SimpleNamespace(pump=Mock(), after=Mock(), destroy=Mock(), _finish_close=Mock())
        app.pump.thread.is_alive.return_value = True
        gui_register.RegisterApp._finish_close(app)
        app.destroy.assert_not_called()
        app.pump.thread.join.assert_not_called()
        app.pump.thread.is_alive.return_value = False
        gui_register.RegisterApp._finish_close(app)
        app.destroy.assert_called_once()

    def test_five_real_capture_callbacks_collect_paired_samples_before_save(self):
        app = controls_owner()
        app.current_step, app.session_token = 0, 1
        app.samples_collected, app.embeddings_collected, app._sample_crops = [], [], []
        app.is_capturing = True
        app.ready_timer, app.flash_timer = 0, 0
        app.progress_var, app.conf_var, app.hint_var, app.status_var = Variable(0), Variable(), Variable(), Variable()
        app._update_controls, app._build_step_indicators, app._refresh_thumbnails = Mock(), Mock(), Mock()
        app._save_registration = Mock()
        app._finalize_registration = types.MethodType(gui_register.RegisterApp._finalize_registration, app)
        def submit(work, success, failure):
            try:
                result = work()
            except Exception as error:
                failure(error)
                raise
            success(result)
        app.io = types.SimpleNamespace(submit=submit)
        frame = np.random.default_rng(123).integers(65, 195, (480, 640, 3), dtype=np.uint8)
        for pose in ('frontal', 'left', 'right', 'up', 'down'):
            gui_register.RegisterApp._do_capture(app, frame, [sample_face(pose)])
        self.assertEqual([sample['pose'] for sample in app.samples_collected],
                         ['frontal', 'left', 'right', 'up', 'down'])
        self.assertEqual(len(app._sample_crops), 5)
        self.assertTrue(app.capture_done)
        self.assertFalse(app.is_capturing)
        self.assertFalse(app.sample_busy)
        app._save_registration.assert_not_called()


class NativeRegistrationLayoutTests(unittest.TestCase):
    def test_primary_controls_fit_small_window_and_preview_keeps_aspect_ratio(self):
        patches = [patch.object(gui_register.RegisterApp, name) for name in
                   ('_load_engine_async', '_open_webcam', '_poll_frame', '_load_employees')]
        for replacement in patches:
            replacement.start()
            self.addCleanup(replacement.stop)
        try:
            app = gui_register.RegisterApp()
        except gui_register.tk.TclError as error:
            self.skipTest(f'Native Tk unavailable: {error}')
        self.addCleanup(app.destroy)
        self.addCleanup(app.io.close)
        for width, height in ((1180, 760), (1000, 700)):
            app.geometry(f'{width}x{height}')
            app.deiconify()
            app.update()
            for button in (app.btn_start, app.btn_capture, app.btn_save, app.btn_reset):
                self.assertTrue(button.winfo_ismapped())
                top = button.winfo_rooty() - app.winfo_rooty()
                self.assertGreaterEqual(top, 0)
                self.assertLess(top + button.winfo_height(), height - 25)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        app._show_frame(frame)
        self.assertAlmostEqual(app._current_photo.width() / app._current_photo.height(), 4 / 3, places=2)
        self.assertEqual(len(app._thumbnail_widgets), 5)
        self.assertEqual(app.btn_save['state'], 'disabled')


if __name__ == '__main__':
    unittest.main()
