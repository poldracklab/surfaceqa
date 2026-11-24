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


class ReviewClient(TestClient):
    """Sends reviews the way the page does: with the reviewer the page was opened as and
    the time of the save it last saw, unless the test gives them itself."""

    def _as_the_page_would(self, url: str, body):
        if not isinstance(body, dict) or "reviewer" in body:
            return body
        seen = self.get(url.removesuffix("/submit"))
        if seen.status_code != 200:
            return body
        review = seen.json()["review"]
        return {"reviewer": review["reviewer"], "saved": review["saved"], **body}

    def put(self, url, json=None, **kwargs):
        return super().put(url, json=self._as_the_page_would(url, json), **kwargs)

    def post(self, url, json=None, **kwargs):
        return super().post(url, json=self._as_the_page_would(url, json), **kwargs)


def _client(qa, reviewer=None, blind=False) -> TestClient:
    client = ReviewClient(create_app(qa, blind=blind), follow_redirects=False)
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


def test_a_name_is_stored_in_lower_case(qa_planted):
    # on a case-insensitive disk Ann and ann would otherwise share one file
    response = _client(qa_planted).post("/reviewer", data={"name": "Ann", "next": "/"})
    assert "surfaceqa_reviewer=ann" in response.headers["set-cookie"]
    assert _client(qa_planted, "Ann").get(f"/api/review/{FIRST}").status_code == 401


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


# ---- found by the review of the branch -------------------------------------------------------

LEAKS = ["/ratings/{key}/{run}/ann.json", "/ratings/{key}/{run}/bob.json", "/final/{key}.json",
         "/export/ratings.tsv", "/export/marks.tsv", "/ratings/", "/final/", "/current.json",
         "//subjects/{key}/index.html", "/subjects/{key}//index.html",
         "/subjects/{key}/current.json"]
# the test client rewrites these to an ordinary page address before sending, so they are
# answered by the page for that reviewer; what matters is that nothing of the others is in it
REWRITTEN = ["/subjects/{key}/./index.html", "//index.html"]


@pytest.mark.parametrize("path", REWRITTEN)
@pytest.mark.parametrize("blind", [False, True])
def test_addresses_the_client_rewrites_show_only_the_reviewers_own_page(qa_reviewed, path, blind):
    from surfaceqa.finalize import finalize
    from surfaceqa.site import write_site

    finalize(qa_reviewed)
    write_site(qa_reviewed)
    text = _client(qa_reviewed, "cat", blind=blind).get(path.format(key=FIRST)).text
    assert "bob-note-quux" not in text and "ann-note-xyzzy" not in text
    assert '<td class="grade">C+</td>' not in text


@pytest.mark.parametrize("path", LEAKS)
@pytest.mark.parametrize("blind", [False, True])
def test_reviews_finals_exports_and_static_pages_are_not_served_as_files(qa_reviewed, path, blind):
    from surfaceqa.export import export_tables
    from surfaceqa.finalize import finalize
    from surfaceqa.site import write_site

    finalize(qa_reviewed)
    export_tables(qa_reviewed)
    write_site(qa_reviewed)
    url = path.format(key=FIRST, run=current_run_dir(qa_reviewed, FIRST).name)
    for reviewer in ("cat", None):
        response = _client(qa_reviewed, reviewer, blind=blind).get(url)
        assert response.status_code in (400, 404), url
        assert "bob-note-quux" not in response.text and "ann-note-xyzzy" not in response.text


@pytest.mark.parametrize("path", ["/index.html/", "/subjects/{key}/index.html/"])
def test_a_trailing_slash_never_reaches_the_pages_written_to_disk(qa_reviewed, path):
    from surfaceqa.site import write_site

    write_site(qa_reviewed)
    client = TestClient(create_app(qa_reviewed), follow_redirects=True)
    client.cookies.set("surfaceqa_reviewer", "cat")
    assert "bob-note-quux" not in client.get(path.format(key=FIRST)).text


