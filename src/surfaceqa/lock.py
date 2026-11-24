"""One build of a QA directory at a time, whichever program starts it."""

import json
import os
from contextlib import contextmanager
from pathlib import Path

from surfaceqa.layout import read_json, replace_text

LOCK_FILE = "build.lock"


class Busy(Exception):
    """Another build of this QA directory is running."""


def _alive(pid) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # it exists and belongs to someone else
        return True
    return True


def building(qa_dir: Path) -> bool:
    """Whether a build that is still alive holds this QA directory."""
    stored = read_json(Path(qa_dir) / LOCK_FILE)
    return isinstance(stored, dict) and _alive(stored.get("pid"))


def release(qa_dir: Path) -> None:
    (Path(qa_dir) / LOCK_FILE).unlink(missing_ok=True)


@contextmanager
def build_lock(qa_dir: Path):
    """Hold the QA directory for a build; raises Busy when a live build has it."""
    qa_dir = Path(qa_dir)
    if building(qa_dir):
        raise Busy(str(qa_dir))
    qa_dir.mkdir(parents=True, exist_ok=True)
    replace_text(qa_dir / LOCK_FILE, json.dumps({"pid": os.getpid()}))
    try:
        yield
    finally:
        release(qa_dir)
