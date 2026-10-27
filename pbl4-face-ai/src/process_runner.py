"""Own only dashboard-started children and stop them when the window closes."""
import os
import subprocess
import threading


class ProcessRunner:
    def __init__(self):
        self.lock = threading.Lock()
        self.closed = False
        self.active = set()

    def run(self, command, **kwargs):
        with self.lock:
            if self.closed:
                raise RuntimeError('Dashboard is closed')
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=flags, **kwargs)
            self.active.add(process)
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=.25)
                    return subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
                except subprocess.TimeoutExpired:
                    with self.lock:
                        closed = self.closed
                    if closed:
                        process.kill()
        finally:
            with self.lock:
                self.active.discard(process)

    def close(self):
        with self.lock:
            self.closed = True
            for process in self.active:
                if process.poll() is None:
                    try:
                        process.terminate()
                    except OSError:
                        pass
