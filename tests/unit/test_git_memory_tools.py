import subprocess

from pycode_agent.tools.base import Risk, ToolContext
from pycode_agent.tools.git_tools import GitDiff, GitStatus
from pycode_agent.tools.memory_tools import MemoryRead, MemoryWrite
from pycode_agent.utils.diff import PatchManager


def _git(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=a",
                    "commit", "--allow-empty", "-qm", "init"], cwd=tmp_path)

def _ctx(tmp_path):
    return ToolContext(project_dir=tmp_path, patch_manager=PatchManager())

def test_git_status(tmp_path):
    _git(tmp_path)
    (tmp_path / "new.py").write_text("x\n", encoding="utf-8")
    res = GitStatus().run(GitStatus.args_model(), _ctx(tmp_path))
    assert res.ok and "new.py" in res.content

def test_git_diff(tmp_path):
    _git(tmp_path)
    f = tmp_path / "a.py"
    f.write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path)
    res = GitDiff().run(GitDiff.args_model(staged=True), _ctx(tmp_path))
    assert res.ok and "a.py" in res.content

def test_memory_read_missing(tmp_path):
    res = MemoryRead().run(MemoryRead.args_model(), _ctx(tmp_path))
    assert res.ok and "no project memory" in res.content.lower()

def test_memory_write_and_read(tmp_path):
    MemoryWrite().run(MemoryWrite.args_model(content="# Mem\n- uses pytest\n"), _ctx(tmp_path))
    res = MemoryRead().run(MemoryRead.args_model(), _ctx(tmp_path))
    assert "uses pytest" in res.content

def test_memory_write_is_high_risk():
    assert MemoryWrite.risk == Risk.HIGH
