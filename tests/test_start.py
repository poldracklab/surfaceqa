import os

import pytest

from surfaceqa import start
from surfaceqa.settings import save_sources
from tests.synth import write_subject


@pytest.fixture
def home(tmp_path, monkeypatch):
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    return folder


def _snapshot(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_is_qa_dir(qa, tmp_path):
    assert start.is_qa_dir(qa)
    assert not start.is_qa_dir(tmp_path) and not start.is_qa_dir(tmp_path / "absent")


def test_describe_a_subject_and_a_subjects_folder(synth_sources):
    write_subject(synth_sources[0], name="sub-02")
    assert start.describe(synth_sources[0]) == {"path": str(synth_sources[0]), "name": "fastsurfer",
                                                "subject": False, "n_subjects": 2}
    one = start.describe(synth_sources[0] / "sub-01")
    assert one["subject"] is True and one["n_subjects"] == 0 and one["name"] == "sub-01"


def test_list_folders_gives_sorted_folders_and_never_files(synth_sources, tmp_path):
    (tmp_path / "notes.txt").write_text("secret")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "Zeta").mkdir()
    listing = start.list_folders(tmp_path)
    names = [f["name"] for f in listing["folders"]]
    assert names == ["fastsurfer", "freesurfer-8.2.0", "Zeta"]
    assert listing["path"] == str(tmp_path) and listing["parent"] == str(tmp_path.parent)
    assert listing["error"] is None and not listing.get("truncated")
    assert listing["folders"][0]["n_subjects"] == 1
    assert "notes.txt" not in str(listing) and ".hidden" not in str(listing)


def test_list_folders_inside_a_subjects_folder_marks_subjects(synth_sources):
    listing = start.list_folders(synth_sources[0])
    assert [(f["name"], f["subject"]) for f in listing["folders"]] == [("sub-01", True)]


