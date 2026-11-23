"""Write the index page and one page per subject from what is in the QA directory."""

import json
import shutil
from importlib import resources
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, PackageLoader, select_autoescape

from surfaceqa.build import load_meta
from surfaceqa.layout import current_run_dir
from surfaceqa.checklist import checklist_sections, finding_text
from surfaceqa.qa import load_findings
from surfaceqa.regions import REGIONS
from surfaceqa.scoring import rank_within_pipeline

VIEW_ORDER = ("coronal", "sagittal", "axial")
NO_RUN_TEMPLATE = {"missing files": "missing.html", "build failed": "failed.html"}


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


def _subject_record(qa_dir: Path, folder: Path) -> dict:
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
    top = found["findings"][0] if found["findings"] else None
    largest = f"{finding_text(top)} · {titles[top['region']]}" if top else ""
    not_run = [i for i in found["indicators"] if i["status"] == "not run"]
    partial = [i for i in found["indicators"] if i["status"] == "ran" and i["reason"]]
    any_ran = len(not_run) < len(found["indicators"])
    return {"qa": found, "score": found["score"] if any_ran else None, "qa_failed": False,
            "largest": largest, "not_run": not_run, "partial": partial,
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


def _subject_records(qa_dir: Path) -> list[dict]:
    root = qa_dir / "subjects"
    folders = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    records = [_subject_record(qa_dir, folder) for folder in folders]
    _add_ranks(records)
    return sorted(records, key=_review_order)


def _copy_static(qa_dir: Path) -> None:
    source = resources.files("surfaceqa") / "web" / "static"
    with resources.as_file(source) as path:
        shutil.copytree(path, qa_dir / "static", dirs_exist_ok=True)


def _write_subject_page(env: Environment, qa_dir: Path, record: dict) -> None:
    name = "subject.html" if record["has_run"] else NO_RUN_TEMPLATE[record["status"]]
    template = env.get_template(name)
    html = template.render(subject=record, views=VIEW_ORDER, root="../../")
    (qa_dir / "subjects" / record["key"] / "index.html").write_text(html)


def write_site(qa_dir: Path) -> None:
    qa_dir = Path(qa_dir)
    env = _environment()
    records = _subject_records(qa_dir)
    _copy_static(qa_dir)
    for record in records:
        _write_subject_page(env, qa_dir, record)
    index = env.get_template("index.html").render(subjects=records, root="")
    (qa_dir / "index.html").write_text(index)
