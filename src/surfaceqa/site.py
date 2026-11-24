"""Write the index page and one page per subject from what is in the QA directory."""

import json
import shutil
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, PackageLoader, select_autoescape

from surfaceqa.build import load_meta
from surfaceqa.layout import current_run_dir
from surfaceqa.compare import VIEWER_PAGE, candidates, run_metas
from surfaceqa.checklist import checklist_sections, finding_text, scored_findings
from surfaceqa.protocol import load_protocol
from surfaceqa.qa import load_findings
from surfaceqa.queue import blind_order
from surfaceqa.regions import REGIONS
from surfaceqa.scoring import rank_within_pipeline
from surfaceqa.site_guidance import guidance_fields
from surfaceqa.site_reviews import review_fields

VIEW_ORDER = ("coronal", "sagittal", "axial")
NO_RUN_TEMPLATE = {"missing files": "missing.html", "build failed": "failed.html"}


@dataclass(frozen=True)
class View:
    """Who a page is rendered for. The pages written by `build` use the default."""
    reviewer: str | None = None
    blind: bool = False
    serving: bool = False  # rendered by `surfaceqa serve`, so ratings can be saved


@cache
def _environment() -> Environment:
    return Environment(loader=PackageLoader("surfaceqa", "web/templates"),
                       autoescape=select_autoescape(["html"]))


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _fallback_info(key: str) -> dict:
    source, _, name = key.partition("__")
    return {"key": key, "source": source, "name": name, "path": "", "pipeline": "unknown",
            "version": None}


def _status(meta: dict | None, missing: dict | None, failed: bool) -> str:
    """The state of the latest build; an earlier good run does not make a subject ready."""
    if missing is not None:
        return "missing files"
    if failed or meta is None:
        return "build failed"
    return "ready"


def _subject_record(qa_dir: Path, folder: Path, view: View) -> dict:
    record = _build_record(qa_dir, folder)
    reviews = review_fields(qa_dir, record, view)
    return {**record, **reviews, **guidance_fields(qa_dir, record, view, reviews)}


def _build_record(qa_dir: Path, folder: Path) -> dict:
    key = folder.name
    meta = load_meta(qa_dir, key)
    missing = _read_json(folder / "missing.json")
    record = {**_fallback_info(key), **(meta or {}), **(missing or {}), "has_run": meta is not None}
    record["status"] = _status(meta, missing, (folder / "error.txt").is_file())
    version = f" {record['version']}" if record.get("version") else ""
    return {**record, "pipeline_label": f"{record['pipeline']}{version}",
            "href": f"subjects/{quote(key)}/index.html", **_qa_fields(qa_dir, folder)}


def _qa_fields(qa_dir: Path, folder: Path) -> dict:
    """What the indicators produced for the subject's current run."""
    found = load_findings(qa_dir, folder.name)
    if found is None:
        return {"qa": None, "score": None, "qa_failed": _qa_failed(qa_dir, folder.name),
                "sections": checklist_sections(None)}
    titles = {region.id: region.title for region in REGIONS}
    scored = scored_findings(found)
    top = scored[0] if scored else None
    largest = f"{finding_text(top)} · {titles[top['region']]}" if top else ""
    not_run = [i for i in found["indicators"] if i["status"] == "not run"]
    partial = [i for i in found["indicators"] if i["status"] == "ran" and i["reason"]]
    any_ran = len(not_run) < len(found["indicators"])
    return {"qa": found, "score": found["score"] if any_ran else None, "qa_failed": False,
            "largest": largest, "n_findings": len(scored), "not_run": not_run, "partial": partial,
            "n_indicators": len(found["indicators"]), "sections": checklist_sections(found)}


def _qa_failed(qa_dir: Path, key: str) -> bool:
    run_dir = current_run_dir(qa_dir, key)
    return run_dir is not None and (run_dir / "qa_error.txt").is_file()


def _add_ranks(records: list[dict]) -> None:
    scored = {r["key"]: (r["source"], r["score"]) for r in records if r["score"] is not None}
    ranks = rank_within_pipeline(scored)
    for record in records:
        record["rank"] = ranks.get(record["key"])


