"""Thickness across the subjects of one source folder: the median and spread at each common point."""

import hashlib
import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from surfaceqa import thresholds
from surfaceqa.layout import current_run_dir, read_json
from surfaceqa.thickness_map import HEMIS, load_thickness_map, map_signature

COHORT_VERSION = 1  # raise when the statistics change, so they are computed again
MAD_TO_SD = 1.4826


@dataclass
class Cohort:
    source: str
    n: int  # subjects with a thickness map
    signature: str
    median: dict[str, np.ndarray] | None  # None while there are too few subjects
    spread: dict[str, np.ndarray] | None  # robust standard deviation


def _folder(qa_dir: Path) -> Path:
    return Path(qa_dir) / "cohort"


def _members(qa_dir: Path) -> dict[str, dict[str, Path]]:
    """source -> {subject key: current run folder}, for the runs that have a thickness map."""
    root = Path(qa_dir) / "subjects"
    sources: dict[str, dict[str, Path]] = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        members = sources.setdefault(folder.name.partition("__")[0], {})
        run_dir = current_run_dir(qa_dir, folder.name)
        if run_dir is not None and map_signature(run_dir) is not None:
            members[folder.name] = run_dir
    return sources


def _signature(members: dict[str, Path]) -> str:
    made_from = {key: [run_dir.name, map_signature(run_dir)] for key, run_dir in members.items()}
    text = json.dumps({"version": COHORT_VERSION, "minimum": thresholds.MIN_COHORT,
                       "members": made_from}, sort_keys=True)
    return hashlib.sha1(text.encode()).hexdigest()


def _statistics(stack: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray] | None:
    """Median and robust spread over subjects; NaN where too few of them have cortex."""
    if not stack:
        return None
    values = np.stack(stack).astype(np.float64)
    enough = np.isfinite(values).sum(axis=0) >= thresholds.MIN_COHORT
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # points where no subject has cortex
        median = np.nanmedian(values, axis=0)
        spread = MAD_TO_SD * np.nanmedian(np.abs(values - median), axis=0)
    return (np.where(enough, median, np.nan).astype(np.float32),
            np.where(enough, spread, np.nan).astype(np.float32))


def _arrays(members: dict[str, Path]) -> dict[str, np.ndarray]:
    maps = [m for m in (load_thickness_map(run_dir) for run_dir in members.values()) if m]
    arrays = {}
    for hemi in HEMIS:
        found = _statistics([m[hemi] for m in maps if hemi in m])
        if found is not None:
            arrays[f"{hemi}_median"], arrays[f"{hemi}_spread"] = found
    return arrays


def _write_statistics(path: Path, members: dict[str, Path]) -> None:
    partial = path.with_suffix(".partial")
    with open(partial, "wb") as handle:
        np.savez_compressed(handle, **_arrays(members))
    os.replace(partial, path)


def _update_source(qa_dir: Path, source: str, members: dict[str, Path]) -> bool:
    """Bring one source folder's statistics up to date; True when they changed."""
    folder = _folder(qa_dir)
    signature = _signature(members)
    stored = read_json(folder / f"{source}.json") or {}
    switched_on = len(members) >= thresholds.MIN_COHORT
    if stored.get("signature") == signature and (folder / f"{source}.npz").is_file() == switched_on:
        return False
    folder.mkdir(parents=True, exist_ok=True)
    if switched_on:
        _write_statistics(folder / f"{source}.npz", members)
    else:
        (folder / f"{source}.npz").unlink(missing_ok=True)
    record = {"version": COHORT_VERSION, "n": len(members), "signature": signature,
              "members": {key: run_dir.name for key, run_dir in members.items()}}
    (folder / f"{source}.json").write_text(json.dumps(record, indent=1))
    return True


def update_cohorts(qa_dir: Path) -> set[str]:
    """Recompute the statistics of every source folder whose subjects changed; returns those."""
    return {source for source, members in _members(qa_dir).items()
            if _update_source(Path(qa_dir), source, members)}


def _read_statistics(path: Path) -> tuple[dict, dict] | None:
    try:
        with np.load(path) as stored:
            hemis = [hemi for hemi in HEMIS if f"{hemi}_median" in stored.files]
            return ({hemi: stored[f"{hemi}_median"] for hemi in hemis},
                    {hemi: stored[f"{hemi}_spread"] for hemi in hemis})
    except Exception:
        return None


def load_cohort(qa_dir: Path, source: str) -> Cohort | None:
    """The stored statistics of a source folder; None when `update_cohorts` never saw it."""
    record = read_json(_folder(qa_dir) / f"{source}.json")
    if record is None:
        return None
    median, spread = _read_statistics(_folder(qa_dir) / f"{source}.npz") or (None, None)
    return Cohort(source, record["n"], record["signature"], median, spread)
