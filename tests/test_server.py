import json

import pytest
from fastapi.testclient import TestClient

from surfaceqa.server import create_app


def test_server_serves_index_and_assets(qa):
    client = TestClient(create_app(qa))
    assert client.get("/").status_code == 200
    assert "surfaceqa" in client.get("/").text
    assert client.get("/static/logic.js").status_code == 200
    run = json.loads((qa / "subjects" / "fastsurfer__sub-01" / "current.json").read_text())["run"]
    base = f"/subjects/fastsurfer__sub-01/runs/{run}"
    assert client.get(f"{base}/meta.json").json()["key"] == "fastsurfer__sub-01"
    assert client.get(f"{base}/slices/coronal/010.jpg").headers["content-type"] == "image/jpeg"
    assert client.get(f"{base}/contours_coronal.bin").status_code == 200


@pytest.mark.parametrize("path", ["/%2e%2e/%2e%2e/etc/passwd", "/..%2f..%2fetc/passwd",
                                  "/static/%2e%2e/%2e%2e/%2e%2e/etc/passwd"])
def test_server_does_not_serve_outside_qa_dir(qa, path):
    # encoded, because the test client collapses a literal /../ before sending
    (qa.parent / "secret.txt").write_text("secret")
    client = TestClient(create_app(qa))
    assert client.get(path).status_code in (400, 404)
    assert client.get("/%2e%2e/secret.txt").status_code in (400, 404)


# ---- reviewing -------------------------------------------------------------------------------

from surfaceqa.layout import current_run_dir
from surfaceqa.review_store import load_review
from tests.reviewing import make_review

FIRST, SECOND, RECON = "fastsurfer__sub-01", "fastsurfer__sub-02", "freesurfer-8.2.0__sub-01"


def _client(qa, reviewer=None, blind=False) -> TestClient:
    client = TestClient(create_app(qa, blind=blind), follow_redirects=False)
    if reviewer:
        client.cookies.set("surfaceqa_reviewer", reviewer)
    return client


def _payload(qa, key, **ratings) -> dict:
    review = make_review("ignored", key, current_run_dir(qa, key).name, **ratings)
    return {k: review[k] for k in ("run", "items", "marks", "grade", "notes", "unratable")}


def _files(folder) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def test_setting_a_name_sets_a_cookie_and_redirects_back(qa_planted):
    client = _client(qa_planted)
    response = client.post("/reviewer", data={"name": "cat", "next": f"/subjects/{FIRST}/"})
    assert response.status_code == 303 and response.headers["location"] == f"/subjects/{FIRST}/"
    assert "surfaceqa_reviewer=cat" in response.headers["set-cookie"]
    assert "Reviewer: <strong>cat</strong>" in client.get("/").text


def test_clearing_the_name_removes_the_cookie(qa_planted):
    client = _client(qa_planted, "cat")
    response = client.post("/reviewer/clear")
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert 'surfaceqa_reviewer=""' in response.headers["set-cookie"]


@pytest.mark.parametrize("name", ["a/b", "..", "", "a b"])
def test_bad_names_are_refused_and_nothing_is_written(qa_planted, name):
    client = _client(qa_planted)
    response = client.post("/reviewer", data={"name": name, "next": "/"})
    assert response.status_code == 400 and "set-cookie" not in response.headers
    assert "letters" in response.text.lower()
    assert not (qa_planted / "ratings").exists()


@pytest.mark.parametrize("cookie", ["a/b", "..", "../../x"])
def test_a_forged_name_cookie_is_treated_as_no_name(qa_planted, cookie):
    client = _client(qa_planted, cookie)
    assert client.get(f"/api/review/{FIRST}").status_code == 401
    assert client.put(f"/api/review/{FIRST}", json=_payload(qa_planted, FIRST)).status_code == 401
    assert not (qa_planted / "ratings").exists()


@pytest.mark.parametrize("target", ["https://example.org", "//example.org", "/\\example.org", ""])
def test_redirect_target_outside_the_site_is_ignored(qa_planted, target):
    response = _client(qa_planted).post("/reviewer", data={"name": "cat", "next": target})
    assert response.status_code == 303 and response.headers["location"] == "/"


def test_review_api_needs_a_name(qa_planted):
    client = _client(qa_planted)
    assert client.get(f"/api/review/{FIRST}").status_code == 401
    assert client.put(f"/api/review/{FIRST}", json=_payload(qa_planted, FIRST)).status_code == 401
    assert client.post(f"/api/review/{FIRST}/submit", json=_payload(qa_planted, FIRST)).status_code == 401


