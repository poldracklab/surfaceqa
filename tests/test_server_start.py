import pytest
from fastapi.testclient import TestClient

from surfaceqa import recent
from surfaceqa.server import create_app
from surfaceqa.server_start import StartMode

TOKEN = "tok-9f3a-launch"
BASE = "http://127.0.0.1:8765"
GETS = ["/", "/start", "/start/folders", "/start/plan", "/start/progress", "/start/status"]
POSTS = ["/start/open", "/start/forget", "/start/build", "/start/cancel", "/start/check"]


def _app(qa_dir=None):
    return create_app(qa_dir, start=StartMode(TOKEN))


def _visitor(app) -> TestClient:
    """A browser that has not been given the launch address."""
    return TestClient(app, base_url=BASE, follow_redirects=False)


def _client(qa_dir=None) -> TestClient:
    """A browser that opened the printed address."""
    client = _visitor(_app(qa_dir))
    assert client.get(f"/?token={TOKEN}").status_code == 303
    return client


def _form(**fields):
    return {"data": fields, "headers": {"origin": BASE}}


# ---- the guard -------------------------------------------------------------------------------

@pytest.mark.parametrize("path", GETS)
def test_get_is_refused_without_the_launch_token(path):
    response = _visitor(_app()).get(path)
    assert response.status_code == 403 and "token" in response.text.lower()
    assert TOKEN not in response.text


@pytest.mark.parametrize("path", POSTS)
def test_post_is_refused_without_the_launch_token(path, tmp_path):
    assert _visitor(_app()).post(path, **_form(path=str(tmp_path))).status_code == 403


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8765", "127.0.0.1.evil.example",
                                  "localhost.evil.example:8765", "[::1]:8765", "10.0.0.5:8765", ""])
@pytest.mark.parametrize("path", GETS + ["/static/app.css"])
def test_a_foreign_host_name_is_refused_everywhere(host, path):
    response = _client().get(path, headers={"host": host})
    assert response.status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "localhost:9000", "127.0.0.1", "LOCALHOST:1"])
def test_loopback_names_are_accepted_on_any_port(host):
    client = _visitor(_app())
    assert client.get(f"/start?token={TOKEN}", headers={"host": host}).status_code == 303
    assert client.get("/start", headers={"host": host}).status_code == 200


def test_two_copies_on_different_ports_do_not_share_the_token_cookie():
    first, second = _visitor(_app()), None
    first.get(f"/start?token={TOKEN}")
    names = [cookie.name for cookie in first.cookies.jar]
    first.get(f"/start?token={TOKEN}", headers={"host": "127.0.0.1:8766"})
    assert len({cookie.name for cookie in first.cookies.jar}) == 2 and names[0].endswith("8765")


@pytest.mark.parametrize("origin", ["http://evil.example", "http://evil.example:8765", "null",
                                    "http://localhost.evil.example:8765"])
@pytest.mark.parametrize("path", POSTS + ["/reviewer", "/report"])
def test_a_post_from_another_site_is_refused(origin, path, tmp_path, qa):
    client = _client(qa)
    response = client.post(path, data={"path": str(tmp_path), "name": "ann"}, headers={"origin": origin})
    assert response.status_code == 403
    assert "ann" not in client.get("/").text


def test_the_token_in_the_address_sets_a_cookie_and_is_dropped_from_the_address():
    response = _visitor(_app()).get(f"/start?token={TOKEN}")
    assert response.status_code == 303 and response.headers["location"] == "/start"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


@pytest.mark.parametrize("token", ["wrong", "", TOKEN + "x", TOKEN[:-1]])
def test_a_wrong_token_is_refused(token):
    client = _visitor(_app())
    assert client.get(f"/start?token={token}").status_code == 403
    assert client.get("/start").status_code == 403


def test_the_refusal_page_has_a_form_for_the_token_and_its_style():
    client = _visitor(_app())
    page = client.get("/start").text
    assert 'name="token"' in page
    assert client.get("/static/app.css").status_code == 200


def test_pages_never_contain_the_token(qa):
    client = _client(qa)
    assert TOKEN not in client.get("/start").text and TOKEN not in client.get("/").text


# ---- serve is unchanged ----------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/start", "/start/folders", "/start/plan", "/start/progress", "/start/status"])
def test_serve_has_no_start_pages(qa, path):
    assert TestClient(create_app(qa)).get(path).status_code == 404


