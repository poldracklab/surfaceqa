"""A build started from the start page: the `build` command as a child process."""

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from surfaceqa import lock, progress

LOG_FILE = "build.log"
BLANK = {"stage": None, "done": 0, "total": 0, "problems": [], "cohort_failed": False}


@dataclass
class Job:
    out: Path
    process: subprocess.Popen
    cancelled: bool = False


def default_jobs() -> int:
    """Subjects built side by side: half the cores, so the machine stays usable."""
    return max(1, (os.cpu_count() or 1) // 2)


def _command(sources: list[Path], out: Path, jobs: int) -> list[str]:
    return [sys.executable, "-m", "surfaceqa.cli", "build", *map(str, sources),
            "--out", str(out), "--jobs", str(jobs), "--progress"]


def start(sources: list[Path], out: Path, jobs: int) -> Job:
    """Start building these sources into `out`; returns at once."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / progress.STATUS_FILE).unlink(missing_ok=True)  # an earlier build's, not this one's
    with open(out / LOG_FILE, "w") as log:
        process = subprocess.Popen(_command(sources, out, jobs), stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
    return Job(out, process)


def _log_tail(out: Path, lines: int = 5) -> list[str]:
    try:
        return (out / LOG_FILE).read_text(errors="replace").splitlines()[-lines:]
    except OSError:
        return []


def _state(job: Job, stored: dict) -> str:
    if job.process.poll() is None:
        return "running"
    if stored.get("state") == "done":
        return "done"
    return "cancelled" if job.cancelled else "stopped"


def status(job: Job) -> dict:
    """How far the job has got: running, done, cancelled, or stopped (it ended by itself
    without finishing, with the last lines of its log)."""
    stored = progress.read(job.out) or {}
    state = _state(job, stored)
    answer = {**BLANK, **stored, "state": state, "out": str(job.out)}
    return {**answer, "log_tail": _log_tail(job.out)} if state == "stopped" else answer


def _kill(job: Job, how: int) -> None:
    try:
        os.killpg(job.process.pid, how)
    except ProcessLookupError:
        pass


def cleanup(job: Job) -> None:
    """Leave nothing of the job behind: no worker, no lock, no half-written file. For a job
    that was cancelled or that died by itself."""
    _kill(job, signal.SIGKILL)  # workers outlive a build that is killed
    job.process.wait()
    lock.release(job.out)
    _sweep(job.out)


def cancel(job: Job) -> None:
    """Stop the build and its workers at once. What it finished stays."""
    if job.process.poll() is None:
        job.cancelled = True
        _kill(job, signal.SIGTERM)
        try:
            job.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    cleanup(job)


def _sweep(out: Path) -> None:
    """Remove what the stopped build was in the middle of writing."""
    for where in ("", "cohort/", "subjects/*/", "subjects/*/runs/*/"):
        for partial in out.glob(f"{where}.*.partial"):
            partial.unlink(missing_ok=True)