VARIANTS = ["{base}/{name}/", "{base}//{name}", "/{base}/{name}", "{base}/./{name}",
            "{base}/x/../{name}", "{base}/{upper}", "{base}/slices/../{name}",
            "{base}/%2e/{name}", "{base}/{name}%00"]


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", ["findings.json", "findings_voxels.bin"])
def test_blind_findings_are_not_served_under_any_spelling_of_the_address(qa_reviewed, variant, name):
    run = current_run_dir(qa_reviewed, FIRST).name
    url = variant.format(base=f"/subjects/{FIRST}/runs/{run}", name=name, upper=name.upper())
    for reviewer in ("cat", None):
        response = TestClient(create_app(qa_reviewed, blind=True), follow_redirects=True)
        if reviewer:
            response.cookies.set("surfaceqa_reviewer", reviewer)
        assert response.get(url).status_code in (400, 404), url


def test_only_the_viewer_files_of_a_run_are_served(qa_reviewed):
    run = current_run_dir(qa_reviewed, FIRST).name
    base = f"/subjects/{FIRST}/runs/{run}"
    client = _client(qa_reviewed, "cat")
    for name in ("meta.json", "findings.json", "findings_voxels.bin", "contours_axial.json",
                 "contours_sagittal.bin", "slices/axial/000.jpg"):
        assert client.get(f"{base}/{name}").status_code == 200, name
    (qa_reviewed / "subjects" / FIRST / "runs" / run / "notes.txt").write_text("private")
    for name in ("notes.txt", "slices/", "slices/axial/", "META.JSON", "slices/axial/000.JPG"):
        assert client.get(f"{base}/{name}").status_code == 404, name
    assert client.get(f"/subjects/{FIRST}/runs/zzzzzzzzzzzz/meta.json").status_code == 404
    assert client.get("/static/app.css").status_code == 200


def test_the_error_of_a_failed_build_can_be_read(qa):
    (qa / "subjects" / "fastsurfer__sub-02" / "error.txt").write_text("Traceback: boom")
    assert "boom" in _client(qa).get("/subjects/fastsurfer__sub-02/error.txt").text
    assert _client(qa).get("/subjects/fastsurfer__sub-01/error.txt").status_code == 404


def test_a_page_opened_under_another_name_cannot_save(qa_reviewed):
    """Shared machine: a page opened as ann, then the name changed to bob in another tab."""
    before = load_review(qa_reviewed, FIRST, current_run_dir(qa_reviewed, FIRST).name, "bob")
    payload = {**_payload(qa_reviewed, FIRST, sinus="major"), "reviewer": "ann", "saved": None}
    client = _client(qa_reviewed, "bob")
    for response in (client.put(f"/api/review/{FIRST}", json=payload),
                     client.post(f"/api/review/{FIRST}/submit", json=payload)):
        assert response.status_code == 409 and "ann" in response.json()["detail"]
    assert load_review(qa_reviewed, FIRST, before["run"], "bob") == before


def test_a_payload_without_the_reviewer_is_refused(qa_planted):
    response = TestClient(create_app(qa_planted))
    response.cookies.set("surfaceqa_reviewer", "cat")
    assert response.put(f"/api/review/{FIRST}", json=_payload(qa_planted, FIRST)).status_code == 409
    assert not (qa_planted / "ratings").exists()


def test_a_stale_window_cannot_overwrite_a_newer_save(qa_planted):
    client = _client(qa_planted, "cat")
    stale = {**_payload(qa_planted, FIRST, sinus="minor"), "reviewer": "cat", "saved": None}
    assert client.put(f"/api/review/{FIRST}", json=stale).status_code == 200
    client.put(f"/api/review/{FIRST}", json=_payload(qa_planted, FIRST, sinus="major",
               marks=[{"region": "sinus", "kind": "pial_out", "grid": [32.0, 32.0, 40.0],
                       "surface": None, "finding": None, "note": ""}]))
    response = client.put(f"/api/review/{FIRST}", json=stale)  # the first window, unaware
    assert response.status_code == 409 and "another window" in response.json()["detail"]
    assert client.get(f"/api/review/{FIRST}").json()["review"]["items"]["sinus"]["rating"] == "major"


def test_each_response_carries_the_stamp_for_the_next_save(qa_planted):
    client = TestClient(create_app(qa_planted))
    client.cookies.set("surfaceqa_reviewer", "cat")
    payload = {**_payload(qa_planted, FIRST), "reviewer": "cat", "saved": None}
    first = client.put(f"/api/review/{FIRST}", json=payload).json()["review"]
    second = client.put(f"/api/review/{FIRST}", json={**payload, "saved": first["saved"]})
    assert second.status_code == 200
    third = client.post(f"/api/review/{FIRST}/submit",
                        json={**payload, "saved": second.json()["review"]["saved"]})
    assert third.status_code == 200 and third.json()["review"]["submitted"]


