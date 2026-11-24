import pytest

from surfaceqa.guidance import build_guidance
from tests.synth import FASTSURFER_COMMAND, FREESURFER_COMMAND

S = "/data/fs/sub-01"
NEVER_EDIT = ["mri/mask.mgz", "mri/brainmask.mgz", "tmp/control.dat", "seed files",
              "mri/aseg.presurf.mgz"]


def meta(pipeline="fastsurfer", version="2.6.1", path=S, name="sub-01"):
    return {"key": f"src__{name}", "source": "src", "name": name, "path": path,
            "pipeline": pipeline, "version": version}


def prov(command, edited=False):
    evidence = ["tmp/control.dat exists"] if edited else []
    return {"version": 1, "command": command, "edited": edited, "evidence": evidence, "signature": {}}


def mark(kind="pial_out", region="sinus", tkr=(1.5, -20.0, 3.25), **extra):
    return {"region": region, "kind": kind, "grid": [1, 2, 3], "surface": "lh.pial",
            "finding": None, "note": "", "tkr": list(tkr) if tkr else None, "vertex": 7, **extra}


def test_no_marks_no_guidance():
    assert build_guidance(meta(), prov(FASTSURFER_COMMAND), [], None) is None


def test_fastsurfer_pial_problem_has_two_steps_in_the_documented_order():
    out = build_guidance(meta(), prov(FASTSURFER_COMMAND), [mark(note="into the sinus")], None)
    (problem,) = out["problems"]
    assert problem["region_title"] == "Sagittal and transverse sinus"
    assert problem["kind_label"] == "pial too far out" and problem["note"] == "into the sinus"
    first, second = problem["steps"]
    assert first["edit"] == "mri/aparc.DKTatlas+aseg.deep.manedit.mgz"
    # -n: pasting it again must never overwrite edits made in an earlier round
    assert first["copy"] == (f"cp -n {S}/mri/aparc.DKTatlas+aseg.deep.mgz "
                             f"{S}/mri/aparc.DKTatlas+aseg.deep.manedit.mgz")
    assert first["rerun"]["command"] == FASTSURFER_COMMAND + " --edits"
    assert second["copy"] is None and second["edit"] == "mri/brain.finalsurfs.manedit.mgz"
    assert second["rerun"]["command"] == FASTSURFER_COMMAND + " --edits --surf_only"
    assert first["rerun"]["label"] != second["rerun"]["label"]
    for step in (first, second):
        assert f"{S}/{step['edit']}" in step["freeview"]
        assert "-ras 1.50 -20.00 3.25 tkreg" in step["freeview"]
        assert step["text"] and step["paint"]
    # the segmentation is shown with its label colours, which is what label editing needs
    assert f"{S}/{first['edit']}:colormap=lut:opacity=0.4" in first["freeview"]
    assert "colormap" not in second["freeview"]
    assert out["never_edit"] == NEVER_EDIT and out["cautions"] and out["rerun_note"]
    assert out["warning"] is None and out["edited"] is False and out["docs"].startswith("https://")


def test_recon_all_white_surface_problem_carries_the_original_options():
    out = build_guidance(meta("freesurfer", "8.2.0"), prov(FREESURFER_COMMAND),
                         [mark("white_short", "white_surface")], None)
    fill, points = out["problems"][0]["steps"]
    tail = "-T2pial -3T -parallel -openmp 8"
    assert fill["rerun"]["command"] == f"recon-all -s sub-01 -autorecon2-wm -autorecon3 {tail}"
    assert points["rerun"]["command"] == f"recon-all -s sub-01 -autorecon2-cp -autorecon3 {tail}"
    assert f"{S}/mri/wm.mgz:colormap=heat:opacity=0.4" in fill["freeview"]
    # control points are placed on the brainmask; the point file itself is not a volume
    assert f"{S}/mri/brainmask.mgz" in points["freeview"] and "control.dat" not in points["freeview"]
    assert out["never_edit"] != NEVER_EDIT


def test_kay_note_only_where_it_applies():
    marks = [mark(region="medial_temporal"), mark(region="inferior_temporal"), mark(region="sinus")]
    problems = build_guidance(meta(), prov(FASTSURFER_COMMAND), marks, None)["problems"]
    notes = {p["region"]: p["region_note"] for p in problems}
    assert notes["sinus"] is None
    assert "not worth fixing" in notes["medial_temporal"] and "not worth fixing" in notes["inferior_temporal"]


