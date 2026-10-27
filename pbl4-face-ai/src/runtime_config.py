"""Load local project configuration without overriding explicit environment values."""

import os
import sys
from pathlib import Path


def load_environment():
    if sys.platform == 'win32':
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8', errors='replace')
    os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[2] / '.pbl4-run/cache/matplotlib'))
    path = Path(__file__).resolve().parents[2] / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if key.replace("_", "").isalnum() and key[0].isalpha():
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                os.environ.setdefault(key, value)
