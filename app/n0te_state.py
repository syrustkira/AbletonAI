"""Crash-safe primitives for N0TE's local product state."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_locks_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}


def path_lock(path: Path) -> threading.RLock:
    key = str(path.expanduser().resolve())
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def atomic_write_json(path: Path, value: Any, *, mode: int | None = None) -> None:
    """Write JSON completely or leave the previous file intact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path_lock(path):
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        tmp = Path(temporary)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            if mode is not None:
                os.chmod(tmp, mode)
            os.replace(tmp, path)
            # Persist the directory entry as well as file contents where the
            # platform supports directory fsync (POSIX/macOS/Linux).
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
