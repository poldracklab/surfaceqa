"""Which other reconstructions a subject can be compared with in the viewer."""

import re
from pathlib import Path
from urllib.parse import quote

from surfaceqa.layout import read_json, subject_dir

SESSION = re.compile(r"_ses-.*$")
PREFIX = re.compile(r"^(?:sub-|subj-?(?=\d)|sub(?=\d))")
VIEWER_PAGE = "viewer.html"


def subject_label(name: str) -> str:
    """The person a subject folder is named after: sub-07, subj07 and sub-07_ses-x are all 7."""
    label = PREFIX.sub("", SESSION.sub("", name.lower()))
    return str(int(label)) if label.isdigit() else label


def _others(record: dict, records: list[dict]) -> list[dict]:
    """The same person in another subject folder, of this or another source."""
    label = subject_label(record["name"])
    same = [r for r in records if r["key"] != record["key"] and r["has_run"]
            and subject_label(r["name"]) == label]
    return [{"group": "other", "label": f"{r['source']} · {r['name']}",
             "href": f"../{quote(r['key'])}/runs/{r['run']}/{VIEWER_PAGE}"} for r in same]


def run_metas(qa_dir: Path, key: str) -> list[dict]:
    """The meta of every finished run of a subject, newest first."""
    runs = subject_dir(qa_dir, key) / "runs"
    folders = [p for p in runs.iterdir() if p.is_dir()] if runs.is_dir() else []
    metas = [meta for meta in (read_json(p / "meta.json") for p in folders) if meta]
    return sorted(metas, key=lambda meta: meta.get("built", ""), reverse=True)


def _previous(qa_dir: Path, record: dict) -> list[dict]:
    """Earlier runs of this subject: what it looked like before it was edited and rerun."""
    earlier = [m for m in run_metas(qa_dir, record["key"]) if m.get("run") != record["run"]]
    return [{"group": "previous", "label": f"earlier run, built {meta.get('built', '')[:10]}",
             "href": f"runs/{meta['run']}/{VIEWER_PAGE}"} for meta in earlier if meta.get("run")]


def candidates(qa_dir: Path, record: dict, records: list[dict]) -> list[dict]:
    """What the subject page offers under "Compare with"; links are relative to that page."""
    if not record["has_run"]:
        return []
    return _others(record, records) + _previous(qa_dir, record)
