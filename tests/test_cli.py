from surfaceqa.cli import main
from tests.synth import write_subject


def test_cli_build_writes_site(synth_sources, tmp_path, capsys):
    qa = tmp_path / "qa"
    assert main(["build", *map(str, synth_sources), "--out", str(qa)]) == 0
    assert (qa / "index.html").exists()
    assert "fastsurfer__sub-01  built" in capsys.readouterr().out


def test_cli_build_default_out_is_sibling(synth_sources):
    assert main(["build", str(synth_sources[0])]) == 0
    assert (synth_sources[0].parent / "surfaceqa" / "index.html").exists()


def test_cli_build_subject_filter(synth_sources, tmp_path):
    write_subject(synth_sources[0], name="sub-02")
    qa = tmp_path / "qa"
    main(["build", str(synth_sources[0]), "--out", str(qa), "--subjects", "sub-02"])
    assert [p.name for p in (qa / "subjects").iterdir()] == ["fastsurfer__sub-02"]


def test_cli_refuses_out_inside_source(synth_sources, capsys):
    assert main(["build", str(synth_sources[0]), "--out", str(synth_sources[0] / "qa")]) == 2
    assert not (synth_sources[0] / "qa").exists()


def test_cli_build_returns_1_when_a_subject_fails(synth_sources, tmp_path):
    (synth_sources[1] / "sub-01" / "surf" / "lh.white").write_bytes(b"junk")
    assert main(["build", *map(str, synth_sources), "--out", str(tmp_path / "qa")]) == 1


def test_cli_build_no_subjects_found(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    assert main(["build", str(tmp_path / "empty"), "--out", str(tmp_path / "qa")]) == 2
    assert "no subjects found" in capsys.readouterr().err.lower()


def test_cli_single_subject_source_defaults_out_beside_the_subjects_folder(synth_sources):
    subject = synth_sources[0] / "sub-01"
    assert main(["build", str(subject)]) == 0
    assert not (synth_sources[0] / "surfaceqa").exists()  # never inside the subjects folder
    assert (synth_sources[0].parent / "surfaceqa" / "index.html").exists()


def test_cli_refuses_out_inside_the_subjects_folder_of_a_single_subject(synth_sources, capsys):
    subject = synth_sources[0] / "sub-01"
    assert main(["build", str(subject), "--out", str(synth_sources[0] / "qa")]) == 2
    assert not (synth_sources[0] / "qa").exists()


def test_cli_refuses_two_sources_that_would_share_a_key(tmp_path, capsys):
    a = write_subject(tmp_path / "siteA" / "freesurfer", pipeline="freesurfer").parent
    b = write_subject(tmp_path / "siteB" / "freesurfer", pipeline="freesurfer").parent
    assert main(["build", str(a), str(b), "--out", str(tmp_path / "qa")]) == 2
    assert "freesurfer__sub-01" in capsys.readouterr().err
    assert not (tmp_path / "qa").exists()


def test_serve_accepts_blind(qa, monkeypatch):
    import uvicorn

    from surfaceqa import server

    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.update(kwargs))
    real = server.create_app
    monkeypatch.setattr(server, "create_app",
                        lambda qa_dir, blind=False: seen.update(blind=blind) or real(qa_dir, blind=blind))
    from surfaceqa.cli import main

    assert main(["serve", str(qa), "--blind"]) == 0
    assert seen["blind"] is True
    assert main(["serve", str(qa)]) == 0
    assert seen["blind"] is False


def test_export_command_writes_four_tables(qa, capsys):
    from surfaceqa.cli import main

    assert main(["export", str(qa)]) == 0
    assert sorted(p.name for p in (qa / "export").iterdir()) == [
        "final.tsv", "indicators.tsv", "marks.tsv", "ratings.tsv"]
    assert "ratings.tsv" in capsys.readouterr().out


def test_finalize_command_lists_disagreements(qa, capsys):
    from surfaceqa.cli import main
    from surfaceqa.layout import current_run_dir
    from surfaceqa.review_store import submit_review
    from tests.reviewing import MARK, make_review

    key = "fastsurfer__sub-01"
    run = current_run_dir(qa, key).name
    submit_review(qa, make_review("ann", key, run, sinus="major", grade="A", marks=[MARK]))
    submit_review(qa, make_review("bob", key, run, sinus="none", grade="C"))
    assert main(["finalize", str(qa)]) == 0
    out = capsys.readouterr().out
    assert f"{key}: Sagittal and transverse sinus (ann Major (needs fix), bob None); grade (ann A, bob C)" in out
    assert "1 disagreement" in out and "1 unreviewed" in out
    assert (qa / "final" / f"{key}.json").is_file()
    assert "disagreement" in (qa / "index.html").read_text()


