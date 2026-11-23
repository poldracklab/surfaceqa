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
