import json
import os
import shutil
import time

import pytest

from surfaceqa import jobs
from surfaceqa.lock import building
from tests.synth import write_subject


def _wait(job, until, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status = jobs.status(job)
        if until(status):
            return status
        time.sleep(0.05)
    raise AssertionError(f"timed out: {jobs.status(job)}")


def _finished(status):
    return status["state"] != "running"


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture
def many(tmp_path):
    """A source with enough subjects that a build can be stopped in the middle."""
    for i in range(12):
        write_subject(tmp_path / "study", name=f"sub-{i:02d}")
    return tmp_path / "study"


def test_default_jobs_is_at_least_one():
    assert 1 <= jobs.default_jobs() <= max(1, (os.cpu_count() or 1) // 2)


def test_a_job_builds_the_qa_directory(synth_sources, tmp_path):
    out = tmp_path / "new" / "qa"
    job = jobs.start(synth_sources, out, 1)
    first = jobs.status(job)
    assert first["state"] == "running" and first["out"] == str(out)
    status = _wait(job, _finished)
    assert status["state"] == "done" and status["total"] == 2 and status["problems"] == []
    assert (out / "index.html").is_file() and not building(out)
    assert not _alive(job.process.pid)


def test_status_of_an_earlier_build_is_not_shown_for_a_new_job(synth_sources, tmp_path, many):
    out = tmp_path / "qa"
    _wait(jobs.start(synth_sources, out, 1), _finished)
    job = jobs.start([many], out, 1)
    status = jobs.status(job)
    assert status["state"] == "running" and status["total"] in (0, 12)
    jobs.cancel(job)


def test_a_job_reports_subjects_that_failed(synth_sources, tmp_path):
    (synth_sources[1] / "sub-01" / "surf" / "lh.white").write_bytes(b"junk")
    status = _wait(jobs.start(synth_sources, tmp_path / "qa", 1), _finished)
    assert status["state"] == "done"
    assert [p["key"] for p in status["problems"]] == ["freesurfer-8.2.0__sub-01"]


@pytest.mark.parametrize("n_jobs", [1, 2])
def test_cancel_stops_the_build_and_leaves_whole_files(many, tmp_path, n_jobs):
    out = tmp_path / "qa"
    job = jobs.start([many], out, n_jobs)
    seen = _wait(job, lambda s: s["done"] >= 1 or s["state"] != "running")
    assert seen["state"] == "running" and seen["total"] == 12
    jobs.cancel(job)
    status = jobs.status(job)
    assert status["state"] == "cancelled"
    assert not _alive(job.process.pid) and not building(out) and not (out / "build.lock").exists()
    for path in out.rglob("*.json"):
        json.loads(path.read_text())
    assert not list(out.rglob("*.partial"))
    again = _wait(jobs.start([many], out, 2), _finished)
    assert again["state"] == "done" and again["total"] == 12 and again["problems"] == []
    assert len(list((out / "subjects").iterdir())) == 12


def test_cancel_leaves_no_worker_behind(many, tmp_path):
    import subprocess

    job = jobs.start([many], tmp_path / "qa", 2)
    _wait(job, lambda s: s["done"] >= 1 or s["state"] != "running")
    group = os.getpgid(job.process.pid)
    jobs.cancel(job)
    time.sleep(0.2)
    listed = subprocess.run(["ps", "-o", "pid=", "-g", str(group)], capture_output=True, text=True)
    assert listed.stdout.split() == []


def test_cancel_after_the_end_changes_nothing(synth_sources, tmp_path):
    job = jobs.start(synth_sources, tmp_path / "qa", 1)
    _wait(job, _finished)
    jobs.cancel(job)
    assert jobs.status(job)["state"] == "done"


def test_a_job_that_cannot_run_ends_as_stopped_with_the_reason(synth_sources, tmp_path):
    shutil.rmtree(synth_sources[0])
    status = _wait(jobs.start([synth_sources[0]], tmp_path / "qa", 1), _finished)
    assert status["state"] == "stopped"
    assert "not a folder" in "\n".join(status["log_tail"])


def test_the_build_never_writes_into_the_source(many, tmp_path):
    before = sorted(str(p) for p in many.rglob("*"))
    _wait(jobs.start([many], tmp_path / "qa", 2), _finished)
    assert sorted(str(p) for p in many.rglob("*")) == before
