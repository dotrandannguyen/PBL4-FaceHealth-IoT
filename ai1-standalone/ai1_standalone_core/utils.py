"""Path and console helpers for standalone data safety."""

import re
import sys
from pathlib import Path


ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_employee_id(value):
    if not isinstance(value, str) or not value or not ID_PATTERN.fullmatch(value):
        raise ValueError("Employee ID may contain only ASCII letters, digits, '_' and '-'.")
    if value in {".", ".."}:
        raise ValueError("Employee ID is not a valid path component.")
    if value.upper() == "UNKNOWN":
        raise ValueError("UNKNOWN is reserved for unregistered faces.")
    return value


def safe_identity_path(root, identity):
    identity = validate_employee_id(identity)
    root = Path(root).resolve()
    candidate = root / identity
    if candidate.is_symlink():
        raise ValueError("Employee data folders must not be symbolic links.")
    path = candidate.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Employee ID resolves outside the standalone data directory.") from exc
    return path


def configure_console():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


def ascii_display(value):
    """Make Vietnamese names readable with OpenCV's built-in ASCII font."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).encode(
        "ascii", "replace"
    ).decode("ascii")