def _review_order(record: dict) -> tuple:
    """Grouped by source folder; most suspicious first; subjects without a score last."""
    score = record["score"]
    return (record["source"], score is None, -(score or 0.0), record["key"])


HIDDEN = {"score": None, "rank": None, "largest": "", "n_findings": None, "qa": None,
          "not_run": [], "partial": []}


def _hide_indicators(record: dict) -> dict:
    """Blind review: nothing the indicators produced reaches the page."""
    if not record["hide_indicators"]:
        return record
    return {**record, **HIDDEN, "sections": checklist_sections(None)}


def _ordered(records: list[dict], view: View) -> list[dict]:
    if not view.blind or view.reviewer is None:
        return sorted(records, key=_review_order)
    by_key = {record["key"]: record for record in records}
    return [by_key[key] for key in blind_order(list(by_key), view.reviewer)]


def subject_records(qa_dir: Path, view: View = View()) -> list[dict]:
    """Every subject in the QA directory as `view.reviewer` may see it, in review order."""
    qa_dir = Path(qa_dir)
    root = qa_dir / "subjects"
    folders = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    records = [_subject_record(qa_dir, folder, view) for folder in folders]
    _add_ranks(records)
    for record in records:
        record["compare"] = candidates(qa_dir, record, records)
    return _ordered([_hide_indicators(record) for record in records], view)


def _needs_name(view: View) -> bool:
    return view.serving and view.blind and view.reviewer is None


def _context(view: View, root: str, here: str) -> dict:
    return {"view": view, "root": root, "here": here, "protocol": load_protocol(),
            "reviewing": view.serving and view.reviewer is not None}


def render_index(records: list[dict], view: View = View()) -> str:
    name = "name.html" if _needs_name(view) else "index.html"
    return _environment().get_template(name).render(subjects=records, **_context(view, "", "/"))


def render_subject(record: dict, view: View = View()) -> str:
    name = "subject.html" if record["has_run"] else NO_RUN_TEMPLATE[record["status"]]
    here = f"/subjects/{quote(record['key'])}/"
    template = _environment().get_template("name.html" if _needs_name(view) else name)
    run_url = f"runs/{record['run']}/" if record["has_run"] else ""
    return template.render(subject=record, views=VIEW_ORDER, run_url=run_url, embedded=False,
                           **_context(view, "../../", here))


def render_viewer(record: dict, meta: dict, view: View = View()) -> str:
    """One run of a subject as a viewer and nothing else, to be shown beside another subject.

    `meta` is the run's own: an earlier run may be of another pipeline version than the current one.
    """
    version = f" {meta['version']}" if meta.get("version") else ""
    return _environment().get_template("viewer.html").render(
        subject=record, views=VIEW_ORDER, run_url="", embedded=True,
        pipeline_label=f"{meta.get('pipeline', 'unknown')}{version}",
        built=meta.get("built", "")[:10], **_context(view, "../../../../", ""))


def render_guidance(record: dict, view: View = View()) -> str:
    """The fix guidance of one subject on its own, for the page to reload after a save."""
    here = f"/subjects/{quote(record['key'])}/"
    template = _environment().get_template("_guidance.html")
    return template.render(subject=record, **_context(view, "../../", here))


def _copy_static(qa_dir: Path) -> None:
    source = resources.files("surfaceqa") / "web" / "static"
    with resources.as_file(source) as path:
        shutil.copytree(path, qa_dir / "static", dirs_exist_ok=True)


def _write_viewers(qa_dir: Path, record: dict) -> None:
    for meta in run_metas(qa_dir, record["key"]):
        folder = qa_dir / "subjects" / record["key"] / "runs" / meta["run"]
        (folder / VIEWER_PAGE).write_text(render_viewer(record, meta))


def write_site(qa_dir: Path) -> None:
    """The read-only pages: what `surfaceqa serve` shows to someone who has not given a name."""
    qa_dir = Path(qa_dir)
    records = subject_records(qa_dir)
    _copy_static(qa_dir)
    for record in records:
        (qa_dir / "subjects" / record["key"] / "index.html").write_text(render_subject(record))
        _write_viewers(qa_dir, record)
    (qa_dir / "index.html").write_text(render_index(records))
