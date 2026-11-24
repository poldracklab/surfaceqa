import json

import pytest

from surfaceqa.build import build_subject
from surfaceqa.discover import find_subjects
from surfaceqa.pipelines import detect_pipeline
from surfaceqa.provenance import PROVENANCE_FILE, PROVENANCE_VERSION, load_provenance, write_provenance
from tests.synth import FASTSURFER_COMMAND, write_subject


@pytest.fixture
def built(tmp_path):
    subj = write_subject(tmp_path / "freesurfer", pipeline="freesurfer")
    ref = find_subjects([subj])[0]
    qa = tmp_path / "qa"
    return subj, ref, qa, build_subject(ref, qa)


def _run_dir(qa, ref, res):
    return qa / "subjects" / ref.key / "runs" / res.run


def test_write_provenance_records_the_command_and_edit_state(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer")
    ref = find_subjects([subj])[0]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert write_provenance(ref, detect_pipeline(subj), run_dir) is True
    stored = json.loads((run_dir / PROVENANCE_FILE).read_text())
    assert stored["version"] == PROVENANCE_VERSION and stored["command"] == FASTSURFER_COMMAND
    assert stored["edited"] is False and stored["evidence"] == []
    assert "scripts/deep-seg.log" in stored["signature"]


def test_unchanged_subject_is_not_rewritten(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer")
    ref = find_subjects([subj])[0]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_provenance(ref, detect_pipeline(subj), run_dir)
    stamp = (run_dir / PROVENANCE_FILE).stat().st_mtime_ns
    assert write_provenance(ref, detect_pipeline(subj), run_dir) is False
    assert (run_dir / PROVENANCE_FILE).stat().st_mtime_ns == stamp


def test_build_writes_provenance(built):
    subj, ref, qa, res = built
    stored = load_provenance(qa, ref.key)
    assert res.status == "built" and stored["edited"] is False
    assert stored["command"].endswith("-openmp 8")
    assert build_subject(ref, qa).status == "unchanged"


def test_a_new_edit_file_updates_the_subject(built):
    subj, ref, qa, res = built
    (subj / "tmp").mkdir()
    (subj / "tmp" / "control.dat").write_text("0 0 0\n")
    assert build_subject(ref, qa).status == "updated"
    stored = load_provenance(qa, ref.key)
    assert stored["edited"] is True and "tmp/control.dat" in stored["evidence"][0]


def test_provenance_from_older_code_is_rewritten(built, monkeypatch):
    subj, ref, qa, res = built
    monkeypatch.setattr("surfaceqa.provenance.PROVENANCE_VERSION", 10_000)
    assert build_subject(ref, qa).status == "updated"
    assert load_provenance(qa, ref.key)["version"] == 10_000


@pytest.mark.parametrize("content", ["[1, 2]", "not json", '{"version": 1}',
                                     '{"version": 1, "command": 3, "edited": "no", "evidence": {}, "signature": {}}'])
def test_wrong_shaped_provenance_is_ignored(built, content):
    subj, ref, qa, res = built
    (_run_dir(qa, ref, res) / PROVENANCE_FILE).write_text(content)
    assert load_provenance(qa, ref.key) is None


def test_load_provenance_of_an_unknown_subject(tmp_path):
    assert load_provenance(tmp_path, "nope__nobody") is None


def test_a_failure_here_keeps_the_viewer(tmp_path, monkeypatch):
    from surfaceqa.build import load_meta

    subj = write_subject(tmp_path / "fastsurfer")
    monkeypatch.setattr("surfaceqa.provenance.detect_edits", lambda *a, **k: 1 / 0)
    ref = find_subjects([subj])[0]
    res = build_subject(ref, tmp_path / "qa")
    assert res.status == "built" and load_meta(tmp_path / "qa", ref.key) is not None
    assert load_provenance(tmp_path / "qa", ref.key) is None


# ---- "edited" can be unknown ----------------------------------------------------------------

def _provenance(tmp_path, spoil=None, pipeline="freesurfer"):
    from surfaceqa.discover import find_subjects
    from surfaceqa.pipelines import detect_pipeline
    from surfaceqa.provenance import write_provenance
    from tests.synth import write_subject

    subj = write_subject(tmp_path / "fs", pipeline=pipeline)
    if spoil:
        spoil(subj)
    (tmp_path / "run").mkdir()
    write_provenance(find_subjects([subj])[0], detect_pipeline(subj), tmp_path / "run")
    import json
    return json.loads((tmp_path / "run" / "provenance.json").read_text())


def test_a_volume_that_cannot_be_read_makes_edited_unknown_not_yes(tmp_path):
    record = _provenance(tmp_path, lambda subj: (subj / "mri" / "wm.mgz").write_bytes(b"junk"))
    assert record["edited"] is None
    assert record["evidence"] == ["mri/wm.mgz could not be read, so it was not checked for edits"]


def test_real_evidence_wins_over_an_unreadable_volume(tmp_path):
    def spoil(subj):
        (subj / "mri" / "wm.mgz").write_bytes(b"junk")
        (subj / "tmp").mkdir()
        (subj / "tmp" / "control.dat").write_text("1 2 3\n")

    assert _provenance(tmp_path, spoil)["edited"] is True


def test_provenance_records_every_stage_of_the_first_run(tmp_path):
    lines = ["recon-all -s sub-01 -i a.nii.gz -autorecon1", "recon-all -s sub-01 -autorecon2 -T2pial",
             "recon-all -s sub-01 -autorecon-pial"]

    def stages(subj):
        (subj / "scripts" / "recon-all.log").write_text("\n".join(lines) + "\n")

    record = _provenance(tmp_path, stages)
    assert record["command"] == lines[0] and record["stages"] == lines[:2]
    assert record["version"] == 3
