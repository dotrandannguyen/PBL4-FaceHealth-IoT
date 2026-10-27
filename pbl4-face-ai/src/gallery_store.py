"""Cross-process gallery writes and independent reader cache invalidation."""
from contextlib import contextmanager
import os
from pathlib import Path
import pickle
import threading
import time

from .atomic_storage import atomic_write

_guards = {}
_guards_lock = threading.Lock()


@contextmanager
def gallery_lock(path, timeout=30):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _guards_lock:
        guard = _guards.setdefault(str(path).casefold() if os.name == 'nt' else str(path), threading.RLock())
    with guard, path.with_name(path.name + '.lock').open('a+b', buffering=0) as stream:
        # Reading byte zero before acquiring its Windows lock can itself raise
        # PermissionError while another process holds the lock.
        deadline = time.monotonic() + timeout
        acquired = False
        try:
            while not acquired:
                try:
                    if os.fstat(stream.fileno()).st_size == 0:
                        stream.write(b'\0')
                        stream.flush()
                    stream.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Gallery is busy')
                    time.sleep(.01)
            yield
        finally:
            if acquired:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_UN)


def replace_from_loader(path, loader):
    # Lock before fetching, not just before saving: a slower old fetch must not
    # overwrite a newer refresh after a registration/deletion.
    with gallery_lock(path):
        gallery = loader()
        if not isinstance(gallery, dict):
            raise ValueError('Gallery must be a dictionary')
        atomic_write(path, pickle.dumps(gallery, protocol=pickle.HIGHEST_PROTOCOL))
        return gallery


def update_gallery(path, transform):
    def load_and_update():
        try:
            with Path(path).open('rb') as stream:
                gallery = pickle.load(stream)
        except FileNotFoundError:
            gallery = {}
        if not isinstance(gallery, dict):
            raise ValueError('Gallery must be a dictionary')
        return transform(gallery)
    return replace_from_loader(path, load_and_update)


class GalleryCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._signature = None
        self._gallery = {}

    def load(self, path, force_reload=False):
        path = Path(path)
        with self._lock:
            try:
                stat = path.stat()
            except FileNotFoundError:
                self._gallery, self._signature = {}, None
                return {}
            signature = (str(path.resolve()), stat.st_mtime_ns, stat.st_size, stat.st_ino)
            if not force_reload and signature == self._signature:
                return self._gallery
            with path.open('rb') as stream:
                gallery = pickle.load(stream)
            if not isinstance(gallery, dict):
                raise ValueError('Invalid gallery file')
            self._gallery, self._signature = gallery, signature
            return gallery