def test_finalize_and_export_refuse_a_folder_that_is_not_a_qa_directory(tmp_path, capsys):
    from surfaceqa.cli import main

    assert main(["finalize", str(tmp_path)]) == 2
    assert main(["export", str(tmp_path)]) == 2
    assert "surfaceqa build" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_build_stores_the_rerun_template_for_each_source(synth_sources, tmp_path):
    from surfaceqa.settings import rerun_template

    out = tmp_path / "qa"
    template = "docker run img {command}"
    assert main(["build", *map(str, synth_sources), "--out", str(out), "--rerun-template", template]) == 0
    assert all(rerun_template(out, source.name) == template for source in synth_sources)


def test_build_refuses_a_rerun_template_without_the_placeholder(synth_sources, tmp_path, capsys):
    out = tmp_path / "qa"
    code = main(["build", str(synth_sources[0]), "--out", str(out), "--rerun-template", "docker run img"])
    assert code == 2 and "{command}" in capsys.readouterr().err
    assert not out.exists()


def test_build_compares_the_subjects_of_a_source_folder(tmp_path, monkeypatch):
    from surfaceqa.cohort import load_cohort
    from tests.synth import write_qa_files

    for i in range(3):
        write_qa_files(write_subject(tmp_path / "fs", name=f"sub-{i:02d}"))
    qa = tmp_path / "qa"
    assert main(["build", str(tmp_path / "fs"), "--out", str(qa)]) == 0
    cohort = load_cohort(qa, "fs")
    assert cohort.n == 3 and cohort.median is None  # thirty are needed
    page = (qa / "subjects" / "fs__sub-00" / "index.html").read_text()
    assert "needs 30 subjects in this source folder; there are 3" in page


def test_report_command_writes_the_page_and_prints_where(qa, capsys):
    assert main(["report", str(qa)]) == 0
    assert (qa / "report" / "index.html").is_file()
    assert str(qa / "report" / "index.html") in capsys.readouterr().out


def test_report_refuses_a_folder_that_is_not_a_qa_directory(tmp_path):
    assert main(["report", str(tmp_path)]) == 2
    assert not (tmp_path / "report").exists()


def test_build_records_the_sources_as_given(synth_sources, tmp_path):
    from surfaceqa.settings import sources

    qa = tmp_path / "qa"
    one_subject = synth_sources[1] / "sub-01"
    assert main(["build", str(synth_sources[0]), str(one_subject), "--out", str(qa)]) == 0
    assert sources(qa) == [synth_sources[0].resolve(), one_subject.resolve()]


def test_a_later_build_with_a_template_keeps_the_recorded_sources(synth_sources, tmp_path):
    from surfaceqa.settings import rerun_template, sources

    qa = tmp_path / "qa"
    main(["build", str(synth_sources[0]), "--out", str(qa)])
    main(["build", str(synth_sources[1]), "--out", str(qa), "--rerun-template", "ssh box {command}"])
    assert sources(qa) == [s.resolve() for s in synth_sources]
    assert rerun_template(qa, "freesurfer-8.2.0") == "ssh box {command}"


# ---- surfaceqa with no sub-command: the start page --------------------------------------------

import re
import socket

import pytest


@pytest.fixture
def launched(monkeypatch):
    """Run the start command without a real server or browser; records what it would do."""
    import uvicorn

    from surfaceqa import cli

    seen = {"opened": []}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.update(app=app, **kwargs))
    monkeypatch.setattr(cli, "_open_when_listening", lambda port, address: seen["opened"].append((port, address)))
    return seen


def _free() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.mark.parametrize("argv", [[], ["start"]])
def test_no_sub_command_starts_the_start_page(launched, capsys, argv):
    port = _free()
    assert main([*argv, *(["--port", str(port)] if argv else [])]) == 0
    assert launched["host"] == "127.0.0.1"
    app = launched["app"]
    assert app.state.qa_dir is None and len(app.state.start.token) >= 16
    printed = capsys.readouterr().out
    address = re.search(r"http://127\.0\.0\.1:(\d+)/\?token=(\S+)", printed)
    assert address and int(address.group(1)) == launched["port"] and address.group(2) == app.state.start.token
    assert launched["opened"] == [(launched["port"], address.group(0))]
    if argv:
        assert launched["port"] == port


