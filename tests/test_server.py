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
