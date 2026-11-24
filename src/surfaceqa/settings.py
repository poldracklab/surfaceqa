"""Settings kept in the QA directory: the launch line that reruns the subjects of a source."""

import json
from pathlib import Path

from surfaceqa.invocation import PLACEHOLDER
from surfaceqa.layout import read_json

SETTINGS_FILE = "settings.json"


def has_placeholder(template: str) -> bool:
    return PLACEHOLDER in template


def _templates(qa_dir: Path) -> dict[str, str]:
    stored = read_json(Path(qa_dir) / SETTINGS_FILE)
    templates = stored.get("rerun_templates") if isinstance(stored, dict) else None
    if not isinstance(templates, dict):
        return {}
    return {source: text for source, text in templates.items()
            if isinstance(text, str) and has_placeholder(text)}


def save_rerun_template(qa_dir: Path, sources: list[str], template: str) -> None:
    """Remember `template` for these source folders; other sources keep theirs."""
    templates = {**_templates(qa_dir), **{source: template for source in sources}}
    Path(qa_dir).mkdir(parents=True, exist_ok=True)
    (Path(qa_dir) / SETTINGS_FILE).write_text(json.dumps({"rerun_templates": templates}, indent=1))


def rerun_template(qa_dir: Path, source: str) -> str | None:
    return _templates(qa_dir).get(source)
