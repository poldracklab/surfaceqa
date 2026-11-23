"""Turn a subject's findings into the checklist sections shown on its page."""

from surfaceqa.regions import REGIONS

WHAT = {
    "pial_out": "pial too far out", "gray_missed": "gray matter missed",
    "white_short": "white surface short", "crossing": "hemispheres overlap",
    "thickness": "thick patch", "topology": "topology defect",
    "look_here": "cortex label outside the pial surface",
}
HINT_KIND = "look_here"


def scored_findings(found: dict) -> list[dict]:
    """Findings that count as possible errors, leaving out the places to look."""
    return [f for f in found["findings"] if f["kind"] != HINT_KIND]


def finding_text(finding: dict) -> str:
    """For example 'pial too far out · 217 mm³' or 'thick patch · 391 vertices'."""
    if finding["size_mm3"] is None:
        return f"{WHAT[finding['kind']]} · {finding['n']} vertices"
    return f"{WHAT[finding['kind']]} · {round(finding['size_mm3'])} mm³"


def _section(region, findings: list[dict], defaults: dict) -> dict:
    mine = [{**f, "text": finding_text(f)} for f in findings if f["region"] == region.id]
    return {"id": region.id, "title": region.title, "look_for": region.look_for,
            "findings": [f for f in mine if f["kind"] != HINT_KIND],
            "hints": [f for f in mine if f["kind"] == HINT_KIND],
            "defaults": defaults.get(region.id, [])}


def checklist_sections(found: dict | None) -> list[dict]:
    """One section per region, in Kay's order; findings keep their most-points-first order.

    Every region is always listed. Without findings (the indicators failed or never ran)
    each section says so instead of implying that nothing was found.
    """
    findings = found["findings"] if found else []
    defaults = found["defaults"] if found else {}
    sections = [_section(region, findings, defaults) for region in REGIONS]
    return [{**section, "indicators_available": found is not None} for section in sections]
