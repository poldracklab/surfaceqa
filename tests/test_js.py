import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = sorted(str(p) for p in (Path(__file__).parent / "js").glob("*.test.mjs"))


def test_node_logic_tests():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "--test", *JS_TESTS], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
