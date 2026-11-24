import pytest
from fastapi.testclient import TestClient

from surfaceqa import recent
from surfaceqa.server import create_app
from surfaceqa.server_start import StartMode

TOKEN = "tok-9f3a-launch"
BASE = "http://127.0.0.1:8765"
GETS = ["/", "/start", "/start/folders", "/start/plan"]
POSTS = ["/start/open", "/start/forget", "/start/build"]


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
