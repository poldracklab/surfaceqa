"""One build of a QA directory at a time, whichever program starts it.

The lock is an operating-system lock on a file in the QA directory, so it cannot be taken by
two builders at once and it ends with the build even when the build is killed.
"""

import json
import os
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # no such locks on this system: builds are not kept apart there
    fcntl = None

LOCK_FILE = "build.lock"


class Busy(Exception):
    """Another build of this QA directory is running."""


def _same_file(handle: int, path: Path) -> bool:
    try:
        return os.fstat(handle).st_ino == os.stat(path).st_ino
    except FileNotFoundError:
        return False


def _lock(handle: int) -> bool:
    if fcntl is None:
        return True
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _hold(path: Path) -> int | None:
    """Take the lock; an open file handle, or None when another build has it."""
    while True:
        handle = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
        if not _lock(handle):
            os.close(handle)
            return None
        if _same_file(handle, path):
            return handle
        os.close(handle)  # its last holder removed the file as we opened it: take the new one


def _let_go(path: Path, handle: int) -> None:
    path.unlink(missing_ok=True)  # before unlocking, so nobody is left holding a removed file
    os.close(handle)


def building(qa_dir: Path) -> bool:
    """Whether a build holds this QA directory. A lock file nobody holds is removed."""
    path = Path(qa_dir) / LOCK_FILE
    if not path.exists():
        return False
    handle = _hold(path)
    if handle is None:
        return True
    _let_go(path, handle)
    return False


def release(qa_dir: Path) -> None:
    """Remove what a build that was killed left behind; a lock that is held stays."""
    building(qa_dir)


@contextmanager
def build_lock(qa_dir: Path):
    """Hold the QA directory for a build; raises Busy when another build has it."""
    path = Path(qa_dir) / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = _hold(path)
    if handle is None:
        raise Busy(str(qa_dir))
    try:
        os.ftruncate(handle, 0)
        os.write(handle, json.dumps({"pid": os.getpid()}).encode())
        yield
    finally:
        _let_go(path, handle)
