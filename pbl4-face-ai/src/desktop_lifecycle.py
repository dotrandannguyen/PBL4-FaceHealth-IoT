"""Graceful, exclusive camera-window switching without blocking Tk."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from uuid import uuid4


def install_close_listener(owner, close_callback):
    """A dashboard-owned child receives a stop file and releases its own resources."""
    value = os.environ.get('PBL4_UI_STOP_FILE')
    if not value:
        return
    stop_path = Path(value)

    def poll():
        if stop_path.exists():
            close_callback()
        else:
            owner.after(150, poll)
    owner.after(150, poll)


class CameraModuleLauncher:
    """Launch the next camera module only after the current child has exited."""
    def __init__(self, owner, python, base_dir, env, on_error):
        self.owner, self.python = owner, python
        self.base_dir, self.env, self.on_error = Path(base_dir), dict(env), on_error
        self.run_dir = self.base_dir.parent / '.pbl4-run' / 'desktop'
        self.active = None
        self.pending = None
        self.closing = False
        self.timer = None
        self.close_callback = None

    def launch(self, script, title):
        if self.closing:
            return
        if self.active and self.pending is None and self.active['script'] == script and self.active['process'].poll() is None:
            return
        self.pending = script, title
        if self.active:
            self._request_stop()
        self._poll()

    def _request_stop(self):
        self.active['stop'].touch(exist_ok=True)

    def _poll(self):
        if self.timer is not None:
            self.owner.after_cancel(self.timer)
            self.timer = None
        if self.active:
            process = self.active['process']
            if process.poll() is None:
                self.timer = self.owner.after(100, self._poll)
                return
            active, self.active = self.active, None
            active['out'].close()
            active['err'].close()
            active['stop'].unlink(missing_ok=True)
            if process.returncode and not self.closing:
                self.on_error(active['title'], str(active['error_path']))
        if self.closing:
            if self.close_callback:
                callback, self.close_callback = self.close_callback, None
                callback()
            return
        if self.pending:
            script, title = self.pending
            self.pending = None
            self.run_dir.mkdir(parents=True, exist_ok=True)
            prefix = self.run_dir / (Path(script).stem + '-' + uuid4().hex[:10])
            stop = prefix.with_suffix('.stop')
            error_path = prefix.with_suffix('.err.log')
            output = prefix.with_suffix('.out.log').open('wb')
            error = error_path.open('wb')
            env = dict(self.env, PBL4_UI_STOP_FILE=str(stop))
            try:
                process = subprocess.Popen([self.python, '-u', '-B', script], cwd=self.base_dir,
                                           env=env, stdout=output, stderr=error,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            except Exception:
                output.close()
                error.close()
                self.on_error(title, str(error_path))
                return
            self.active = dict(process=process, script=script, title=title, stop=stop,
                               out=output, err=error, error_path=error_path)
            self.timer = self.owner.after(100, self._poll)

    def close(self, callback):
        self.closing, self.pending, self.close_callback = True, None, callback
        if self.active:
            self._request_stop()
        self._poll()
