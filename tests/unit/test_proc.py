import sys

from pycode_agent.utils.proc import ProcResult, run_command


def test_run_command_success():
    res = run_command([sys.executable, "-c", "print('hi')"])
    assert isinstance(res, ProcResult)
    assert res.ok and res.returncode == 0
    assert "hi" in res.stdout
    assert res.error is None


def test_run_command_nonzero_exit():
    res = run_command([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert not res.ok and res.returncode == 3
    assert res.error is None  # ran fine, just exited nonzero


def test_run_command_missing_program():
    res = run_command(["this-program-does-not-exist-xyz"])
    assert not res.ok and res.error is not None


def test_run_command_timeout():
    res = run_command(
        [sys.executable, "-c", "import time; time.sleep(5)"], timeout=1,
    )
    assert not res.ok and res.error == "timed out"
