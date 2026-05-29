from pathlib import Path
from pycode_agent.utils.diff import PatchManager, ConflictError
import pytest

def test_preview_unified_diff(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("line1\nline2\n", encoding="utf-8")
    pm = PatchManager()
    diff = pm.preview(f, "line1\nCHANGED\n")
    assert "-line2" in diff
    assert "+CHANGED" in diff

def test_apply_and_rollback(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("old\n", encoding="utf-8")
    pm = PatchManager()
    token = pm.apply(f, "new\n")
    assert f.read_text(encoding="utf-8") == "new\n"
    pm.rollback(token)
    assert f.read_text(encoding="utf-8") == "old\n"

def test_apply_new_file_then_rollback(tmp_path):
    f = tmp_path / "created.txt"
    pm = PatchManager()
    token = pm.apply(f, "hello\n")
    assert f.read_text(encoding="utf-8") == "hello\n"
    pm.rollback(token)
    assert not f.exists()

def test_conflict_when_expected_mismatch(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("actual\n", encoding="utf-8")
    pm = PatchManager()
    with pytest.raises(ConflictError):
        pm.apply(f, "new\n", expected_old="something else\n")
    assert f.read_text(encoding="utf-8") == "actual\n"  # 文件未被破坏
