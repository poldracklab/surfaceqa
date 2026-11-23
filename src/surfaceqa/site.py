"""Write the index page and one page per subject from what is in the QA directory."""

import json
import shutil
from importlib import resources
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, PackageLoader, select_autoescape

from surfaceqa.build import load_meta

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
            "href": f"subjects/{quote(key)}/index.html"}


def _subject_records(qa_dir: Path) -> list[dict]:
    root = qa_dir / "subjects"
    folders = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    return [_subject_record(qa_dir, folder) for folder in folders]


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
