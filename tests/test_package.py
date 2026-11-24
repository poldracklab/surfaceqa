"""The package as a researcher gets it: `uvx surfaceqa` runs from the wheel alone."""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    out = tmp_path_factory.mktemp("dist")
    built = subprocess.run([uv, "build", "--wheel", "--out-dir", str(out), str(ROOT)],
                           capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    (path,) = out.glob("*.whl")
    return path


def test_wheel_is_version_0_2_0_under_the_mit_licence(wheel):
    assert wheel.name.startswith("surfaceqa-0.2.0-")
    with zipfile.ZipFile(wheel) as archive:
        (metadata,) = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        text = archive.read(metadata).decode()
        (licence,) = [n for n in archive.namelist() if n.endswith("LICENSE")]
        assert "MIT License" in archive.read(licence).decode()
    assert "License-Expression: MIT" in text and "Requires-Python: >=3.13" in text


def test_wheel_carries_every_template_and_script(wheel):
    web = ROOT / "src" / "surfaceqa" / "web"
    expected = {f"surfaceqa/web/{p.relative_to(web).as_posix()}" for p in web.rglob("*") if p.is_file()}
    assert {"surfaceqa/web/templates/start.html", "surfaceqa/web/templates/progress.html",
            "surfaceqa/web/static/start.js", "surfaceqa/web/static/app.css"} <= expected
    with zipfile.ZipFile(wheel) as archive:
        assert expected <= set(archive.namelist())


def test_wheel_has_no_tests_or_stray_files(wheel):
    with zipfile.ZipFile(wheel) as archive:
        tops = {name.split("/")[0] for name in archive.namelist()}
    assert tops == {"surfaceqa", "surfaceqa-0.2.0.dist-info"}


def test_the_readme_starts_with_the_one_command():
    readme = (ROOT / "README.md").read_text()
    quick = readme[readme.index("## Quick start"):readme.index("## Install")]
    assert "uvx surfaceqa" in quick and "git+https://github.com/poldracklab/surfaceqa" in quick
    assert "ssh -L 8765:localhost:8765" in quick and "--no-browser" in quick


CHECK = """
import sys
from pathlib import Path
import surfaceqa.server, surfaceqa.server_start
from fastapi.testclient import TestClient
assert Path(surfaceqa.server.__file__).is_relative_to(sys.argv[1]), surfaceqa.server.__file__
app = surfaceqa.server.create_app(None, start=surfaceqa.server_start.StartMode("t0ken"))
client = TestClient(app, base_url="http://127.0.0.1:8765", follow_redirects=False)
assert client.get("/start?token=t0ken").status_code == 303
assert "Inspect new data" in client.get("/start").text
for name in ("start.js", "start_logic.js", "progress.js", "app.css"):
    assert client.get(f"/static/{name}").status_code == 200, name
print("ok")
"""


def test_the_unpacked_wheel_serves_the_start_page_by_itself(wheel, tmp_path):
    """Run from the wheel's files alone, away from the checkout: the pages and scripts it needs
    must be inside it."""
    import os
    import sys

    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(tmp_path / "site")
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "site")}
    ran = subprocess.run([sys.executable, "-c", CHECK, str(tmp_path / "site")], cwd=tmp_path,
                         env=env, capture_output=True, text=True)
    assert ran.returncode == 0 and ran.stdout.strip() == "ok", ran.stderr
