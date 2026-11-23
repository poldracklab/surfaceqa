import shutil
import subprocess

import pytest


def test_node_logic_tests():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "--test", "tests/js/"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
