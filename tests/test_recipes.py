import pytest

from surfaceqa.protocol import load_protocol
from surfaceqa.recipes import load_recipes, recipe_for, version_warning

NEVER_EDIT = ["mri/mask.mgz", "mri/brainmask.mgz", "tmp/control.dat", "seed files",
              "mri/aseg.presurf.mgz"]
SEG_EDIT = "mri/aparc.DKTatlas+aseg.deep.manedit.mgz"
BFS_EDIT = "mri/brain.finalsurfs.manedit.mgz"


def _steps(pipeline, kind):
    return recipe_for(pipeline, kind)["steps"]


@pytest.mark.parametrize("pipeline", ["fastsurfer", "freesurfer"])
def test_every_mark_kind_has_a_recipe_for_both_pipelines(pipeline):
    for kind in load_protocol()["mark_kinds"]:
        steps = _steps(pipeline, kind["id"])
        assert steps and all(step["text"] for step in steps)
        assert all({"text", "edit", "copy_from", "paint", "rerun", "overlay"} <= set(s) for s in steps)


def test_recipe_for_an_unknown_pipeline_or_kind_is_none():
    assert recipe_for("unknown", "pial_out") is None
    assert recipe_for("fastsurfer", "nonsense") is None


@pytest.mark.parametrize("kind,value", [("pial_out", "1"), ("gray_missed", "255")])
def test_fastsurfer_pial_recipes_follow_the_spec_table(kind, value):
    first, second = _steps("fastsurfer", kind)
    assert first["edit"] == SEG_EDIT and first["rerun"] == "seg"
    assert first["copy_from"] == "mri/aparc.DKTatlas+aseg.deep.mgz"
    assert second["edit"] == BFS_EDIT and second["rerun"] == "surf"
    assert second["copy_from"] is None  # FastSurfer writes this file itself
    assert value in second["paint"]


@pytest.mark.parametrize("kind", ["white_short", "white_past", "topology"])
def test_fastsurfer_white_recipes_end_with_the_white_matter_edit(kind):
    steps = _steps("fastsurfer", kind)
    last = steps[-1]
    assert last["edit"] == "mri/wm.mgz" and "mri/filled.mgz" in last["text"]
    assert last["rerun"] == "surf" and "255" in last["paint"] and "1" in last["paint"]
    if kind != "topology":
        assert steps[0]["edit"] == SEG_EDIT and steps[0]["rerun"] == "seg"


def test_fastsurfer_crossing_says_nothing_is_documented():
    steps = _steps("fastsurfer", "crossing")
    assert "No dedicated edit is documented" in steps[0]["text"]
    assert steps[0]["edit"] == SEG_EDIT


def test_fastsurfer_never_edit_list():
    block = load_recipes()["pipelines"]["fastsurfer"]
    assert block["never_edit"] == NEVER_EDIT
    edited = {step["edit"] for recipe in block["recipes"].values() for step in recipe["steps"]}
    assert not edited & set(NEVER_EDIT)


FREESURFER_TABLE = {
    "pial_out": [(BFS_EDIT, "pial")],
    "gray_missed": [("mri/wm.mgz", "wm"), (BFS_EDIT, "pial")],
    "white_short": [("mri/wm.mgz", "wm"), ("tmp/control.dat", "cp")],
    "white_past": [("mri/wm.mgz", "wm")],
    "topology": [("mri/wm.mgz", "wm")],
    "crossing": [("mri/wm.mgz", "wm"), (BFS_EDIT, "pial")],
}


@pytest.mark.parametrize("kind", sorted(FREESURFER_TABLE))
def test_freesurfer_recipes_follow_the_plan_table(kind):
    steps = _steps("freesurfer", kind)
    assert [(step["edit"], step["rerun"]) for step in steps] == FREESURFER_TABLE[kind]
    assert all(step["edit"] != "mri/brainmask.mgz" for step in steps)


def test_freesurfer_paint_values():
    assert "1" in _steps("freesurfer", "pial_out")[0]["paint"]
    assert "255" in _steps("freesurfer", "gray_missed")[1]["paint"]
    assert "255" in _steps("freesurfer", "white_short")[0]["paint"]
    assert "1" in _steps("freesurfer", "white_past")[0]["paint"]
    assert "orig.nofix" in _steps("freesurfer", "topology")[0]["text"]
    assert "No dedicated edit is documented" in _steps("freesurfer", "crossing")[0]["text"]


def test_each_pipeline_has_cautions_a_rerun_note_and_a_docs_link():
    for block in load_recipes()["pipelines"].values():
        assert block["cautions"] and block["rerun_note"] and block["docs"].startswith("https://")
    assert load_recipes()["pipelines"]["fastsurfer"]["written_for"] == "2.6"
    assert load_recipes()["pipelines"]["freesurfer"]["written_for"] == "8"
    assert isinstance(load_recipes()["version"], int)


def test_region_notes():
    assert set(load_recipes()["region_notes"]) == {"inferior_temporal", "medial_temporal"}


def test_version_warning():
    assert version_warning("fastsurfer", "2.6.1") is None
    assert version_warning("freesurfer", "8.2.0") is None
    old = version_warning("freesurfer", "6.0.0")
    assert "6.0.0" in old and "8" in old
    assert "2.6" in version_warning("fastsurfer", "2.60.0")  # 2.60 is not 2.6
    assert version_warning("fastsurfer", None)
    assert version_warning("unknown", None)
