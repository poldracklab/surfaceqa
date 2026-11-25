"""A QA directory built by someone else is data: nothing in it decides where surfaceqa writes."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from surfaceqa.layout import current_run_dir, run_meta
from surfaceqa.server import create_app
from surfaceqa.server_start import StartMode
from surfaceqa.site import subject_records, write_site

TOKEN = "tok-9f3a-launch"
BASE = "http://127.0.0.1:8765"
FIRST = "fastsurfer__sub-01"
MISSING = "fastsurfer__sub-02"  # the subject of the `qa` fixture with a missing surface


@pytest.fixture
def elsewhere(tmp_path_factory) -> Path:
    """A folder outside the QA directory, with a page of its owner's."""
    folder = tmp_path_factory.mktemp("elsewhere")
    (folder / "index.html").write_text("ORIGINAL")
    return folder


def _open(qa_dir: Path) -> TestClient:
    """Open the directory from the start page, the way a researcher does."""
    client = TestClient(create_app(None, start=StartMode(TOKEN)), base_url=BASE, follow_redirects=False)
    client.get(f"/?token={TOKEN}")
    response = client.post("/start/open", data={"path": str(qa_dir)}, headers={"origin": BASE})
    assert response.status_code == 303
    return client


def _tree(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


def _edit_json(path: Path, **fields) -> None:
    path.write_text(json.dumps({**json.loads(path.read_text()), **fields}))


def _meta_file(qa: Path, key: str = FIRST) -> Path:
    return current_run_dir(qa, key) / "meta.json"


# ---- the subject key is the folder's name ------------------------------------------------------

@pytest.mark.parametrize("key", ["{elsewhere}", "../../../{elsewhere_name}", "other__subject"])
def test_a_key_in_missing_json_is_ignored(qa, elsewhere, key):
    spoofed = key.format(elsewhere=elsewhere, elsewhere_name=elsewhere.name)
    _edit_json(qa / "subjects" / MISSING / "missing.json", key=spoofed)
    assert MISSING in [record["key"] for record in subject_records(qa)]
    assert spoofed not in [record["key"] for record in subject_records(qa)]


def test_a_key_in_meta_json_is_ignored(qa, elsewhere):
    _edit_json(_meta_file(qa), key=str(elsewhere))
    assert FIRST in [record["key"] for record in subject_records(qa)]


def test_opening_a_directory_with_a_spoofed_key_writes_nothing_outside_it(qa, elsewhere):
    _edit_json(qa / "subjects" / MISSING / "missing.json", key=str(elsewhere))
    (qa / "index.html").unlink()
    before = _tree(elsewhere)
    client = _open(qa)
    assert (elsewhere / "index.html").read_text() == "ORIGINAL" and _tree(elsewhere) == before
    assert client.get(f"/subjects/{MISSING}/").status_code == 200


# ---- run names ---------------------------------------------------------------------------------

@pytest.mark.parametrize("run", ["../../../x", "/tmp/x", "ABCDEF012345", "0123456789abc", ""])
def test_a_current_run_that_is_not_a_run_name_is_no_run(qa, run):
    (qa / "subjects" / FIRST / "current.json").write_text(json.dumps({"run": run}))
    assert current_run_dir(qa, FIRST) is None


def test_the_run_is_the_name_of_its_folder_whatever_meta_says(qa):
    run_dir = _meta_file(qa).parent
    _edit_json(_meta_file(qa), run="../../../../x")
    assert run_meta(run_dir)["run"] == run_dir.name


@pytest.mark.parametrize("field", ["source", "name"])
@pytest.mark.parametrize("value", ["../x", "a/b", "/abs", "a\\b", "..", ".", "", 3, None])
def test_meta_whose_source_or_name_is_not_a_plain_name_is_not_read(qa, field, value):
    _edit_json(_meta_file(qa), **{field: value})
    assert run_meta(_meta_file(qa).parent) is None


def test_meta_of_an_ordinary_run_is_read(qa):
    meta = run_meta(_meta_file(qa).parent)
    assert meta["source"] == "fastsurfer" and meta["name"] == "sub-01"


def test_a_source_in_missing_json_that_is_not_a_plain_name_is_ignored(qa):
    _edit_json(qa / "subjects" / MISSING / "missing.json", source="../../x", name="a/b")
    record = next(r for r in subject_records(qa) if r["key"] == MISSING)
    assert (record["source"], record["name"]) == ("fastsurfer", "sub-02")


def test_a_viewer_is_not_written_for_meta_naming_a_run_elsewhere(qa, elsewhere):
    _edit_json(_meta_file(qa), run=str(elsewhere))
    write_site(qa)
    assert not (elsewhere / "viewer.html").exists()


# ---- links -------------------------------------------------------------------------------------

def test_a_subject_folder_that_is_a_link_is_not_a_subject(qa, elsewhere):
    (elsewhere / "current.json").write_text("{}")
    (qa / "subjects" / "linked__subject").symlink_to(elsewhere, target_is_directory=True)
    before = _tree(elsewhere)
    write_site(qa)
    assert "linked__subject" not in [record["key"] for record in subject_records(qa)]
    assert (elsewhere / "index.html").read_text() == "ORIGINAL" and _tree(elsewhere) == before


def test_a_run_folder_that_is_a_link_is_not_read(qa, elsewhere):
    run_dir = _meta_file(qa).parent
    target = elsewhere / run_dir.name
    run_dir.rename(target)
    run_dir.symlink_to(target, target_is_directory=True)
    assert run_meta(run_dir) is None


def test_a_page_that_is_a_link_is_replaced_not_written_through(qa, elsewhere):
    target = elsewhere / "index.html"
    for page in (qa / "index.html", qa / "subjects" / FIRST / "index.html"):
        page.unlink()
        page.symlink_to(target)
    write_site(qa)
    assert target.read_text() == "ORIGINAL"
    assert not (qa / "index.html").is_symlink() and "sub-01" in (qa / "index.html").read_text()


def test_static_files_that_are_links_are_replaced_not_written_through(qa, elsewhere):
    target = elsewhere / "index.html"
    style = next((qa / "static").glob("*.css"))
    style.unlink()
    style.symlink_to(target)
    write_site(qa)
    assert target.read_text() == "ORIGINAL" and not style.is_symlink()


def test_a_static_folder_that_is_a_link_is_replaced(qa, elsewhere):
    import shutil
    shutil.rmtree(qa / "static")
    (qa / "static").symlink_to(elsewhere, target_is_directory=True)
    before = _tree(elsewhere)
    write_site(qa)
    assert _tree(elsewhere) == before and not (qa / "static").is_symlink()
