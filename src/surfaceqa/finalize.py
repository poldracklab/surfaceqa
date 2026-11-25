"""Write the final labels of every subject: <qa>/final/<subject key>.json."""

import json
from pathlib import Path

from surfaceqa.consensus import combine
from surfaceqa.layout import current_run_dir, read_json, subject_folders
from surfaceqa.protocol import item_ids, load_protocol
from surfaceqa.review_store import list_reviews
from surfaceqa.reviews import item_title


def _keys_with_a_run(qa_dir: Path) -> list[tuple[str, str]]:
    runs = [(folder.name, current_run_dir(qa_dir, folder.name)) for folder in subject_folders(qa_dir)]
    return [(key, run_dir.name) for key, run_dir in runs if run_dir is not None]


def finalize(qa_dir: Path) -> list[dict]:
    """Combine the reviews of each subject's current run and store the result."""
    folder = Path(qa_dir) / "final"
    folder.mkdir(exist_ok=True)
    records = []
    for key, run in _keys_with_a_run(qa_dir):
        record = {"key": key, "run": run, **combine(list_reviews(qa_dir, key, run))}
        (folder / f"{key}.json").write_text(json.dumps(record, indent=1))
        records.append(record)
    return records


SHAPE = {"key": str, "run": str, "status": str, "reviewers": list, "inputs": dict,
         "unratable": bool, "items": dict, "grade": dict, "marks": list, "needs_fix": list,
         "disagreements": list}


def _usable(final) -> bool:
    """A file with the whole shape of a final record; anything else is ignored."""
    if not isinstance(final, dict):
        return False
    if not all(isinstance(final.get(name), kind) for name, kind in SHAPE.items()):
        return False
    items = [final["items"].get(item) for item in item_ids()]
    whole = all(isinstance(entry, dict) and {"final", "ratings", "disagree"} <= set(entry)
                for entry in items)
    return whole and {"final", "grades", "disagree"} <= set(final["grade"])


def load_final(qa_dir: Path, key: str) -> dict | None:
    final = read_json(Path(qa_dir) / "final" / f"{key}.json")
    return final if _usable(final) else None


def is_stale(final: dict, reviews: list[dict], run: str) -> bool:
    """True when the surfaces or the submitted reviews changed after finalize ran."""
    return final["run"] != run or final["inputs"] != combine(reviews)["inputs"]


def _who_said_what(values: dict[str, str], labels: dict[str, str]) -> str:
    return ", ".join(f"{reviewer} {labels.get(value, value)}" for reviewer, value in values.items())


def describe_disagreement(record: dict) -> str:
    """One line naming what the reviewers of a subject disagree on, and who said what."""
    protocol = load_protocol()
    levels = protocol["region_scale"] + protocol["pass_scale"]
    labels = {level["id"]: level["label"] for level in levels}
    parts = []
    for item in record["disagreements"]:
        if item == "grade":
            parts.append(f"grade ({_who_said_what(record['grade']['grades'], {})})")
        elif item == "unratable":
            parts.append("whether the subject can be rated")
        else:
            said = _who_said_what(record["items"][item]["ratings"], labels)
            parts.append(f"{item_title(item)} ({said})")
    return f"{record['key']}: {'; '.join(parts)}"
