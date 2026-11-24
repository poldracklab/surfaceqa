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


def test_only_one_of_many_simultaneous_builders_is_inside_at_a_time(tmp_path):
    import threading
    import time

    barrier, guard = threading.Barrier(8), threading.Lock()
    seen = {"inside": 0, "most": 0, "admitted": 0, "refused": 0}

    def builder():
        barrier.wait()
        try:
            with build_lock(tmp_path):
                with guard:
                    seen["inside"] += 1
                    seen["admitted"] += 1
                    seen["most"] = max(seen["most"], seen["inside"])
                time.sleep(0.05)
                with guard:
                    seen["inside"] -= 1
        except Busy:
            with guard:
                seen["refused"] += 1

    for _ in range(5):
        threads = [threading.Thread(target=builder) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert seen["most"] == 1 and seen["admitted"] >= 5 and seen["admitted"] + seen["refused"] == 40


def test_release_does_not_take_a_held_lock_away(tmp_path):
    from surfaceqa.lock import release

    with build_lock(tmp_path):
        release(tmp_path)
        assert building(tmp_path)
        with pytest.raises(Busy):
            with build_lock(tmp_path):
                pass
    assert not building(tmp_path)


def test_two_builds_started_together_do_not_both_run(many, tmp_path):
    command = [sys.executable, "-m", "surfaceqa.cli", "build", str(many), "--out", str(tmp_path / "qa")]
    both = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    ends = [(p.communicate(), p.returncode) for p in both]
    codes = sorted(code for _, code in ends)
    assert codes == [0, 1], ends
    refused = next(out for out, code in ends if code == 1)
    assert "already running" in refused[1] and "failed" not in refused[0]
    assert len(list((tmp_path / "qa" / "subjects").iterdir())) == 12
