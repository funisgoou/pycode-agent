from pycode_agent.context.scanner import scan_project, IGNORED_DIRS

def test_ignores_common_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("", encoding="utf-8")
    profile = scan_project(tmp_path)
    assert "src/main.py" in profile.tree
    assert "node_modules" not in profile.tree

def test_detects_python(tmp_path):
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    profile = scan_project(tmp_path)
    assert "python" in profile.languages

def test_profile_summary_is_str(tmp_path):
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    profile = scan_project(tmp_path)
    assert isinstance(profile.summary(), str)
    assert profile.summary()
