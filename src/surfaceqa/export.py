"""Write the review tables: ratings, marks, final labels and indicator values."""

import csv
from pathlib import Path

from surfaceqa.finalize import is_stale, load_final
from surfaceqa.layout import run_meta, subject_dir
from surfaceqa.protocol import item_ids
from surfaceqa.provenance import run_provenance
from surfaceqa.review_store import all_reviews, list_reviews
from surfaceqa.site import subject_records

SUBJECT = ["key", "source", "subject", "pipeline", "version", "edited", "run"]
RATINGS = [*SUBJECT, "current_run", "reviewer", "protocol", "submitted", "revised", "item",
           "rating", "note"]
MARKS = ["key", "edited", "run", "current_run", "reviewer", "region", "kind", "surface", "vertex",
         "grid_x", "grid_y", "grid_z", "tkr_x", "tkr_y", "tkr_z", "finding", "note"]
FINAL = ["key", "edited", "run", "status", "reviewers", "item", "final", "disagree"]
INDICATORS = [*SUBJECT, "score", "indicator", "status", "n_findings", "reason"]


def _cell(value) -> str:
    """One table cell: empty for nothing, and never a tab or a line break."""
    text = "" if value is None else str(value)
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _yes(flag) -> str:
    """Blank when it is not known: never recorded, or a file could not be checked."""
    return "" if flag is None else ("yes" if flag else "no")


def _write(path: Path, header: list[str], rows: list[dict]) -> Path:
    with open(path, "w", newline="") as handle:
        # quoted where needed, the way spreadsheet, pandas and R readers expect by default
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows([_cell(row.get(column)) for column in header] for row in rows)
    return path


def _subject_columns(record: dict) -> dict:
    return {"key": record["key"], "source": record["source"], "subject": record["name"],
            "pipeline": record["pipeline"], "version": record["version"],
            "edited": _yes(record["edited"])}


def _submitted(qa_dir: Path, record: dict) -> list[dict]:
    return [review for review in all_reviews(qa_dir, record["key"]) if review["submitted"]]


def _run_columns(qa_dir: Path, key: str, run: str) -> dict:
    """What is recorded about one run of a subject, which may be an earlier one than the
    current: its pipeline, version and edit state. Blank where the run no longer says."""
    run_dir = subject_dir(qa_dir, key) / "runs" / run
    meta, provenance = run_meta(run_dir) or {}, run_provenance(run_dir)
    return {"pipeline": meta.get("pipeline"), "version": meta.get("version"),
            "edited": _yes(provenance["edited"] if provenance else None)}


def _review_rows(qa_dir: Path, record: dict, review: dict) -> list[dict]:
    """One row per item of a review, then its grade, then why it could not be rated."""
    head = {**_subject_columns(record), **_run_columns(qa_dir, record["key"], review["run"]),
            "run": review["run"],
            "current_run": _yes(review["run"] == record.get("run")),
            "reviewer": review["reviewer"], "protocol": review.get("protocol"),
            "submitted": review["submitted"], "revised": _yes(review.get("revised"))}
    rows = [{**head, "item": item, **review["items"].get(item, {})} for item in item_ids()]
    rows.append({**head, "item": "overall", "rating": review["grade"], "note": review.get("notes")})
    if review.get("unratable"):
        rows.append({**head, "item": "unratable", "note": review["unratable"]})
    return rows


def _mark_rows(qa_dir: Path, record: dict, review: dict) -> list[dict]:
    edited = _run_columns(qa_dir, record["key"], review["run"])["edited"]
    head = {"key": record["key"], "edited": edited, "run": review["run"],
            "reviewer": review["reviewer"],
            "current_run": _yes(review["run"] == record.get("run"))}
    rows = []
    for mark in review["marks"]:
        grid = dict(zip(("grid_x", "grid_y", "grid_z"), mark["grid"]))
        tkr = dict(zip(("tkr_x", "tkr_y", "tkr_z"), mark.get("tkr") or ()))
        rows.append({**head, **mark, **grid, **tkr})
    return rows


def _final_rows(qa_dir: Path, record: dict) -> list[dict]:
    final = load_final(qa_dir, record["key"])
    if final is None:
        return []
    run = record.get("run")
    stale = run is None or is_stale(final, list_reviews(qa_dir, record["key"], run), run)
    edited = _run_columns(qa_dir, record["key"], final["run"])["edited"]
    head = {"key": final["key"], "edited": edited, "run": final["run"],
            "status": "stale" if stale else final["status"], "reviewers": ",".join(final["reviewers"])}
    rows = [{**head, "item": item, "final": entry["final"], "disagree": _yes(entry["disagree"])}
            for item, entry in final["items"].items()]
    rows.append({**head, "item": "overall", "final": final["grade"]["final"],
                 "disagree": _yes(final["grade"]["disagree"])})
    rows.append({**head, "item": "unratable", "final": _yes(final["unratable"]),
                 "disagree": _yes("unratable" in final["disagreements"])})
    return rows


def _indicator_rows(record: dict) -> list[dict]:
    head = {**_subject_columns(record), "run": record.get("run"), "score": record["score"]}
    if not record["qa"]:
        return [{**head, "status": "not computed"}]
    return [{**head, "indicator": i["name"], "status": i["status"], "n_findings": i["n_findings"],
             "reason": i["reason"]} for i in record["qa"]["indicators"]]


def export_tables(qa_dir: Path, out_dir: Path | None = None) -> list[Path]:
    """Write ratings.tsv, marks.tsv, final.tsv and indicators.tsv; submitted reviews only."""
    qa_dir = Path(qa_dir)
    out_dir = Path(out_dir) if out_dir else qa_dir / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    records = sorted(subject_records(qa_dir), key=lambda record: record["key"])
    reviews = [(qa_dir, record, review) for record in records for review in _submitted(qa_dir, record)]
    tables = {
        "ratings": (RATINGS, [row for found in reviews for row in _review_rows(*found)]),
        "marks": (MARKS, [row for found in reviews for row in _mark_rows(*found)]),
        "final": (FINAL, [row for record in records for row in _final_rows(qa_dir, record)]),
        "indicators": (INDICATORS, [row for record in records for row in _indicator_rows(record)]),
    }
    return [_write(out_dir / f"{name}.tsv", header, rows) for name, (header, rows) in tables.items()]