@pytest.mark.parametrize("path", POSTS + ["/start/cancel", "/start/check"])
def test_serve_has_no_start_actions(qa, path, tmp_path):
    client = TestClient(create_app(qa))
    assert client.post(path, data={"path": str(tmp_path), "source": str(tmp_path)}).status_code in (404, 405)
    assert "/start" not in client.get("/").text


def test_serve_needs_no_token_and_accepts_any_host(qa):
    assert TestClient(create_app(qa), base_url="http://reviewbox.lab:8765").get("/").status_code == 200


# ---- no project open -------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/index.html", "/subjects/fastsurfer__sub-01/", "/report/index.html",
                                  "/next", "/subjects/fastsurfer__sub-01/review"])
def test_without_a_project_every_project_page_leads_to_the_start_page(path):
    response = _client().get(path)
    assert response.status_code == 303 and response.headers["location"] == "/start"


def test_the_start_page_with_nothing_remembered():
    page = _client().get("/start").text
    assert "No project has been opened on this machine yet" in page
    assert 'action="/start/build"' in page and 'action="/start/open"' in page


# ---- the folder browser ----------------------------------------------------------------------

def test_folders_without_a_path_gives_the_starting_places():
    places = _client().get("/start/folders").json()["places"]
    assert places[0]["name"] == "Home"


def test_folders_lists_sub_folders_with_subject_counts_and_no_file_names(synth_sources, tmp_path):
    (tmp_path / "secret-notes.txt").write_text("x")
    listing = _client().get("/start/folders", params={"path": str(tmp_path)}).json()
    assert [(f["name"], f["n_subjects"]) for f in listing["folders"]][:2] == [("fastsurfer", 1),
                                                                              ("freesurfer-8.2.0", 1)]
    assert "secret-notes" not in str(listing) and listing["error"] is None


def test_folders_of_a_missing_path_is_an_error_message_not_a_failure(tmp_path):
    response = _client().get("/start/folders", params={"path": str(tmp_path / "absent")})
    assert response.status_code == 200 and response.json()["error"]


# ---- planning a build ------------------------------------------------------------------------

def test_plan_gives_the_default_output_and_the_subject_count(synth_sources):
    plan = _client().get("/start/plan", params={"source": [str(s) for s in synth_sources], "out": ""}).json()
    assert plan == {"out": str(synth_sources[0].parent / "surfaceqa"), "error": None, "adds": False,
                    "n_subjects": 2}


def test_plan_reports_a_refusal(synth_sources):
    plan = _client().get("/start/plan", params={"source": str(synth_sources[0]),
                                                "out": str(synth_sources[0] / "qa")}).json()
    assert "inside" in plan["error"]


def test_build_with_a_refused_request_starts_nothing(synth_sources, tmp_path):
    client = _client()
    response = client.post("/start/build", **_form(source=str(synth_sources[0]), out=str(synth_sources[0] / "qa")))
    assert response.status_code == 400 and "inside" in response.text
    assert not (synth_sources[0] / "qa").exists()
    assert client.app.state.start.job is None
    response = client.post("/start/build", **_form(source="", out=""))
    assert response.status_code == 400 and "Choose a folder" in response.text


def test_build_is_refused_while_another_program_builds_the_same_directory(synth_sources, tmp_path):
    from surfaceqa.lock import build_lock

    client = _client()
    with build_lock(tmp_path / "qa"):
        response = client.post("/start/build", **_form(source=str(synth_sources[0]), out=str(tmp_path / "qa")))
    assert response.status_code == 409 and "already" in response.text
    assert client.app.state.start.job is None


# ---- opening a project -----------------------------------------------------------------------

def test_open_a_qa_directory(qa):
    client = _client()
    response = client.post("/start/open", **_form(path=str(qa)))
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert "sub-01" in client.get("/").text
    page = client.get("/start").text
    assert str(qa.resolve()) in page and "3 subjects" in page and "fastsurfer" in page
    assert [p["path"] for p in recent.projects()] == [str(qa.resolve())]


def test_open_something_that_is_not_a_qa_directory(tmp_path):
    client = _client()
    response = client.post("/start/open", **_form(path=str(tmp_path)))
    assert response.status_code == 400 and "not a QA directory" in response.text
    assert client.get("/").status_code == 303 and recent.projects() == []
    assert client.post("/start/open", **_form(path="")).status_code == 400