@pytest.mark.parametrize("make", ["absent", "file"])
def test_list_folders_of_something_that_is_not_a_folder(tmp_path, make):
    target = tmp_path / "x"
    if make == "file":
        target.write_text("x")
    listing = start.list_folders(target)
    assert listing["folders"] == [] and listing["error"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
def test_list_folders_of_an_unreadable_folder(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    (tmp_path / "open").mkdir()
    locked.chmod(0)
    try:
        assert start.list_folders(locked)["error"] and start.list_folders(locked)["folders"] == []
        names = [f["name"] for f in start.list_folders(tmp_path)["folders"]]
        assert names == ["locked", "open"]  # listed, counted as holding no subject
    finally:
        locked.chmod(0o755)


def test_list_folders_survives_a_symlink_loop(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "loop").symlink_to(tmp_path / "a")
    (tmp_path / "self").symlink_to(tmp_path / "self")
    listing = start.list_folders(tmp_path)
    assert [f["name"] for f in listing["folders"]] == ["a"] and listing["error"] is None
    assert [f["name"] for f in start.list_folders(tmp_path / "a")["folders"]] == ["loop"]


def test_list_folders_stops_at_500(tmp_path):
    for i in range(503):
        (tmp_path / f"d{i:04d}").mkdir()
    listing = start.list_folders(tmp_path)
    assert len(listing["folders"]) == 500 and listing["truncated"] is True
    assert listing["folders"][-1]["name"] == "d0499"


def test_the_root_has_no_parent():
    assert start.list_folders("/")["parent"] is None


def test_places_start_with_home(home):
    places = start.places()
    assert places[0] == {"path": str(home), "name": "Home"}
    assert all(set(p) == {"path", "name"} for p in places)


def test_default_out_is_beside_the_source(synth_sources, home):
    assert start.default_out(synth_sources) == synth_sources[0].parent / "surfaceqa"
    assert start.default_out([synth_sources[1] / "sub-01"]) == synth_sources[0].parent / "surfaceqa"


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes everywhere")
def test_default_out_falls_back_to_home_when_beside_cannot_be_written(tmp_path, home):
    data = tmp_path / "readonly"
    source = write_subject(data / "study").parent
    data.chmod(0o555)
    try:
        assert start.default_out([source]) == home / "surfaceqa" / "study"
    finally:
        data.chmod(0o755)


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes everywhere")
def test_fallback_gets_a_number_when_the_name_is_taken_by_other_sources(tmp_path, home):
    data = tmp_path / "readonly"
    source = write_subject(data / "study").parent
    taken = home / "surfaceqa" / "study"
    (taken / "subjects").mkdir(parents=True)
    save_sources(taken, [tmp_path / "elsewhere" / "study"])
    mine = home / "surfaceqa" / "study-2"
    (mine / "subjects").mkdir(parents=True)
    save_sources(mine, [source])
    data.chmod(0o555)
    try:
        assert start.default_out([source]) == mine  # its own earlier project is reused
        save_sources(mine, [tmp_path / "third"])
        assert start.default_out([source]) == home / "surfaceqa" / "study-3"
    finally:
        data.chmod(0o755)


def test_a_good_request_passes_and_creates_nothing(synth_sources, tmp_path):
    before = _snapshot(tmp_path)
    assert start.check_request(synth_sources, tmp_path / "new" / "deeper" / "qa") is None
    assert start.check_request([synth_sources[0] / "sub-01"], tmp_path / "qa") is None
    assert _snapshot(tmp_path) == before


def test_adding_to_an_existing_qa_directory_is_allowed_and_said(qa, synth_sources, tmp_path):
    assert start.check_request(synth_sources, qa) is None
    assert start.adds_to_existing(qa) is True
    assert start.adds_to_existing(tmp_path / "new") is False
    (tmp_path / "empty").mkdir()
    assert start.check_request(synth_sources, tmp_path / "empty") is None
    assert start.adds_to_existing(tmp_path / "empty") is False


def _refused(sources, out, word, root):
    before = _snapshot(root)
    message = start.check_request(sources, out)
    assert message and word in message.lower(), message
    assert _snapshot(root) == before


def test_refusals(synth_sources, tmp_path):
    (tmp_path / "empty-source").mkdir()
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "thesis.doc").write_text("x")
    (tmp_path / "file").write_text("x")
    good = tmp_path / "qa"
    _refused([], good, "choose", tmp_path)
    _refused([tmp_path / "absent"], good, "not a folder", tmp_path)
    _refused([tmp_path / "file"], good, "not a folder", tmp_path)
    _refused([tmp_path / "empty-source"], good, "no subject", tmp_path)
    _refused([synth_sources[0], tmp_path / "empty-source"], good, "no subject", tmp_path)
    _refused(synth_sources, synth_sources[0] / "qa", "inside", tmp_path)
    _refused(synth_sources, synth_sources[1], "inside", tmp_path)
    _refused([synth_sources[0] / "sub-01"], synth_sources[0] / "qa", "inside", tmp_path)
    _refused(synth_sources, tmp_path / "busy", "not empty", tmp_path)
    _refused(synth_sources, tmp_path / "file", "not a folder", tmp_path)
    _refused(synth_sources, tmp_path / "file" / "qa", "cannot be written", tmp_path)


def test_two_sources_that_would_share_subject_names_are_refused(tmp_path):
    write_subject(tmp_path / "a" / "study")
    write_subject(tmp_path / "b" / "study")
    _refused([tmp_path / "a" / "study", tmp_path / "b" / "study"], tmp_path / "qa", "study", tmp_path)


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes everywhere")
def test_an_output_that_cannot_be_written_is_refused(synth_sources, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        _refused(synth_sources, locked / "qa", "cannot be written", synth_sources[0])
        _refused(synth_sources, locked, "cannot be written", synth_sources[0])
    finally:
        locked.chmod(0o755)


def test_plan_fills_in_the_default_output(synth_sources):
    assert start.plan(synth_sources, "") == {"out": str(synth_sources[0].parent / "surfaceqa"),
                                              "error": None, "adds": False, "n_subjects": 2}
    assert start.plan([str(synth_sources[0]), "  ", ""], "  ")["n_subjects"] == 1


def test_plan_with_a_chosen_output(qa, synth_sources, tmp_path):
    assert start.plan(synth_sources, str(qa))["adds"] is True
    assert start.plan(synth_sources, str(tmp_path / "x"))["out"] == str(tmp_path / "x")


def test_plan_with_a_problem_says_it_and_names_no_output_to_use(synth_sources, tmp_path):
    assert start.plan([], "") == {"out": "", "error": "Choose a folder to inspect.", "adds": False,
                                  "n_subjects": 0}
    bad_source = start.plan([tmp_path / "absent"], "")
    assert "Not a folder" in bad_source["error"] and bad_source["out"] == ""
    bad_out = start.plan(synth_sources, str(synth_sources[0] / "qa"))
    assert "inside" in bad_out["error"] and bad_out["out"] == str(synth_sources[0] / "qa")
