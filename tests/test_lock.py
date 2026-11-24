import json
import os
import subprocess
import sys

import pytest

from surfaceqa.lock import LOCK_FILE, Busy, build_lock, building


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_lock_is_held_inside_and_gone_after(tmp_path):
    assert not building(tmp_path)
    with build_lock(tmp_path):
        assert building(tmp_path)
        assert json.loads((tmp_path / LOCK_FILE).read_text()) == {"pid": os.getpid()}
    assert not building(tmp_path) and not (tmp_path / LOCK_FILE).exists()


def test_lock_creates_the_qa_directory(tmp_path):
    with build_lock(tmp_path / "qa"):
        assert (tmp_path / "qa" / LOCK_FILE).is_file()


def test_a_second_lock_is_refused_while_the_first_is_held(tmp_path):
    with build_lock(tmp_path):
        with pytest.raises(Busy):
            with build_lock(tmp_path):
                pass
        assert building(tmp_path)  # the refusal did not take the first lock away


def test_lock_is_released_when_the_build_raises(tmp_path):
    with pytest.raises(RuntimeError):
        with build_lock(tmp_path):
            raise RuntimeError("boom")
    assert not building(tmp_path)


@pytest.mark.parametrize("content", ["junk", "{}", '{"pid": "x"}'])
def test_an_unreadable_lock_does_not_block(tmp_path, content):
    (tmp_path / LOCK_FILE).write_text(content)
    assert not building(tmp_path)
    with build_lock(tmp_path):
        pass


def test_the_lock_of_a_dead_process_does_not_block(tmp_path):
    (tmp_path / LOCK_FILE).write_text(json.dumps({"pid": _dead_pid()}))
    assert not building(tmp_path)
    with build_lock(tmp_path):
        assert building(tmp_path)