def test_open_writes_the_pages_again_when_they_are_missing(qa):
    (qa / "index.html").unlink()
    _client().post("/start/open", **_form(path=str(qa)))
    assert (qa / "index.html").is_file()


def test_a_second_project_replaces_the_first(qa, qa_planted_elsewhere):
    client = _client()
    client.post("/start/open", **_form(path=str(qa)))
    client.post("/start/open", **_form(path=str(qa_planted_elsewhere)))
    assert "only-here" in client.get("/").text and "sub-02" not in client.get("/").text


@pytest.fixture
def qa_planted_elsewhere(tmp_path_factory):
    from surfaceqa.cli import main
    from tests.synth import write_subject

    root = tmp_path_factory.mktemp("elsewhere")
    write_subject(root / "study", name="only-here")
    main(["build", str(root / "study"), "--out", str(root / "qa")])
    return root / "qa"


def test_forget_removes_a_project_from_the_list(qa, tmp_path):
    client = _client()
    recent.remember(tmp_path / "gone")
    page = client.get("/start").text
    assert str(tmp_path / "gone") in page and "missing" in page
    assert client.post("/start/forget", **_form(path=str(tmp_path / "gone"))).status_code == 303
    assert str(tmp_path / "gone") not in client.get("/start").text


def test_folder_names_are_escaped(tmp_path):
    odd = tmp_path / "<b>bold</b>" / "qa"
    (odd / "subjects").mkdir(parents=True)
    client = _client()
    client.post("/start/open", **_form(path=str(odd)))
    page = client.get("/start").text
    assert "&lt;b&gt;bold" in page and "<b>bold" not in page
    refused = client.post("/start/open", **_form(path=str(tmp_path / "<i>x</i>"))).text
    assert "<i>x" not in refused


def test_reviewing_works_in_start_mode(qa):
    client = _client(qa)
    assert client.post("/reviewer", **_form(name="ann")).status_code == 303
    assert "ann" in client.get("/").text


# ---- building from the page ------------------------------------------------------------------

import time

from surfaceqa.layout import current_run_dir


