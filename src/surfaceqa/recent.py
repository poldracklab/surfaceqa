"""The QA directories opened on this machine, so the start page can offer them again."""

import json
import os
from datetime import datetime
from pathlib import Path

from surfaceqa.build import load_meta
from surfaceqa.discover import source_root
from surfaceqa.layout import read_json, replace_text
from surfaceqa.settings import sources as recorded_sources
from surfaceqa.start import is_qa_dir

RECENT_FILE = "recent.json"
KEPT = 20


def home() -> Path:
    """Where the tool keeps what belongs to this machine and not to a QA directory."""
    return Path(os.environ.get("SURFACEQA_HOME") or Path.home() / ".surfaceqa")


def _entries() -> list[dict]:
    stored = read_json(home() / RECENT_FILE)
    return [e for e in stored if _valid(e)] if isinstance(stored, list) else []


def _valid(entry) -> bool:
    return (isinstance(entry, dict) and isinstance(entry.get("path"), str)
            and isinstance(entry.get("opened"), str))


def _save(entries: list[dict]) -> None:
    home().mkdir(parents=True, exist_ok=True)
    replace_text(home() / RECENT_FILE, json.dumps(entries[:KEPT], indent=1))


def _others(qa_dir: Path) -> list[dict]:
    path = str(Path(qa_dir).resolve())
    return [entry for entry in _entries() if entry["path"] != path]


def remember(qa_dir: Path, now: datetime | None = None) -> None:
    opened = (now or datetime.now()).isoformat(timespec="seconds")
    _save([{"path": str(Path(qa_dir).resolve()), "opened": opened}, *_others(qa_dir)])


def forget(qa_dir: Path) -> None:
    _save(_others(qa_dir))


def _source_names(qa_dir: Path) -> list[str]:
    recorded = {source_root(path).name for path in recorded_sources(qa_dir)}
    return sorted(recorded or {_source_of(qa_dir, key) for key in _keys(qa_dir)} - {None})


def _keys(qa_dir: Path) -> list[str]:
    try:
        return sorted(p.name for p in (qa_dir / "subjects").iterdir() if p.is_dir())
    except OSError:
        return []


def _source_of(qa_dir: Path, key: str) -> str | None:
    meta = load_meta(qa_dir, key)
    return meta.get("source") if meta else key.rsplit("__", 1)[0]


def _when(text: str) -> str:
    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text


def _project(entry: dict) -> dict:
    qa_dir = Path(entry["path"])
    exists = is_qa_dir(qa_dir)
    return {"path": entry["path"], "opened": _when(entry["opened"]), "exists": exists,
            "sources": _source_names(qa_dir) if exists else [],
            "n_subjects": len(_keys(qa_dir)) if exists else 0}


def projects() -> list[dict]:
    """The remembered QA directories, most recently opened first."""
    return [_project(entry) for entry in sorted(_entries(), key=lambda e: e["opened"], reverse=True)]
