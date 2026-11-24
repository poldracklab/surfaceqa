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


def test_pressing_the_mouse_in_a_checklist_section_does_not_scroll_it():
    """A section taller than the checklist panel was scrolled into view on mouse-down, which
    moved the rating button away from the cursor before the click landed. There is no browser
    in the test suite, so this guards the source: only the keyboard may scroll a section."""
    source = (Path(__file__).parent.parent / "src/surfaceqa/web/static/review.js").read_text()
    (press,) = [line for line in source.splitlines() if '"pointerdown"' in line]
    assert "setCurrent(index, {scroll: false})" in press
    assert "if (scroll) itemEls[index].scrollIntoView" in source


def test_a_failed_save_is_scheduled_again():
    """No browser in the suite: guards that the save failure paths ask for a retry and that a
    success clears the count."""
    source = (Path(__file__).parent.parent / "src/surfaceqa/web/static/review.js").read_text()
    save = source[source.index("async function saveNow"):source.index("function queueSave")]
    assert save.count("retryLater()") == 2 and "state.failures = 0" in save
    assert "L.retryDelay(state.failures)" in source