def _status(client, until=lambda s: s["state"] != "running", seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status = client.get("/start/status").json()
        if until(status):
            return status
        time.sleep(0.05)
    raise AssertionError(f"timed out: {status}")


def _build(client, sources, out):
    fields = [("source", str(s)) for s in sources] + [("out", str(out))]
    from urllib.parse import urlencode
    return client.post("/start/build", content=urlencode(fields),
                       headers={"origin": BASE, "content-type": "application/x-www-form-urlencoded"})


def _started(client):
    return _status(client, lambda s: s["done"] >= 1 or s["state"] != "running")


def test_without_a_build_there_is_no_progress_to_show():
    client = _client()
    assert client.get("/start/status").json() == {"state": "none"}
    response = client.get("/start/progress")
    assert response.status_code == 303 and response.headers["location"] == "/start"
    assert client.post("/start/cancel", **_form()).status_code == 303


def test_build_from_the_page_to_the_project(synth_sources, tmp_path):
    client = _client()
    response = _build(client, synth_sources, tmp_path / "qa")
    assert response.status_code == 303 and response.headers["location"] == "/start/progress"
    page = client.get("/start/progress")
    assert page.status_code == 200 and "/static/progress.js" in page.text and str(tmp_path / "qa") in page.text
    status = _status(client)
    assert status["state"] == "done" and status["total"] == 2 and status["problems"] == []
    assert status["open"] is True and status["out"] == str(tmp_path / "qa")
    index = client.get("/").text
    assert "sub-01" in index and "Check for new or changed subjects" in index and 'href="/start"' in index
    assert [p["path"] for p in recent.projects()] == [str(tmp_path / "qa")]


def test_a_subject_that_fails_is_named_with_one_line(synth_sources, tmp_path):
    (synth_sources[1] / "sub-01" / "surf" / "lh.white").write_bytes(b"junk")
    client = _client()
    _build(client, synth_sources, tmp_path / "qa")
    (problem,) = _status(client)["problems"]
    assert problem["key"] == "freesurfer-8.2.0__sub-01" and "\n" not in problem["reason"]


def test_a_second_build_is_refused_while_one_runs(many, synth_sources, tmp_path):
    client = _client()
    _build(client, [many], tmp_path / "qa")
    job = client.app.state.start.job
    response = _build(client, synth_sources, tmp_path / "other")
    assert response.status_code == 409 and "already running" in response.text
    assert client.app.state.start.job is job and not (tmp_path / "other").exists()
    client.post("/start/cancel", **_form())


def test_cancel_then_build_again(many, tmp_path):
    client = _client()
    _build(client, [many], tmp_path / "qa")
    assert _started(client)["state"] == "running"
    response = client.post("/start/cancel", **_form())
    assert response.status_code == 303 and response.headers["location"] == "/start/progress"
    assert client.get("/start/status").json()["state"] == "cancelled"
    assert "Cancelled" in client.get("/start/progress").text or "cancelled" in client.get("/start/progress").text
    _build(client, [many], tmp_path / "qa")
    status = _status(client)
    assert status["state"] == "done" and status["total"] == 12


def test_a_cancelled_build_with_finished_subjects_is_remembered(many, tmp_path):
    client = _client()
    _build(client, [many], tmp_path / "qa")
    _started(client)
    client.post("/start/cancel", **_form())
    client.get("/start/status")
    assert [p["path"] for p in recent.projects()] == [str(tmp_path / "qa")]


def test_a_build_of_other_data_does_not_take_the_open_project_away(qa, tmp_path_factory):
    from tests.synth import write_subject

    other = tmp_path_factory.mktemp("other")
    write_subject(other / "study", name="only-here")
    client = _client(qa)
    _build(client, [other / "study"], other / "qa")
    status = _status(client)
    assert status["state"] == "done" and status["open"] is False
    assert "only-here" not in client.get("/").text and "sub-02" in client.get("/").text
    assert str(other / "qa") in [p["path"] for p in recent.projects()]
    assert "A build of this project is running" not in client.get("/").text


def test_check_builds_the_recorded_sources_again(synth_sources, tmp_path):
    import nibabel as nib

    client = _client()
    _build(client, synth_sources, tmp_path / "qa")
    _status(client)
    before = current_run_dir(tmp_path / "qa", "fastsurfer__sub-01").name
    surface = synth_sources[0] / "sub-01" / "surf" / "lh.pial"
    verts, faces, info = nib.freesurfer.read_geometry(surface, read_metadata=True)
    nib.freesurfer.write_geometry(surface, verts * 0.9, faces, volume_info=info)
    from tests.synth import write_subject
    write_subject(synth_sources[0], name="sub-new")
    response = client.post("/start/check", **_form())
    assert response.status_code == 303 and response.headers["location"] == "/start/progress"
    status = _status(client)
    assert status["state"] == "done" and status["total"] == 3 and status["open"] is True
    assert current_run_dir(tmp_path / "qa", "fastsurfer__sub-01").name != before
    assert "sub-new" in client.get("/").text


def test_check_is_not_offered_for_a_project_without_recorded_sources(qa):
    client = _client(qa)
    index = client.get("/").text
    assert "Check for new or changed subjects" not in index and 'href="/start"' in index
    response = client.post("/start/check", **_form())
    assert response.status_code == 400 and "does not record" in response.text
    assert client.app.state.start.job is None


def test_check_says_when_a_source_folder_is_gone(synth_sources, tmp_path):
    import shutil

    client = _client()
    _build(client, synth_sources, tmp_path / "qa")
    _status(client)
    shutil.rmtree(synth_sources[1])
    response = client.post("/start/check", **_form())
    assert response.status_code == 400 and "Not a folder" in response.text


def test_the_project_can_be_reviewed_while_it_is_being_built_again(many, tmp_path):
    client = _client()
    _build(client, [many], tmp_path / "qa")
    _status(client)
    client.post("/start/check", **_form())
    index = client.get("/").text
    if client.get("/start/status").json()["state"] == "running":
        assert "A build of this project is running" in index and "/start/progress" in index
        assert "Check for new or changed subjects" not in index
    assert client.post("/reviewer", **_form(name="ann")).status_code == 303
    assert client.get("/subjects/study__sub-00/").status_code == 200
    _status(client)
    assert "A build of this project is running" not in client.get("/").text
