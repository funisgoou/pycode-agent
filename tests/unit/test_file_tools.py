from pathlib import Path

from pycode_agent.tools.base import Risk, ToolContext
from pycode_agent.tools.file_tools import ListDir, ReadFile, SearchText, WriteFile
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
    from pycode_agent.tools.file_tools import ReadFile
    from pycode_agent.tools.registry import ToolRegistry
    reg = ToolRegistry(); reg.register(ReadFile())
    res = reg.dispatch("read_file", {"path": "../../etc/passwd"}, _ctx(tmp_path))
    assert not res.ok and "escape" in res.error.lower()

def test_absolute_path_blocked_via_dispatch(tmp_path):
    from pycode_agent.tools.file_tools import ReadFile
    from pycode_agent.tools.registry import ToolRegistry
    reg = ToolRegistry(); reg.register(ReadFile())
    # an absolute path outside project
    outside = "/etc/hosts" if not str(tmp_path).startswith("C:") else "C:/Windows/win.ini"
    res = reg.dispatch("read_file", {"path": outside}, _ctx(tmp_path))
    assert not res.ok


def test_str_replace_unique_match(tmp_path):
    from pycode_agent.tools.file_tools import StrReplace, StrReplaceArgs
    (tmp_path / "f.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    res = StrReplace().run(StrReplaceArgs(path="f.py", old_string="beta", new_string="BETA"), ctx)
    assert res.ok
    assert (tmp_path / "f.py").read_text() == "alpha\nBETA\ngamma\n"


def test_str_replace_not_found(tmp_path):
    from pycode_agent.tools.file_tools import StrReplace, StrReplaceArgs
    (tmp_path / "f.py").write_text("alpha\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    res = StrReplace().run(StrReplaceArgs(path="f.py", old_string="zzz", new_string="x"), ctx)
    assert not res.ok and "not found" in res.error


def test_str_replace_not_unique(tmp_path):
    from pycode_agent.tools.file_tools import StrReplace, StrReplaceArgs
    (tmp_path / "f.py").write_text("dup\ndup\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    res = StrReplace().run(StrReplaceArgs(path="f.py", old_string="dup", new_string="x"), ctx)
    assert not res.ok and "not unique" in res.error


def test_str_replace_refuses_sensitive(tmp_path):
    from pycode_agent.tools.file_tools import StrReplace, StrReplaceArgs
    ctx = _ctx(tmp_path)
    res = StrReplace().run(StrReplaceArgs(path=".env", old_string="a", new_string="b"), ctx)
    assert not res.ok and "sensitive" in res.error


def test_str_replace_missing_file(tmp_path):
    from pycode_agent.tools.file_tools import StrReplace, StrReplaceArgs
    ctx = _ctx(tmp_path)
    res = StrReplace().run(StrReplaceArgs(path="nope.py", old_string="a", new_string="b"), ctx)
    assert not res.ok and "not a file" in res.error


def test_search_text_python_fallback(tmp_path, monkeypatch):
    # Force the rg branch to fail so the pure-Python fallback runs.
    import pycode_agent.tools.file_tools as ft
    from pycode_agent.utils.proc import ProcResult
    monkeypatch.setattr(
        ft, "run_command",
        lambda *a, **k: ProcResult(ok=False, returncode=-1, stdout="", stderr="", error="not found"),
    )
    (tmp_path / "a.py").write_text("hello world\nfoo\n", encoding="utf-8")
    res = SearchText().run(SearchText.args_model(query="hello"), _ctx(tmp_path))
    assert res.ok and "a.py" in res.content and "hello" in res.content


def test_search_text_fallback_skips_sensitive(tmp_path, monkeypatch):
    import pycode_agent.tools.file_tools as ft
    from pycode_agent.utils.proc import ProcResult
    monkeypatch.setattr(
        ft, "run_command",
        lambda *a, **k: ProcResult(ok=False, returncode=-1, stdout="", stderr="", error="not found"),
    )
    (tmp_path / ".env").write_text("APIKEY=hello\n", encoding="utf-8")
    res = SearchText().run(SearchText.args_model(query="hello"), _ctx(tmp_path))
    assert res.ok and ".env" not in res.content


def test_write_preview_shows_diff(tmp_path):
    res = WriteFile().preview(WriteFile.args_model(path="new.txt", content="hi\n"), _ctx(tmp_path))
    assert "hi" in res


def test_str_replace_preview_shows_diff(tmp_path):
    from pycode_agent.tools.file_tools import StrReplace, StrReplaceArgs
    (tmp_path / "f.py").write_text("alpha\nbeta\n", encoding="utf-8")
    out = StrReplace().preview(StrReplaceArgs(path="f.py", old_string="beta", new_string="BETA"), _ctx(tmp_path))
    assert "BETA" in out


def test_write_file_without_patch_manager(tmp_path):
    # ctx.patch_manager is None → falls back to a default PatchManager, no crash.
    ctx = ToolContext(project_dir=tmp_path)
    res = WriteFile().run(WriteFile.args_model(path="n.txt", content="x\n"), ctx)
    assert res.ok
    assert (tmp_path / "n.txt").read_text(encoding="utf-8") == "x\n"
