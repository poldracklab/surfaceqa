"""Turn the marked problems of one subject into fix guidance: what to edit and how to rerun."""

import shlex

from surfaceqa.freeview import NO_FOLDER, freeview_command, usable_point
from surfaceqa.invocation import rerun_commands
from surfaceqa.protocol import load_protocol
from surfaceqa.recipes import load_recipes, recipe_for, version_warning
from surfaceqa.regions import REGIONS

RERUN_LABELS = {
    "seg": "Rerun after a segmentation edit",
    "surf": "Rerun the surfaces only",
    "pial": "Rerun from the pial surface step",
    "wm": "Rerun from the white-matter step",
    "cp": "Rerun with the control points",
}
NO_PIPELINE = {"never_edit": [], "never_edit_note": "", "cautions": [], "rerun_note": "", "docs": None}


def _copy_command(path: str, step: dict) -> str | None:
    if not step["copy_from"]:
        return None
    folder = path or NO_FOLDER
    return shlex.join(["cp", f"{folder}/{step['copy_from']}", f"{folder}/{step['edit']}"])


def _step(step: dict, path: str, tkr, reruns: dict[str, str]) -> dict:
    shown = step.get("view") or step["edit"]
    return {"text": step["text"], "paint": step["paint"], "edit": step["edit"],
            "copy": _copy_command(path, step),
            "freeview": freeview_command(path, shown, tkr, step["overlay"]),
            "rerun": {"label": RERUN_LABELS[step["rerun"]], "command": reruns[step["rerun"]]}}


def _where(tkr) -> str | None:
    return ", ".join(f"{value:.1f}" for value in tkr) if usable_point(tkr) else None


def _problem(mark: dict, meta: dict, reruns: dict[str, str]) -> dict:
    titles = {region.id: region.title for region in REGIONS}
    kinds = {kind["id"]: kind["label"] for kind in load_protocol()["mark_kinds"]}
    recipe = recipe_for(meta["pipeline"], mark["kind"])
    steps = recipe["steps"] if recipe else []
    return {"region": mark["region"], "region_title": titles.get(mark["region"], mark["region"]),
            "kind": mark["kind"], "kind_label": kinds.get(mark["kind"], mark["kind"]),
            "note": mark.get("note", ""), "reviewer": mark.get("reviewer"),
            "where": _where(mark.get("tkr")),
            "region_note": load_recipes()["region_notes"].get(mark["region"]),
            "steps": [_step(step, meta.get("path") or "", mark.get("tkr"), reruns) for step in steps]}


def _checklist_position(mark: dict) -> int:
    order = [region.id for region in REGIONS]
    return order.index(mark["region"]) if mark["region"] in order else len(order)


def build_guidance(meta: dict, provenance: dict | None, marks: list[dict],
                   template: str | None) -> dict | None:
    """Guidance for the marked problems of one subject; None when nothing is marked."""
    if not marks:
        return None
    provenance = provenance or {"command": None, "edited": False, "evidence": []}
    reruns = rerun_commands(meta["pipeline"], provenance["command"], meta["name"], template)
    block = load_recipes()["pipelines"].get(meta["pipeline"], NO_PIPELINE)
    return {"warning": version_warning(meta["pipeline"], meta.get("version")),
            "problems": [_problem(mark, meta, reruns) for mark in sorted(marks, key=_checklist_position)],
            "never_edit": block["never_edit"], "never_edit_note": block["never_edit_note"],
            "cautions": block["cautions"], "rerun_note": block["rerun_note"], "docs": block["docs"],
            "edited": provenance["edited"], "evidence": provenance["evidence"]}
