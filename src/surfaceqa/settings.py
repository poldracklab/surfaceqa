"""Settings kept in the QA directory: the launch line that reruns the subjects of a source."""

import json
from pathlib import Path

from surfaceqa.invocation import PLACEHOLDER
from surfaceqa.layout import read_json, replace_text

SETTINGS_FILE = "settings.json"


def has_placeholder(template: str) -> bool:
    return PLACEHOLDER in template


def _stored(qa_dir: Path) -> dict:
    stored = read_json(Path(qa_dir) / SETTINGS_FILE)
    return stored if isinstance(stored, dict) else {}


def _save(qa_dir: Path, name: str, value) -> None:
    """Change one setting; the others stay as they are."""
    Path(qa_dir).mkdir(parents=True, exist_ok=True)
    replace_text(Path(qa_dir) / SETTINGS_FILE, json.dumps({**_stored(qa_dir), name: value}, indent=1))


def _templates(qa_dir: Path) -> dict[str, str]:
    templates = _stored(qa_dir).get("rerun_templates")
    if not isinstance(templates, dict):
        return {}
    return {source: text for source, text in templates.items()
            if isinstance(text, str) and has_placeholder(text)}


def save_rerun_template(qa_dir: Path, sources: list[str], template: str) -> None:
    """Remember `template` for these source folders; other sources keep theirs."""
    _save(qa_dir, "rerun_templates", {**_templates(qa_dir), **{source: template for source in sources}})


def rerun_template(qa_dir: Path, source: str) -> str | None:
    return _templates(qa_dir).get(source)


def sources(qa_dir: Path) -> list[Path]:
    """The folders this QA directory was built from, as the user gave them."""
    stored = _stored(qa_dir).get("sources")
    return [Path(text) for text in stored if isinstance(text, str)] if isinstance(stored, list) else []


def save_sources(qa_dir: Path, paths: list[Path]) -> None:
    """Add these folders to the ones the QA directory is built from."""
    known = [str(path) for path in sources(qa_dir)]
    added = [str(Path(path).resolve()) for path in paths]
    _save(qa_dir, "sources", list(dict.fromkeys(known + added)))
