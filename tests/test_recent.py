from datetime import datetime, timedelta

from surfaceqa import recent
from tests.synth import fake_qa_dir

T0 = datetime(2026, 11, 24, 9, 0, 0)


def test_home_follows_the_environment(surfaceqa_home, monkeypatch, tmp_path):
    assert recent.home() == surfaceqa_home
    monkeypatch.delenv("SURFACEQA_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert recent.home() == tmp_path / ".surfaceqa"


def test_no_projects_at_first():
    assert recent.projects() == []


def test_remembered_projects_come_newest_first(qa, tmp_path):
    other = tmp_path / "other"
    fake_qa_dir(other)
    recent.remember(qa, T0)
    recent.remember(other, T0 + timedelta(hours=1))
    listed = recent.projects()
    assert [p["path"] for p in listed] == [str(other.resolve()), str(qa.resolve())]
    assert listed[1]["opened"] == "2026-11-24 09:00" and listed[1]["exists"] is True
    assert listed[1]["n_subjects"] == 3
    assert listed[1]["sources"] == ["fastsurfer", "freesurfer-8.2.0"]
    assert listed[0]["n_subjects"] == 1 and listed[0]["sources"] == ["study"]


def test_opening_again_moves_a_project_to_the_top_without_repeating_it(qa, tmp_path):
    other = tmp_path / "other"
    fake_qa_dir(other)
    recent.remember(qa, T0)
    recent.remember(other, T0 + timedelta(hours=1))
    recent.remember(qa, T0 + timedelta(hours=2))
    assert [p["path"] for p in recent.projects()] == [str(qa.resolve()), str(other.resolve())]


def test_a_project_whose_folder_is_gone_is_listed_as_missing(tmp_path):
    recent.remember(tmp_path / "gone", T0)
    assert recent.projects() == [{"path": str((tmp_path / "gone").resolve()), "opened": "2026-11-24 09:00",
                                  "exists": False, "sources": [], "n_subjects": 0}]


def test_forget(qa, tmp_path):
    recent.remember(qa, T0)
    recent.remember(tmp_path / "gone", T0)
    recent.forget(tmp_path / "gone")
    assert [p["path"] for p in recent.projects()] == [str(qa.resolve())]
    recent.forget(tmp_path / "never-listed")


def test_only_twenty_projects_are_kept(tmp_path):
    for i in range(21):
        recent.remember(tmp_path / f"p{i:02d}", T0 + timedelta(minutes=i))
    names = [p["path"].rsplit("/", 1)[1] for p in recent.projects()]
    assert len(names) == 20 and names[0] == "p20" and "p00" not in names


def test_a_corrupt_list_reads_as_empty_and_is_replaced(surfaceqa_home, qa):
    (surfaceqa_home / "recent.json").write_text('{"not": "a list"')
    assert recent.projects() == []
    (surfaceqa_home / "recent.json").write_text('[3, {"path": 4}, {"opened": "x"}]')
    assert recent.projects() == []
    recent.remember(qa, T0)
    assert len(recent.projects()) == 1


def test_sources_recorded_in_settings_are_used(qa, tmp_path):
    from surfaceqa.settings import save_sources

    save_sources(qa, [tmp_path / "fastsurfer", tmp_path / "freesurfer-8.2.0" / "sub-01"])
    recent.remember(qa, T0)
    assert recent.projects()[0]["sources"] == ["fastsurfer", "freesurfer-8.2.0"]
