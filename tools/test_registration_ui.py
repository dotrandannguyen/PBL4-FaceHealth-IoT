"""Headless registration flow checks; no Tk window, camera, model or database.

Exercise the real GUI callbacks with lightweight variables and an immediate
worker. The enrollment store is fake so every sample/job stays in memory.
"""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1] / 'pbl4-face-ai'
sys.path.insert(0, str(ROOT))
with patch.dict(sys.modules, {'src.face_engine': types.SimpleNamespace(FaceEngine=object)}):
    import gui_register


class Variable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class ImmediateWorker:
    def __init__(self):
        self.errors = []

    def submit(self, work, success, failure):
        try:
            result = work()
        except Exception as error:
            self.errors.append(error)
            failure(error)
        else:
            success(result)


class MemoryEnrollment:
    def __init__(self):
        self.jobs = []
        self.state = 'completed'
        self.stage = Mock(side_effect=self._stage)
        self.pending = Mock(side_effect=lambda: [(None, job) for job in self.jobs])
        self.retry = Mock(side_effect=self._retry)
        self.refresh = Mock()
        self.employees = Mock(return_value=[dict(id=1, name='Official employee', n_images=0)])
        self.revision = Mock(return_value='a' * 64)

    def _stage(self, sid, name, samples, revision):
        job = dict(id='new-registration', employee_id=1, action='replace')
        self.jobs.append(job)
        return job['id']

    def _retry(self, job_id=None):
        return dict(completed=int(self.state == 'completed'), pending=0,
                    errors=[], jobs={job_id: self.state})


def owner():
    label = 'SV001 — Official employee'
    app = types.SimpleNamespace(
        sync_busy=False, is_capturing=False, engine=object(),
        employees={label: dict(id=1, name='Official employee', n_images=0)},
        employee_var=Variable(label), id_var=Variable('SV001'),
        name_var=Variable('Official employee'), pending_action=None,
        registration_job=None, registration_state=None,
        capture_done=True, samples_collected=[object() for _ in range(5)],
        embeddings_collected=[object() for _ in range(5)],
        enrollment_revision='a' * 64, hint_var=Variable(),
        status_var=Variable(), conf_var=Variable(), progress_var=Variable(0),
        camera_ready=True, store=MemoryEnrollment(), io=ImmediateWorker(),
        _update_controls=Mock(), _load_employees=Mock(),
        _begin_capture=Mock(), _build_step_indicators=Mock(),
    )
    app._save_registration = types.MethodType(gui_register.RegisterApp._save_registration, app)
    return app


class SaveRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.info = self.enterContext(patch.object(gui_register.messagebox, 'showinfo'))
        self.enterContext(patch.object(gui_register.messagebox, 'showwarning'))
        self.enterContext(patch.object(gui_register.messagebox, 'askyesno', return_value=False))

    def test_success_only_after_selected_job_completes_despite_unrelated_pending(self):
        app = owner()
        app.store.retry.side_effect = lambda job_id: dict(
            completed=1, pending=4, errors=['Unrelated employee offline'],
            jobs={job_id: 'completed'},
        )
        original_samples = list(app.samples_collected)
        app._save_registration()
        app.store.stage.assert_called_once_with('SV001', 'Official employee', original_samples, 'a' * 64)
        app.store.retry.assert_called_once_with(job_id='new-registration')
        self.assertIsNone(app.registration_job)
        self.assertEqual(app.samples_collected, [])
        self.assertEqual(app.embeddings_collected, [])
        self.assertEqual(app.progress_var.get(), 100)
        self.assertFalse(app.sync_busy)
        self.info.assert_called_once()
        app._load_employees.assert_called_once_with(keep_message=True)

    def test_incomplete_states_preserve_captured_samples_and_never_claim_success(self):
        for state in ('saved', 'conflict', 'pending'):
            with self.subTest(state=state):
                self.info.reset_mock()
                app = owner()
                original_samples = list(app.samples_collected)
                app.store.retry.side_effect = lambda job_id, current=state: dict(
                    completed=1, pending=1, errors=[],
                    jobs={job_id: current, 'unrelated-job': 'completed'},
                )
                app._save_registration()
                self.assertEqual(app.registration_job, 'new-registration')
                self.assertEqual(app.samples_collected, original_samples)
                self.assertEqual(len(app.embeddings_collected), 5)
                self.assertFalse(app.sync_busy)
                self.info.assert_not_called()
                app._load_employees.assert_not_called()
                self.assertNotEqual(app.progress_var.get(), 100)
                if state == 'saved':
                    self.assertIn('đã lưu', app.hint_var.get())
                    self.assertIn('chưa cập nhật', app.hint_var.get())
                elif state == 'conflict':
                    self.assertIn('đã thay đổi', app.hint_var.get())
                else:
                    self.assertIn('Chưa lưu', app.hint_var.get())

    def test_worker_failure_after_stage_retries_same_job_without_staging_again(self):
        app = owner()
        original_samples = list(app.samples_collected)
        app.store.retry.side_effect = [
            OSError('Connection lost after staging'),
            dict(completed=1, pending=0, errors=[], jobs={'new-registration': 'completed'}),
        ]
        app._save_registration()
        self.assertEqual(app.registration_job, 'new-registration')
        self.assertEqual(app.samples_collected, original_samples)
        self.info.assert_not_called()
        app._save_registration()
        app.store.stage.assert_called_once()
        self.assertEqual(app.store.retry.call_count, 2)
        self.assertTrue(all(call.kwargs == {'job_id': 'new-registration'}
                            for call in app.store.retry.call_args_list))
        self.info.assert_called_once()

    def test_resume_rejects_delete_missing_and_different_employee_jobs(self):
        for job in (
            dict(id='existing-job', employee_id=1, action='delete'),
            dict(id='existing-job', employee_id=2, action='replace'),
            None,
        ):
            with self.subTest(job=job):
                self.info.reset_mock()
                app = owner()
                app.registration_job = 'existing-job'
                app.store.jobs = [job] if job is not None else []
                app._save_registration()
                app.store.stage.assert_not_called()
                app.store.retry.assert_not_called()
                self.info.assert_not_called()
                self.assertEqual(len(app.samples_collected), 5)
                self.assertFalse(app.sync_busy)
                self.assertEqual(len(app.io.errors), 1)

    def test_save_is_not_submitted_twice_while_worker_is_busy(self):
        app = owner()
        app.sync_busy = True
        app._save_registration()
        app.store.stage.assert_not_called()
        app.store.retry.assert_not_called()


class StartRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.info = self.enterContext(patch.object(gui_register.messagebox, 'showinfo'))
        self.warning = self.enterContext(patch.object(gui_register.messagebox, 'showwarning'))
        self.question = self.enterContext(patch.object(gui_register.messagebox, 'askyesno', return_value=False))

    def ready(self):
        app = owner()
        app.capture_done = False
        app.samples_collected.clear()
        app.embeddings_collected.clear()
        return app

    def test_start_rejects_employee_missing_from_loaded_roster(self):
        app = self.ready()
        app.employees = {}
        gui_register.RegisterApp._start_register(app)
        self.warning.assert_called_once()
        app.store.refresh.assert_not_called()
        app._begin_capture.assert_not_called()
        app.store.retry.assert_not_called()

    def test_start_rechecks_current_database_and_rejects_removed_employee(self):
        app = self.ready()
        app.store.employees.return_value = []
        gui_register.RegisterApp._start_register(app)
        app.store.refresh.assert_called_once()
        app._begin_capture.assert_not_called()
        app.store.stage.assert_not_called()
        app.store.retry.assert_not_called()
        self.assertFalse(app.sync_busy)
        self.assertIn('Chưa bắt đầu', app.hint_var.get())

    def test_start_resumes_pending_replacement_without_camera_or_new_capture(self):
        app = self.ready()
        app.camera_ready = False
        app.store.jobs = [dict(id='resumable-registration', employee_id=1, action='replace')]
        gui_register.RegisterApp._start_register(app)
        app.store.stage.assert_not_called()
        app.store.retry.assert_called_once_with(job_id='resumable-registration')
        app._begin_capture.assert_not_called()
        self.info.assert_called_once()

    def test_preflight_never_resumes_pending_deletion_as_registration(self):
        app = self.ready()
        app.store.jobs = [dict(id='pending-delete', employee_id=1, action='delete')]
        gui_register.RegisterApp._start_register(app)
        app.store.stage.assert_not_called()
        app.store.retry.assert_not_called()
        app._begin_capture.assert_not_called()
        self.info.assert_not_called()
        self.assertIn('xóa', app.hint_var.get())

    def test_preflight_takes_official_name_and_revision_before_capture(self):
        app = self.ready()
        app.store.employees.return_value = [dict(id=1, name='Updated official name', n_images=0)]
        gui_register.RegisterApp._start_register(app)
        self.assertEqual(app.id_var.get(), 'SV001')
        self.assertEqual(app.name_var.get(), 'Updated official name')
        self.assertEqual(app.enrollment_revision, 'a' * 64)
        app._begin_capture.assert_called_once()
        app.store.retry.assert_not_called()
        self.question.assert_not_called()

    def test_existing_faces_require_confirmation_before_new_capture(self):
        app = self.ready()
        app.store.employees.return_value = [dict(id=1, name='Official employee', n_images=5)]
        gui_register.RegisterApp._start_register(app)
        self.question.assert_called_once()
        app._begin_capture.assert_not_called()
        app.store.stage.assert_not_called()
        self.assertFalse(app.sync_busy)


class CameraFreshnessTests(unittest.TestCase):
    def ready(self):
        return types.SimpleNamespace(
            running=True, camera_ready=False, last_frame_time=None,
            pump=types.SimpleNamespace(snapshot_with_timestamp=Mock()),
            _process_frame=Mock(return_value=object()), _show_frame=Mock(),
            _poll_frame=Mock(),
            ready_timer=4, progress_var=Variable(50), hint_var=Variable(),
            is_capturing=True, _canvas_image=7, _current_photo=object(),
            cam_canvas=types.SimpleNamespace(itemconfigure=Mock()),
            after=Mock(return_value='next-poll'),
        )

    def test_duplicate_camera_snapshot_does_not_advance_pose_processing(self):
        app = self.ready()
        frame, faces = object(), [object()]
        app.pump.snapshot_with_timestamp.side_effect = [
            (frame, faces, 100.0), (frame, faces, 100.0), (frame, faces, 101.0),
        ]
        for _ in range(3):
            gui_register.RegisterApp._poll_frame(app)
        self.assertEqual(app._process_frame.call_count, 2)
        self.assertEqual(app._show_frame.call_count, 2)
        self.assertEqual(app.last_frame_time, 101.0)
        self.assertTrue(app.camera_ready)
        self.assertEqual(app.after.call_count, 3)

    def test_missing_fresh_frame_clears_preview_and_pose_readiness(self):
        app = self.ready()
        app.camera_ready = True
        app.pump.snapshot_with_timestamp.return_value = (None, [], None)
        gui_register.RegisterApp._poll_frame(app)
        self.assertFalse(app.camera_ready)
        self.assertEqual(app.ready_timer, 0)
        self.assertEqual(app.progress_var.get(), 0)
        self.assertIsNone(app._current_photo)
        app.cam_canvas.itemconfigure.assert_called_once_with(7, image='')
        app._process_frame.assert_not_called()
        app.after.assert_called_once()


if __name__ == '__main__':
    unittest.main()
