"""Record, per run, how a subject was made: its original command and whether it was edited.

Kept in the run folder so the fix guidance works when the source folder is not mounted.
"""

import json
from pathlib import Path

from surfaceqa.discover import SubjectRef
from surfaceqa.edits import BFS, BFS_EDIT, FASTSURFER_SEG_EDIT, RECON_ALL_EDIT_FILES, WM, detect_edits
from surfaceqa.invocation import original_command
from surfaceqa.layout import current_run_dir, read_json
from surfaceqa.pipelines import PipelineInfo

PROVENANCE_VERSION = 2  # raise when what is recorded changes, so it is recorded again
PROVENANCE_FILE = "provenance.json"
WATCHED = ("scripts/deep-seg.log", "scripts/recon-surf.log", "scripts/recon-all.log",
           BFS, BFS_EDIT, FASTSURFER_SEG_EDIT, WM, *RECON_ALL_EDIT_FILES)
SHAPE = {"command": (str, type(None)), "edited": bool, "evidence": list, "signature": dict}


def _signature(subject_dir: Path) -> dict[str, list[int]]:
    """Size and modification time of every file the record is made from."""
    stats = {rel: (subject_dir / rel) for rel in WATCHED}
    return {rel: [path.stat().st_size, path.stat().st_mtime_ns]
            for rel, path in stats.items() if path.is_file()}


def _usable(record) -> bool:
    return isinstance(record, dict) and all(
        isinstance(record.get(name), kind) for name, kind in SHAPE.items())


def _read(run_dir: Path) -> dict | None:
    record = read_json(Path(run_dir) / PROVENANCE_FILE)
    return record if _usable(record) else None


def write_provenance(ref: SubjectRef, pipeline: PipelineInfo, run_dir: Path) -> bool:
    """Write the record unless it is up to date; True when it was written."""
    signature = _signature(ref.path)
    stored = _read(run_dir)
    if stored and stored.get("version") == PROVENANCE_VERSION and stored["signature"] == signature:
        return False
    evidence = detect_edits(ref.path, pipeline.name)
    record = {"version": PROVENANCE_VERSION, "command": original_command(ref.path, pipeline.name),
              "edited": bool(evidence), "evidence": evidence, "signature": signature}
    (Path(run_dir) / PROVENANCE_FILE).write_text(json.dumps(record, indent=1))
    return True


def load_provenance(qa_dir: Path, key: str) -> dict | None:
    run_dir = current_run_dir(qa_dir, key)
    return None if run_dir is None else _read(run_dir)
