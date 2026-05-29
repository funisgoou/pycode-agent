from pycode_agent.tools.base import ToolContext, Risk
from pycode_agent.tools.shell_tools import RunShell, is_blacklisted

def _ctx(tmp_path):
    return ToolContext(project_dir=tmp_path)

def test_blacklist_rm_rf_root():
    assert is_blacklisted("rm -rf /")
    assert is_blacklisted("sudo apt install x")
    assert is_blacklisted(":(){ :|:& };:")

def test_normal_command_not_blacklisted():
    assert not is_blacklisted("pytest -q")
    assert not is_blacklisted("git status")

def test_run_echo(tmp_path):
    res = RunShell().run(RunShell.args_model(command="echo hello"), _ctx(tmp_path))
    assert res.ok and "hello" in res.content
    assert res.meta["exit_code"] == 0

def test_blacklisted_refused(tmp_path):
    res = RunShell().run(RunShell.args_model(command="rm -rf /"), _ctx(tmp_path))
    assert not res.ok and "blacklist" in res.error.lower()

def test_run_shell_is_high_risk():
    assert RunShell.risk == Risk.HIGH