@pytest.mark.parametrize("change", ["grade", "item", "mark"])
def test_a_submitted_review_cannot_be_saved_incomplete(qa_reviewed, change):
    run = current_run_dir(qa_reviewed, FIRST).name
    before = load_review(qa_reviewed, FIRST, run, "ann")
    payload = {k: before[k] for k in ("run", "items", "marks", "grade", "notes", "unratable")}
    if change == "grade":
        payload["grade"] = None
    elif change == "item":
        payload["items"] = {**payload["items"], "t1": {"rating": None, "note": ""}}
    else:
        payload["marks"] = []
    response = _client(qa_reviewed, "ann").put(f"/api/review/{FIRST}", json=payload)
    assert response.status_code == 422 and "submitted" in str(response.json()["detail"])
    assert load_review(qa_reviewed, FIRST, run, "ann") == before


def test_a_submitted_review_can_still_be_revised_when_complete(qa_reviewed):
    run = current_run_dir(qa_reviewed, FIRST).name
    before = load_review(qa_reviewed, FIRST, run, "ann")
    payload = {k: before[k] for k in ("run", "items", "marks", "grade", "notes", "unratable")}
    response = _client(qa_reviewed, "ann").put(f"/api/review/{FIRST}", json={**payload, "grade": "D"})
    review = response.json()["review"]
    assert response.status_code == 200 and review["grade"] == "D"
    assert review["submitted"] == before["submitted"] and review["revised"] is True


def test_a_submit_is_one_write_and_a_refused_submit_leaves_a_draft(qa_planted, monkeypatch):
    from surfaceqa import review_store

    writes = []
    real = review_store._write
    monkeypatch.setattr(review_store, "_write", lambda path, review: writes.append(path) or real(path, review))
    client = _client(qa_planted, "cat")
    assert client.post(f"/api/review/{FIRST}/submit", json=_payload(qa_planted, FIRST)).status_code == 200
    assert len(writes) == 1


def test_a_mark_keeps_its_vertex_when_the_source_becomes_unreadable(qa_planted):
    import shutil

    client = _client(qa_planted, "cat")
    payload = _payload(qa_planted, FIRST)
    payload["marks"] = [{"region": "sinus", "kind": "pial_out", "grid": [32.0, 32.0, 40.0],
                         "surface": "lh.pial", "finding": None, "note": ""}]
    first = client.put(f"/api/review/{FIRST}", json=payload).json()["review"]["marks"][0]
    assert isinstance(first["vertex"], int)
    shutil.rmtree(qa_planted.parent / "fastsurfer" / "sub-01")
    payload["notes"] = "an unrelated edit"
    again = client.put(f"/api/review/{FIRST}", json=payload).json()["review"]["marks"][0]
    assert again["vertex"] == first["vertex"] and again["tkr"] == first["tkr"]
    payload["marks"][0]["grid"] = [30.0, 32.0, 40.0]  # the mark was moved: the old vertex is wrong
    moved = client.put(f"/api/review/{FIRST}", json=payload).json()["review"]["marks"][0]
    assert moved["vertex"] is None and moved["tkr"] != first["tkr"]


def test_a_malformed_content_length_is_refused(qa_planted):
    response = _client(qa_planted, "cat").put(
        f"/api/review/{FIRST}", content=b"{}", headers={"content-length": "abc"})
    assert response.status_code in (400, 411, 413, 422)


def test_overlapping_saves_and_a_submit_leave_a_submitted_review(qa_planted):
    """Saves that overlap a submit must not un-submit it, and none may fail on a file clash."""
    from concurrent.futures import ThreadPoolExecutor

    from surfaceqa.review_store import save_review, submit_review

    run = current_run_dir(qa_planted, FIRST).name
    review = make_review("cat", FIRST, run, submitted=False)
    for _ in range(20):
        path = qa_planted / "ratings" / FIRST / run / "cat.json"
        path.unlink(missing_ok=True)
        with ThreadPoolExecutor(8) as pool:
            jobs = [pool.submit(save_review, qa_planted, review) for _ in range(6)]
            jobs.append(pool.submit(submit_review, qa_planted, review))
            jobs += [pool.submit(save_review, qa_planted, review) for _ in range(6)]
            results = [job.result() for job in jobs]  # raises if any write failed
        assert len(results) == 13
        assert load_review(qa_planted, FIRST, run, "cat")["submitted"]
        assert [p.name for p in path.parent.iterdir()] == ["cat.json"]