def test_a_new_reviewer_gets_an_empty_review(qa_planted):
    body = _client(qa_planted, "cat").get(f"/api/review/{FIRST}").json()
    assert body["review"]["reviewer"] == "cat" and body["review"]["items"]["sinus"]["rating"] is None
    assert len(body["missing"]) == 12
    assert not (qa_planted / "ratings").exists()


def test_a_saved_draft_is_returned_on_the_next_get(qa_planted):
    client = _client(qa_planted, "cat")
    saved = client.put(f"/api/review/{FIRST}", json=_payload(qa_planted, FIRST, sinus="minor"))
    assert saved.status_code == 200 and saved.json()["missing"] == []
    review = client.get(f"/api/review/{FIRST}").json()["review"]
    assert review["items"]["sinus"]["rating"] == "minor" and review["reviewer"] == "cat"
    assert review["submitted"] is None and review["saved"]


def test_saving_writes_the_file_under_ratings_for_the_current_run(qa_planted):
    _client(qa_planted, "cat").put(f"/api/review/{FIRST}", json=_payload(qa_planted, FIRST))
    run = current_run_dir(qa_planted, FIRST).name
    assert _files(qa_planted / "ratings") == [f"{FIRST}/{run}/cat.json"]


def test_invalid_rating_is_refused_with_the_field_named(qa_planted):
    payload = _payload(qa_planted, FIRST, t1="major")
    response = _client(qa_planted, "cat").put(f"/api/review/{FIRST}", json=payload)
    assert response.status_code == 422 and "t1" in response.json()["detail"]
    assert not (qa_planted / "ratings").exists()


@pytest.mark.parametrize("body", ["[1, 2]", "not json", '"text"'])
def test_a_body_that_is_not_a_review_is_refused(qa_planted, body):
    response = _client(qa_planted, "cat").put(f"/api/review/{FIRST}", content=body,
                                              headers={"content-type": "application/json"})
    assert response.status_code == 422


def test_save_against_an_old_run_is_refused(qa_planted):
    payload = {**_payload(qa_planted, FIRST), "run": "000000000000"}
    client = _client(qa_planted, "cat")
    for response in (client.put(f"/api/review/{FIRST}", json=payload),
                     client.post(f"/api/review/{FIRST}/submit", json=payload)):
        assert response.status_code == 409 and "reload" in response.json()["detail"].lower()
    assert not (qa_planted / "ratings").exists()


