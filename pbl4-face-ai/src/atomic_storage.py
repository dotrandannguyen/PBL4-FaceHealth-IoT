"""Replace local artifacts atomically; never truncate an active gallery."""

import os
import pickle
import tempfile
import time
from pathlib import Path


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        deadline = time.monotonic() + 2
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # Windows readers/virus scanners may briefly retain a handle
                # without delete sharing. Never truncate the active artifact.
                if os.name != 'nt' or time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_gallery(path, gallery):
    try:
        from .gallery_store import replace_from_loader
    except ImportError:  # Legacy CLI imports this module without a package prefix.
        from src.gallery_store import replace_from_loader
    replace_from_loader(path, lambda: gallery)
