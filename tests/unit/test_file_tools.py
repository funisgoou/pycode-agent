from pathlib import Path
from pycode_agent.tools.base import ToolContext, Risk
from pycode_agent.tools.file_tools import ReadFile, ListDir, SearchText, WriteFile
from pycode_agent.utils.diff import PatchManager

def _ctx(tmp_path) -> ToolContext:
    return ToolContext(project_dir=tmp_path, patch_manager=PatchManager())

def test_read_file(tmp_path):
    (tmp_path / "a.py").write_text("print('x')\n", encoding="utf-8")
    res = ReadFile().run(ReadFile.args_model(path="a.py"), _ctx(tmp_path))
    assert res.ok and "print('x')" in res.content

def test_read_sensitive_blocked(tmp_path):
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    res = ReadFile().run(ReadFile.args_model(path=".env"), _ctx(tmp_path))
    assert not res.ok and "sensitive" in res.error.lower()

def test_list_dir(tmp_path):
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    res = ListDir().run(ListDir.args_model(path="."), _ctx(tmp_path))
    assert res.ok and "a.py" in res.content and "sub" in res.content

def test_search_text(tmp_path):
    (tmp_path / "a.py").write_text("hello world\nfoo\n", encoding="utf-8")
    res = SearchText().run(SearchText.args_model(query="hello"), _ctx(tmp_path))
    assert res.ok and "a.py" in res.content

def test_write_file_is_high_risk():
    assert WriteFile.risk == Risk.HIGH

def test_write_file_creates(tmp_path):
    res = WriteFile().run(WriteFile.args_model(path="new.txt", content="hi\n"), _ctx(tmp_path))
    assert res.ok
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "hi\n"

def test_read_path_traversal_blocked_via_dispatch(tmp_path):
    from pycode_agent.tools.registry import ToolRegistry
    from pycode_agent.tools.file_tools import ReadFile
    reg = ToolRegistry(); reg.register(ReadFile())
    res = reg.dispatch("read_file", {"path": "../../etc/passwd"}, _ctx(tmp_path))
    assert not res.ok and "escape" in res.error.lower()

def test_absolute_path_blocked_via_dispatch(tmp_path):
    from pycode_agent.tools.registry import ToolRegistry
    from pycode_agent.tools.file_tools import ReadFile
    reg = ToolRegistry(); reg.register(ReadFile())
    # an absolute path outside project
    outside = "/etc/hosts" if not str(tmp_path).startswith("C:") else "C:/Windows/win.ini"
    res = reg.dispatch("read_file", {"path": outside}, _ctx(tmp_path))
    assert not res.ok