def test_submit_with_unrated_items_is_refused_and_lists_them(qa_planted):
    payload = _payload(qa_planted, FIRST)
    payload["items"]["sinus"]["rating"] = None
    payload["grade"] = None
    response = _client(qa_planted, "cat").post(f"/api/review/{FIRST}/submit", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == ["Sagittal and transverse sinus: not rated",
                                         "Overall grade: not chosen"]
    stored = load_review(qa_planted, FIRST, current_run_dir(qa_planted, FIRST).name, "cat")
    assert stored["submitted"] is None and stored["items"]["cerebellum"]["rating"] == "none"


def test_complete_review_can_be_submitted(qa_planted):
    client = _client(qa_planted, "cat")
    response = client.post(f"/api/review/{FIRST}/submit", json=_payload(qa_planted, FIRST))
    assert response.status_code == 200 and response.json()["review"]["submitted"]
    assert "cat" in client.get("/").text


def test_marks_get_a_tkr_coordinate_when_saved(qa_planted):
    payload = _payload(qa_planted, FIRST)
    payload["marks"] = [{"region": "sinus", "kind": "pial_out", "grid": [32.0, 32.0, 40.0],
                         "surface": "lh.pial", "finding": None, "note": ""}]
    review = _client(qa_planted, "cat").put(f"/api/review/{FIRST}", json=payload).json()["review"]
    mark = review["marks"][0]
    assert len(mark["tkr"]) == 3 and isinstance(mark["vertex"], int)


def test_next_goes_to_the_most_suspicious_unsubmitted_subject(qa_reviewed):
    assert _client(qa_reviewed, "cat").get("/next").headers["location"] == f"/subjects/{FIRST}/"
    ann = _client(qa_reviewed, "ann")
    assert ann.get("/next").headers["location"] == f"/subjects/{SECOND}/"
    assert ann.get(f"/next?after={SECOND}").headers["location"] == f"/subjects/{RECON}/"
    assert _client(qa_reviewed).get("/next").headers["location"] == "/"


def test_skip_moves_the_subject_to_the_end_of_the_queue(qa_planted):
    client = _client(qa_planted, "cat")
    payload = {**_payload(qa_planted, FIRST), "skipped": True}
    assert client.put(f"/api/review/{FIRST}", json=payload).json()["review"]["skipped"] is True
    assert client.get(f"/next?after={FIRST}").headers["location"] == f"/subjects/{SECOND}/"
    assert client.get("/next").headers["location"] == f"/subjects/{SECOND}/"
    for key in (SECOND, RECON):
        client.post(f"/api/review/{key}/submit", json=_payload(qa_planted, key))
    assert client.get("/next").headers["location"] == f"/subjects/{FIRST}/"
    client.put(f"/api/review/{FIRST}", json=_payload(qa_planted, FIRST))  # rating un-skips
    assert client.get(f"/api/review/{FIRST}").json()["review"]["skipped"] is False
    client.post(f"/api/review/{FIRST}/submit", json=_payload(qa_planted, FIRST))
    assert client.get("/next").headers["location"] == "/"


def test_subject_page_is_rendered_for_the_named_reviewer(qa_reviewed):
    assert 'type="radio"' in _client(qa_reviewed, "cat").get(f"/subjects/{FIRST}/").text
    assert 'type="radio"' in _client(qa_reviewed, "cat").get(f"/subjects/{FIRST}/index.html").text
    unnamed = _client(qa_reviewed).get(f"/subjects/{FIRST}/").text
    assert 'type="radio"' not in unnamed and 'action="/reviewer"' in unnamed
    assert "bob-note-quux" not in _client(qa_reviewed, "cat").get(f"/subjects/{FIRST}/").text
    assert "bob-note-quux" in _client(qa_reviewed, "ann").get(f"/subjects/{FIRST}/").text


def test_subject_address_without_a_slash_redirects(qa_planted):
    response = _client(qa_planted).get(f"/subjects/{FIRST}")
    assert response.status_code in (301, 307, 308)
    assert response.headers["location"].endswith(f"/subjects/{FIRST}/")


def test_unknown_subject_is_404(qa_planted):
    client = _client(qa_planted, "cat")
    assert client.get("/subjects/nobody__sub-99/").status_code == 404
    assert client.get("/api/review/nobody__sub-99").status_code == 404
    assert client.put("/api/review/nobody__sub-99", json={}).status_code == 404
    assert client.get("/api/review/..%2f..%2fx").status_code == 404


def test_subject_without_a_run_has_no_review(qa):
    client = _client(qa, "cat")
    assert client.get("/api/review/fastsurfer__sub-02").status_code == 404
    assert "surf/lh.white" in client.get("/subjects/fastsurfer__sub-02/").text


def test_blind_findings_files_are_not_served_before_submitting(qa_reviewed):
    run = current_run_dir(qa_reviewed, FIRST).name
    for name in ("findings.json", "findings_voxels.bin"):
        path = f"/subjects/{FIRST}/runs/{run}/{name}"
        assert _client(qa_reviewed, "cat", blind=True).get(path).status_code == 404
        assert _client(qa_reviewed, blind=True).get(path).status_code == 404
        assert _client(qa_reviewed, "ann", blind=True).get(path).status_code == 200
        assert _client(qa_reviewed, "cat").get(path).status_code == 200
    assert _client(qa_reviewed, "cat", blind=True).get(
        f"/subjects/{FIRST}/runs/{run}/meta.json").status_code == 200


def test_blind_pages_need_a_name(qa_reviewed):
    client = _client(qa_reviewed, blind=True)
    assert "Give your name" in client.get("/").text
    assert "Give your name" in client.get(f"/subjects/{FIRST}/").text
    assert "Suspicion score" not in _client(qa_reviewed, "cat", blind=True).get(f"/subjects/{FIRST}/").text


def test_oversized_body_is_refused(qa_planted):
    payload = {**_payload(qa_planted, FIRST), "notes": "x" * 1_100_000}
    response = _client(qa_planted, "cat").put(f"/api/review/{FIRST}", json=payload)
    assert response.status_code == 413
    assert not (qa_planted / "ratings").exists()