def test_problems_are_in_checklist_order():
    marks = [mark(region="crossing", kind="crossing"), mark(region="white_surface", kind="white_past"),
             mark(region="sinus"), mark(region="made_up")]
    problems = build_guidance(meta(), prov(FASTSURFER_COMMAND), marks, None)["problems"]
    assert [p["region"] for p in problems] == ["sinus", "white_surface", "crossing", "made_up"]
    assert problems[-1]["region_title"] == "made_up"


def test_other_version_is_warned_about_and_still_gets_steps():
    out = build_guidance(meta("freesurfer", "6.0.0"), prov(FREESURFER_COMMAND), [mark()], None)
    assert "6.0.0" in out["warning"] and out["problems"][0]["steps"]


def test_unknown_pipeline_lists_the_problem_without_steps():
    out = build_guidance(meta("unknown", None), None, [mark()], None)
    assert out["warning"] and out["problems"][0]["steps"] == []
    assert out["problems"][0]["kind_label"] == "pial too far out"
    assert out["never_edit"] == [] and out["cautions"] == [] and out["docs"] is None


def test_kind_without_a_recipe_is_listed_without_steps():
    out = build_guidance(meta(), prov(FASTSURFER_COMMAND), [mark(kind="made_up")], None)
    assert out["problems"][0]["steps"] == [] and out["problems"][0]["kind_label"] == "made_up"


def test_without_provenance_the_rerun_is_a_template():
    out = build_guidance(meta(), None, [mark()], None)
    assert "<" in out["problems"][0]["steps"][0]["rerun"]["command"]
    assert out["edited"] is False and out["evidence"] == []
    out = build_guidance(meta(), prov(None), [mark()], None)
    assert "<" in out["problems"][0]["steps"][0]["rerun"]["command"]


def test_launch_template_gives_a_complete_command():
    out = build_guidance(meta(), prov(FASTSURFER_COMMAND), [mark()], "docker run img {command}")
    assert out["problems"][0]["steps"][0]["rerun"]["command"] == (
        f"docker run img {FASTSURFER_COMMAND} --edits")


def test_mark_without_a_coordinate_still_gets_its_recipe():
    out = build_guidance(meta(), prov(FASTSURFER_COMMAND), [mark(tkr=None)], None)
    step = out["problems"][0]["steps"][0]
    assert "-ras" not in step["freeview"] and step["freeview"].startswith("freeview -v ")
    assert out["problems"][0]["where"] is None


def test_where_and_reviewer_are_reported():
    out = build_guidance(meta(), prov(FASTSURFER_COMMAND), [mark(reviewer="ann"), mark()], None)
    assert out["problems"][0]["reviewer"] == "ann" and out["problems"][1]["reviewer"] is None
    assert out["problems"][0]["where"] == "1.5, -20.0, 3.2" or out["problems"][0]["where"] == "1.5, -20.0, 3.3"


def test_paths_and_names_are_quoted_everywhere():
    out = build_guidance(meta(path="/data/my scans/sub 01", name="sub 01"),
                         prov(None), [mark()], None)
    first = out["problems"][0]["steps"][0]
    assert first["copy"].count("'/data/my scans/sub 01/mri/") == 2
    free = build_guidance(meta("freesurfer", "8.2.0", name="sub 01"), prov(FREESURFER_COMMAND), [mark()], None)
    assert "-s 'sub 01'" in free["problems"][0]["steps"][0]["rerun"]["command"]


def test_edit_evidence_is_passed_on():
    out = build_guidance(meta("freesurfer", "8.2.0"), prov(FREESURFER_COMMAND, edited=True), [mark()], None)
    assert out["edited"] is True and out["evidence"] == ["tmp/control.dat exists"]


@pytest.mark.parametrize("path", ["", None])
def test_without_a_recorded_path_a_placeholder_folder_is_used(path):
    out = build_guidance(meta(path=path), prov(FASTSURFER_COMMAND), [mark()], None)
    assert "<subject folder>/mri/orig.mgz" in out["problems"][0]["steps"][0]["freeview"]


def test_rerun_uses_the_options_of_every_first_run_stage():
    stages = ["recon-all -s sub-01 -i a.nii.gz -autorecon1 -3T", "recon-all -s sub-01 -autorecon3 -T2pial"]
    provenance = {**prov(stages[0]), "stages": stages}
    out = build_guidance(meta("freesurfer", "8.2.0"), provenance, [mark()], None)
    commands = [step["rerun"]["command"] for problem in out["problems"] for step in problem["steps"]]
    assert commands and all(command.endswith("-3T -T2pial") for command in commands)