def test_a_refused_submit_reports_the_stamp_of_the_draft_it_saved(qa_planted):
    """Otherwise the page's next save would look like one from a stale window."""
    client = TestClient(create_app(qa_planted))
    client.cookies.set("surfaceqa_reviewer", "cat")
    payload = {**_payload(qa_planted, FIRST), "grade": None, "reviewer": "cat", "saved": None}
    refused = client.post(f"/api/review/{FIRST}/submit", json=payload)
    assert refused.status_code == 422 and refused.json()["saved"]
    again = client.put(f"/api/review/{FIRST}", json={**payload, "saved": refused.json()["saved"]})
    assert again.status_code == 200


def test_scripts_come_from_the_installed_tool_not_from_the_copy_in_the_qa_directory(qa_planted):
    """A QA directory built by an older version must not pair old scripts with a new server."""
    from importlib import resources

    (qa_planted / "static" / "review.js").write_text("// from an older version")
    served = _client(qa_planted).get("/static/review.js").text
    assert served == (resources.files("surfaceqa") / "web" / "static" / "review.js").read_text()


def test_scripts_are_checked_with_the_server_before_a_cached_copy_is_used(qa_planted):
    """After an upgrade a browser must not go on running the scripts it cached."""
    client = _client(qa_planted)
    for name in ("review.js", "logic.js", "viewer.js", "app.css"):
        response = client.get(f"/static/{name}")
        assert response.headers["cache-control"] == "no-cache" and response.headers["etag"]
    again = client.get("/static/logic.js", headers={"if-none-match": response.headers["etag"]})
    assert again.status_code in (200, 304)


# ---- fix guidance ----------------------------------------------------------------------------

from surfaceqa.finalize import finalize
from surfaceqa.review_store import submit_review
from tests.reviewing import MARK

GUIDANCE = f"/subjects/{RECON}/guidance"


def _major_body(qa, reviewer, note) -> dict:
    run = current_run_dir(qa, RECON).name
    review = make_review(reviewer, RECON, run, sinus="major", marks=[{**MARK, "note": note}])
    return {key: review[key] for key in ("run", "items", "marks", "grade", "notes", "unratable")}


def test_guidance_follows_the_saved_review(qa_reviewed):
    dan = _client(qa_reviewed, "dan")
    assert "freeview -v" not in dan.get(GUIDANCE).text
    assert dan.put(f"/api/review/{RECON}", json=_major_body(qa_reviewed, "dan", "dan-note")).status_code == 200
    fragment = dan.get(GUIDANCE)
    assert fragment.status_code == 200 and fragment.headers["content-type"].startswith("text/html")
    assert "freeview -v" in fragment.text and "-autorecon-pial" in fragment.text
    assert "dan-note" in fragment.text and "<html" not in fragment.text


def test_guidance_of_one_reviewer_is_not_given_to_another(qa_reviewed):
    _client(qa_reviewed, "dan").put(f"/api/review/{RECON}", json=_major_body(qa_reviewed, "dan", "dan-note"))
    for blind in (False, True):
        text = _client(qa_reviewed, "erin", blind=blind).get(GUIDANCE).text
        assert "freeview -v" not in text and "dan-note" not in text


def test_final_guidance_is_given_only_after_the_reviewers_own_submission(qa_reviewed):
    run = current_run_dir(qa_reviewed, RECON).name
    for name in ("dan", "erin"):
        submit_review(qa_reviewed, make_review(name, RECON, run, sinus="major",
                                               marks=[{**MARK, "note": f"{name}-note"}]))
    finalize(qa_reviewed)
    seen = _client(qa_reviewed, "erin").get(GUIDANCE).text
    assert "From the final labels" in seen and "dan-note" in seen and "erin-note" in seen
    for blind in (False, True):
        unseen = _client(qa_reviewed, "fay", blind=blind).get(GUIDANCE).text
        assert "freeview -v" not in unseen and "dan-note" not in unseen
    assert "dan-note" in _client(qa_reviewed).get(GUIDANCE).text  # the open overview


