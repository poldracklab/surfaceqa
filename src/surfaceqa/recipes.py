"""The fix recipes: what to edit for each kind of marked problem, kept in a versioned file."""

import json
from functools import cache
from importlib import resources

NAMES = {"fastsurfer": "FastSurfer", "freesurfer": "FreeSurfer recon-all"}


@cache
def load_recipes() -> dict:
    return json.loads((resources.files("surfaceqa") / "recipes.json").read_text())


def recipe_for(pipeline: str, kind: str) -> dict | None:
    block = load_recipes()["pipelines"].get(pipeline)
    return None if block is None else block["recipes"].get(kind)


def _same_version(version: str, written_for: str) -> bool:
    return version == written_for or version.startswith(written_for + ".")


def version_warning(pipeline: str, version: str | None) -> str | None:
    """A sentence to show when the recipes were not written for this subject's software."""
    block = load_recipes()["pipelines"].get(pipeline)
    if block is None:
        return "This subject was made by a pipeline this tool has no fix recipes for."
    written_for = f"{NAMES[pipeline]} {block['written_for']}"
    if version is None:
        return (f"The version that made this subject is unknown. The recipes were written "
                f"for {written_for}; check them against your version's documentation.")
    if _same_version(version, block["written_for"]):
        return None
    return (f"This subject was made by {NAMES[pipeline]} {version}. The recipes were written "
            f"for {written_for}; check them against your version's documentation.")
