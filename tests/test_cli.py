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
