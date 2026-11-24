import json

from surfaceqa import progress
from surfaceqa.cli import main
from surfaceqa.lock import build_lock
from tests.synth import write_subject


def test_status_round_trip(tmp_path):
    assert progress.read(tmp_path) is None
    progress.write(tmp_path, state="running", stage="render", done=1, total=3)
    assert progress.read(tmp_path) == {"state": "running", "stage": "render", "done": 1, "total": 3}
    assert [p.name for p in tmp_path.iterdir()] == [progress.STATUS_FILE]


def test_junk_status_reads_as_none(tmp_path):
    (tmp_path / progress.STATUS_FILE).write_text("[1")
    assert progress.read(tmp_path) is None


def test_build_with_progress_leaves_a_done_status(synth_sources, tmp_path):
    qa = tmp_path / "qa"
    assert main(["build", *map(str, synth_sources), "--out", str(qa), "--progress"]) == 0
    status = progress.read(qa)
    assert status["state"] == "done" and status["total"] == 2 and status["done"] == 2
    assert status["problems"] == [] and status["cohort_failed"] is False


def test_done_status_names_failed_and_incomplete_subjects(synth_sources, tmp_path):
    (synth_sources[1] / "sub-01" / "surf" / "lh.white").write_bytes(b"junk")
    write_subject(synth_sources[0], name="sub-02", omit=("surf/lh.white",))
    qa = tmp_path / "qa"
    assert main(["build", *map(str, synth_sources), "--out", str(qa), "--progress"]) == 1
    problems = {p["key"]: p for p in progress.read(qa)["problems"]}
    assert set(problems) == {"freesurfer-8.2.0__sub-01", "fastsurfer__sub-02"}
    failed = problems["freesurfer-8.2.0__sub-01"]
    assert failed["status"] == "failed" and failed["reason"] and "\n" not in failed["reason"]
    error = (qa / "subjects" / "freesurfer-8.2.0__sub-01" / "error.txt").read_text()
    assert failed["reason"] == error.strip().splitlines()[-1].strip()
    assert problems["fastsurfer__sub-02"] == {"key": "fastsurfer__sub-02", "status": "missing",
                                             "reason": "missing: surf/lh.white"}


def test_status_while_building_is_running_with_the_pid(synth_sources, tmp_path, monkeypatch):
    import os

    from surfaceqa import cli

    seen = []
    real = cli.build_all

    def watching(refs, out, jobs=1, progress=None):
        def both(stage, done, total):
            progress(stage, done, total)
            seen.append(json.loads((out / "build_status.json").read_text()))
        return real(refs, out, jobs=jobs, progress=both)

    monkeypatch.setattr(cli, "build_all", watching)
    main(["build", str(synth_sources[0]), "--out", str(tmp_path / "qa"), "--progress"])
    assert seen and all(s["state"] == "running" and s["pid"] == os.getpid() for s in seen)
    assert seen[0] == {"state": "running", "pid": os.getpid(), "stage": "render", "done": 0, "total": 1}


def test_build_without_progress_writes_no_status(synth_sources, tmp_path):
    main(["build", str(synth_sources[0]), "--out", str(tmp_path / "qa")])
    assert progress.read(tmp_path / "qa") is None


def test_build_is_refused_while_another_build_holds_the_directory(synth_sources, tmp_path, capsys):
    qa = tmp_path / "qa"
    with build_lock(qa):
        assert main(["build", str(synth_sources[0]), "--out", str(qa)]) == 1
    assert "already running" in capsys.readouterr().err
    assert not (qa / "subjects").exists() and not (qa / "index.html").exists()


def test_build_releases_the_directory(synth_sources, tmp_path):
    from surfaceqa.lock import building

    qa = tmp_path / "qa"
    main(["build", str(synth_sources[0]), "--out", str(qa)])
    assert not building(qa)
    assert main(["build", str(synth_sources[0]), "--out", str(qa)]) == 0