def test_each_launch_has_its_own_token(launched):
    main(["start", "--port", str(_free())])
    first = launched["app"].state.start.token
    main(["start", "--port", str(_free())])
    assert launched["app"].state.start.token != first


@pytest.mark.parametrize("argv", [["--no-browser"], ["start", "--no-browser"]])
def test_no_browser(launched, argv):
    assert main(argv) == 0
    assert launched["opened"] == [] and launched["host"] == "127.0.0.1"


def test_a_taken_port_moves_to_the_next_free_one(launched, capsys):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        assert main(["start", "--port", str(port), "--no-browser"]) == 0
    assert port < launched["port"] <= port + 20
    assert f"http://127.0.0.1:{launched['port']}/" in capsys.readouterr().out


def test_start_cannot_be_given_a_host(launched):
    with pytest.raises(SystemExit) as stop:
        main(["start", "--host", "0.0.0.0"])
    assert stop.value.code == 2 and "app" not in launched


def test_help_lists_start(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0 and "start" in capsys.readouterr().out


def test_a_build_still_running_is_stopped_when_the_tool_is_closed(monkeypatch):
    import uvicorn

    from surfaceqa import cli, jobs

    job, cancelled = object(), []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: setattr(app.state.start, "job", job))
    monkeypatch.setattr(jobs, "cancel", cancelled.append)
    monkeypatch.setattr(cli, "_open_when_listening", lambda port, address: None)
    assert main(["start", "--port", str(_free())]) == 0
    assert cancelled == [job]


def test_the_browser_is_opened_once_the_port_answers(monkeypatch):
    import webbrowser

    from surfaceqa import cli

    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        cli._open_when_listening(server.getsockname()[1], "http://x/").join(timeout=10)
    assert opened == ["http://x/"]


def test_the_browser_is_not_opened_when_nothing_ever_listens(monkeypatch):
    import webbrowser

    from surfaceqa import cli

    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    cli._open_when_listening(_free(), "http://x/", wait=0.3).join(timeout=10)
    assert opened == []


# ---- found by review -------------------------------------------------------------------------

def test_build_refuses_an_out_that_contains_a_source(tmp_path, capsys):
    write_subject(tmp_path / "a" / "subjects")
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    assert main(["build", str(tmp_path / "a" / "subjects"), "--out", str(tmp_path / "a")]) == 2
    assert "contains" in capsys.readouterr().err
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before


def _group_members(pid):
    import subprocess

    return subprocess.run(["ps", "-o", "pid=", "-g", str(pid)], capture_output=True, text=True).stdout.split()


@pytest.mark.parametrize("how", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_closing_the_tool_stops_its_build(how, many, tmp_path, surfaceqa_home):
    """The real program: a terminal that is closed or an ssh session that drops must not leave
    a build running that nobody can see or cancel."""
    import os
    import signal
    import subprocess
    import sys
    import time

    import httpx

    port = _free()
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "SURFACEQA_HOME": str(surfaceqa_home)}
    tool = subprocess.Popen([sys.executable, "-m", "surfaceqa.cli", "start", "--no-browser", "--port", str(port)],
                            stdout=subprocess.PIPE, text=True, env=env)
    try:
        address = re.search(r"http://\S+", tool.stdout.readline()).group(0)
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base, follow_redirects=True, timeout=10) as client:
            for _ in range(100):
                try:
                    client.get(address)
                    break
                except httpx.ConnectError:
                    time.sleep(0.1)
            client.post("/start/build", data={"source": str(many), "out": str(tmp_path / "qa")},
                        headers={"origin": base})
            status = {}
            for _ in range(600):
                status = client.get("/start/status").json()
                if status.get("pid") and status.get("done", 0) >= 1 or status["state"] != "running":
                    break
                time.sleep(0.05)
        assert status["state"] == "running", status
        tool.send_signal(getattr(signal, how))
        tool.wait(timeout=20)
        deadline = time.monotonic() + 10
        while _group_members(status["pid"]) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert _group_members(status["pid"]) == []
    finally:
        if tool.poll() is None:
            tool.kill()