def test_guidance_is_not_served_blind_without_a_name(qa_reviewed):
    run = current_run_dir(qa_reviewed, RECON).name
    submit_review(qa_reviewed, make_review("dan", RECON, run, sinus="major", marks=[dict(MARK)]))
    finalize(qa_reviewed)
    assert _client(qa_reviewed, blind=True).get(GUIDANCE).status_code == 404


@pytest.mark.parametrize("path", ["/subjects/nope__nobody/guidance",
                                  f"/subjects/{RECON}/GUIDANCE", f"{GUIDANCE}.html"])
def test_guidance_address_variants_are_not_found(qa_reviewed, path):
    response = _client(qa_reviewed, "dan").get(path, follow_redirects=False)
    assert response.status_code == 404


def test_guidance_address_with_a_trailing_slash_only_redirects_to_the_gated_address(qa_reviewed):
    response = _client(qa_reviewed, blind=True).get(f"{GUIDANCE}/", follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"].endswith(GUIDANCE)
    assert "freeview" not in response.text


def test_subject_page_loads_the_guidance_script(qa_reviewed):
    assert "static/guidance.js" in _client(qa_reviewed, "dan").get(f"/subjects/{RECON}/").text
    assert _client(qa_reviewed).get("/static/guidance.js").status_code == 200


# ---- the viewer page of a run, for comparing ----------------------------------------------

def _viewer(key, run):
    return f"/subjects/{key}/runs/{run}/viewer.html"


def test_viewer_page_of_a_run_is_served(qa_reviewed):
    run = current_run_dir(qa_reviewed, FIRST).name
    response = _client(qa_reviewed).get(_viewer(FIRST, run))
    assert response.status_code == 200 and response.text.count("<canvas") == 3
    assert "data-findings" not in response.text
    for absent in ("ann-note-xyzzy", "bob-note-quux", "review-data", "checklist"):
        assert absent not in response.text


@pytest.mark.parametrize("key,run", [
    ("nope__nobody", "0123456789ab"), (FIRST, "0123456789ab"), (FIRST, "not-a-run"),
    (FIRST, ".."), (FIRST, "%2e%2e"),
])
def test_viewer_page_of_something_that_is_not_a_run_is_404(qa_reviewed, key, run):
    assert _client(qa_reviewed).get(_viewer(key, run)).status_code == 404


def test_viewer_page_of_another_subjects_run_is_404(qa_reviewed):
    theirs = current_run_dir(qa_reviewed, RECON)
    only_theirs = theirs.parent / "aaaaaaaaaaaa"  # synthetic subjects can share a run name
    only_theirs.mkdir()
    (only_theirs / "meta.json").write_text((theirs / "meta.json").read_text())
    assert _client(qa_reviewed).get(_viewer(RECON, only_theirs.name)).status_code == 200
    assert _client(qa_reviewed).get(_viewer(FIRST, only_theirs.name)).status_code == 404


def test_blind_viewer_page_needs_a_name_and_hides_findings_until_submitted(qa_reviewed):
    run = current_run_dir(qa_reviewed, FIRST).name
    assert _client(qa_reviewed, blind=True).get(_viewer(FIRST, run)).status_code == 404
    waiting = _client(qa_reviewed, "cat", blind=True).get(_viewer(FIRST, run))
    assert waiting.status_code == 200 and 'data-findings="off"' in waiting.text
    # also after submitting: the frame is shown beside another reconstruction of the same
    # person, which this reviewer may not have reviewed yet
    done = _client(qa_reviewed, "ann", blind=True).get(_viewer(FIRST, run))
    assert done.status_code == 200 and 'data-findings="off"' in done.text
    assert "data-findings" not in _client(qa_reviewed, "ann").get(_viewer(FIRST, run)).text


def test_blind_findings_of_an_earlier_run_wait_for_the_review_too(qa_reviewed, tmp_path):
    import nibabel as nib
    from surfaceqa.build import build_all
    from surfaceqa.discover import find_subjects
    from tests.synth import icosphere

    old = current_run_dir(qa_reviewed, FIRST).name
    vertices, faces = icosphere(9.0)
    nib.freesurfer.write_geometry(tmp_path / "fastsurfer" / "sub-01" / "surf" / "lh.pial", vertices, faces)
    build_all(find_subjects([tmp_path / "fastsurfer"]), qa_reviewed)
    assert current_run_dir(qa_reviewed, FIRST).name != old
    path = f"/subjects/{FIRST}/runs/{old}/findings.json"
    # nobody has reviewed the new run, so the findings of the old one are held back from everyone
    for reviewer in ("ann", "cat"):
        assert _client(qa_reviewed, reviewer, blind=True).get(path).status_code == 404
        page = _client(qa_reviewed, reviewer, blind=True).get(_viewer(FIRST, old))
        assert page.status_code == 200 and 'data-findings="off"' in page.text
    assert _client(qa_reviewed, "cat").get(path).status_code == 200
    subject_page = _client(qa_reviewed, "cat").get(f"/subjects/{FIRST}/").text
    assert f'<option value="runs/{old}/viewer.html">' in subject_page and "Earlier runs" in subject_page


# ---- the report, made again from the index page ---------------------------------------------

def test_index_offers_to_make_the_report_and_then_links_to_it(qa_reviewed):
    client = _client(qa_reviewed, "cat")
    before = client.get("/").text
    assert '<form method="post" action="/report"' in before and "Make report" in before
    assert 'href="/report/index.html"' not in before
    assert client.get("/report/index.html").status_code == 404
    made = client.post("/report")
    assert made.status_code == 303 and made.headers["location"] == "/report/index.html"
    page = client.get("/report/index.html")
    assert page.status_code == 200 and "Error distribution" in page.text
    assert page.headers["content-type"].startswith("text/html")
    after = client.get("/").text
    assert 'href="/report/index.html"' in after and "Update report" in after and "made 20" in after


def test_the_report_is_made_again_with_the_reviews_of_the_moment(qa_reviewed):
    client = _client(qa_reviewed, "cat")
    client.post("/report")
    assert "No submitted reviews yet." in client.get("/report/index.html").text
    run = current_run_dir(qa_reviewed, RECON).name
    submit_review(qa_reviewed, make_review("cat", RECON, run))
    assert "No submitted reviews yet." in client.get("/report/index.html").text  # not until asked
    client.post("/report")
    assert "No submitted reviews yet." not in client.get("/report/index.html").text


def test_the_report_tables_are_served_and_nothing_else_from_that_folder(qa_reviewed):
    client = _client(qa_reviewed)
    client.post("/report")
    for name in ("region_ratings.tsv", "problem_kinds.tsv", "indicator_agreement.tsv"):
        response = client.get(f"/report/{name}")
        assert response.status_code == 200 and response.text.startswith("source\t")
    (qa_reviewed / "report" / "other.html").write_text("x")
    for path in ("/report/other.html", "/report/../ratings/x.json", "/report/%2e%2e/final/x.json",
                 "/report/INDEX.HTML", "/report/index.html/", "/report/sub/index.html"):
        assert client.get(path).status_code in (404, 307), path
        assert "Error distribution" not in TestClient(create_app(qa_reviewed)).get(path).text or \
            path == "/report/index.html/", path


def test_subject_links_on_the_served_report_open_the_subject_pages(qa_reviewed):
    client = _client(qa_reviewed, "cat")
    client.post("/report")
    assert f'href="../subjects/{FIRST}/index.html"' in client.get("/report/index.html").text
    assert client.get(f"/subjects/{FIRST}/index.html").status_code == 200


@pytest.mark.parametrize("reviewer", [None, "cat", "ann"])
def test_a_blind_server_neither_makes_nor_serves_the_report(qa_reviewed, reviewer):
    from surfaceqa.report import write_report

    blind = _client(qa_reviewed, reviewer, blind=True)
    assert blind.post("/report").status_code == 404
    assert not (qa_reviewed / "report").exists()
    write_report(qa_reviewed)  # the coordinator made one with the command
    for path in ("/report/index.html", "/report/region_ratings.tsv", "/report/INDEX.HTML",
                 "/report/%69ndex.html", "/report//index.html"):
        response = TestClient(create_app(qa_reviewed, blind=True), follow_redirects=True)
        if reviewer:
            response.cookies.set("surfaceqa_reviewer", reviewer)
        got = response.get(path)
        assert "Error distribution" not in got.text and "source\t" not in got.text, path
    index = blind.get("/").text
    assert 'action="/report"' not in index and "/report/index.html" not in index
