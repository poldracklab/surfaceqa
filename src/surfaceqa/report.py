"""Write the report: how errors are spread over the subjects and regions of a QA directory."""

import csv
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from surfaceqa import summary
from surfaceqa.checklist import WHAT
from surfaceqa.consensus import combine
from surfaceqa.protocol import load_protocol
from surfaceqa.review_store import list_reviews
from surfaceqa.site import environment, subject_records

REPORT_DIR = "report"
PAGE = "index.html"
TABLES = ("region_ratings.tsv", "problem_kinds.tsv", "indicator_agreement.tsv")
STEP = {"none": "step0", "ok": "step0", "minor": "step1", "concern": "step1",
        "major": "step2", "exclude": "step2"}  # the colour step of each level on its scale
EXTRA_LABELS = {summary.DISAGREEMENT: "Disagreement", summary.UNREVIEWED: "Not reviewed",
                summary.UNRATABLE: "Could not be rated"}


def _fact(qa_dir: Path, record: dict) -> dict:
    reviews = list_reviews(qa_dir, record["key"], record["run"]) if record["has_run"] else []
    return {"key": record["key"], "source": record["source"], "name": record["name"],
            "href": f"../subjects/{quote(record['key'])}/index.html", "edited": record["edited"],
            "final": combine(reviews) if record["has_run"] else None,
            "drafts": sum(1 for review in reviews if not review["submitted"]),
            "findings": record["qa"]}


def subject_facts(qa_dir: Path) -> list[dict]:
    """What is known about every subject: its reviews combined now, and its indicator results."""
    return [_fact(Path(qa_dir), record) for record in subject_records(qa_dir)]


def _labels() -> dict[str, str]:
    protocol = load_protocol()
    levels = protocol["region_scale"] + protocol["pass_scale"]
    kinds = {kind["id"]: kind["label"] for kind in protocol["mark_kinds"]}
    return {**{level["id"]: level["label"] for level in levels}, **kinds, **EXTRA_LABELS}


def _segments(counts: dict[str, int]) -> list[dict]:
    """The parts of a stacked bar: each level with its share of the subjects."""
    total = sum(counts.values()) or 1
    return [{"level": level, "n": n, "percent": round(100 * n / total, 2), "step": STEP.get(level, level)}
            for level, n in counts.items() if n]


def _region_rows(facts: list[dict]) -> list[dict]:
    return [{**row, "segments": _segments(row["counts"])} for row in summary.region_ratings(facts)]


def _section(source: str, facts: list[dict]) -> dict:
    state = summary.progress(facts)
    return {"source": source, "progress": state,
            "has_ratings": state["reviewed"] + state["disagreement"] > 0,
            "unbuilt": sum(1 for fact in facts if fact["final"] is None),
            "grades": summary.grade_counts(facts), "regions": _region_rows(facts),
            "problems": summary.problem_kinds(facts), "grid": summary.subject_grid(facts),
            "indicators": summary.indicator_summary(facts),
            "not_computed": summary.not_computed(facts),
            "finding_kinds": summary.finding_kinds(facts), "agreement": summary.agreement(facts)}


def _with_maxima(section: dict) -> dict:
    """The largest cell of each heat table, against which its cells are shaded."""
    subjects = [cell["subjects"] for row in section["problems"] for cell in row["cells"].values()]
    findings = [n for row in section["finding_kinds"] for n in row["cells"].values()]
    return {**section, "most_marked": max(subjects, default=0) or 1,
            "most_found": max(findings, default=0) or 1,
            "most_graded": max((n for _, n in section["grades"]), default=0) or 1}


def _sections(facts: list[dict]) -> list[dict]:
    sources = dict.fromkeys(fact["source"] for fact in facts)
    return [_with_maxima(_section(source, [f for f in facts if f["source"] == source]))
            for source in sources]


def _replace(path: Path, write) -> None:
    """Write a file whole: a reader never gets a page that is still being written."""
    partial = path.with_name(f".{path.name}.{os.getpid()}.partial")
    with open(partial, "w", newline="") as handle:
        write(handle)
    os.replace(partial, path)


def _write_table(path: Path, header: list[str], rows: list[list]) -> None:
    def write(handle) -> None:
        csv.writer(handle, delimiter="\t", lineterminator="\n").writerows([header, *rows])

    _replace(path, write)


def _region_table(sections: list[dict]) -> list[list]:
    return [[s["source"], row["item"], level, n]
            for s in sections for row in s["regions"] for level, n in row["counts"].items()]


def _problem_table(sections: list[dict]) -> list[list]:
    return [[s["source"], row["region"], kind, cell["subjects"], cell["marks"]]
            for s in sections for row in s["problems"] for kind, cell in row["cells"].items()]


def _agreement_table(sections: list[dict]) -> list[list]:
    return [[s["source"], row["region"], finding, level, n]
            for s in sections for row in s["agreement"]
            for finding, side in (("yes", "fired"), ("no", "quiet"))
            for level, n in row[side].items()]


def _write_tables(folder: Path, sections: list[dict]) -> None:
    _write_table(folder / TABLES[0], ["source", "item", "level", "subjects"], _region_table(sections))
    _write_table(folder / TABLES[1], ["source", "region", "kind", "subjects", "marks"],
                 _problem_table(sections))
    _write_table(folder / TABLES[2], ["source", "region", "finding", "rating", "subjects"],
                 _agreement_table(sections))


def write_report(qa_dir: Path, now: datetime | None = None) -> Path:
    """Make the report page and its tables from the reviews and findings as they are now."""
    qa_dir = Path(qa_dir)
    facts = subject_facts(qa_dir)
    sections = _sections(facts)
    folder = qa_dir / REPORT_DIR
    folder.mkdir(exist_ok=True)
    made = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    page = environment().get_template("report.html").render(
        name=qa_dir.name, made=made, overall=summary.progress(facts), sections=sections,
        labels=_labels(), tables=TABLES, steps=STEP, kinds_of_finding=summary.FINDING_KINDS,
        finding_labels=WHAT)
    _replace(folder / PAGE, lambda handle: handle.write(page))
    _write_tables(folder, sections)
    return folder / PAGE



def report_made(qa_dir: Path) -> str | None:
    """When the report page was last made, or None when there is none."""
    page = Path(qa_dir) / REPORT_DIR / PAGE
    if not page.is_file():
        return None
    return datetime.fromtimestamp(page.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
