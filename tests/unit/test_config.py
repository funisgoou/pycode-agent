from pycode_agent.config.loader import (
    merge_config, get_setting, set_project_setting, load_settings,
)
from pycode_agent.config.settings import Settings

def test_cli_overrides_env():
    s = merge_config(
        env={"PYCODE_MODEL_NAME": "env-model"},
        user_file={"model": {"name": "user-model"}},
        project_file={"model": {"name": "proj-model"}},
        cli={"model": {"name": "cli-model"}},
    )
    assert s.model.name == "cli-model"

def test_project_overrides_user():
    s = merge_config(
        env={},
        user_file={"model": {"name": "user-model"}},
        project_file={"model": {"name": "proj-model"}},
        cli={},
    )
    assert s.model.name == "proj-model"

def test_defaults_when_empty():
    s = merge_config(env={}, user_file={}, project_file={}, cli={})
    assert s.security.mode == "confirm"
    assert s.model.timeout == 120


def test_get_setting_value_and_source_default():
    value, source = get_setting("security.mode", env={}, user_file={}, project_file={})
    assert value == "confirm"
    assert source == "default"


def test_get_setting_source_project_over_user():
    value, source = get_setting(
        "model.name", env={},
        user_file={"model": {"name": "u"}},
        project_file={"model": {"name": "p"}},
    )
    assert value == "p"
    assert source == "project"


def test_get_setting_source_env():
    value, source = get_setting(
        "model.name", env={"PYCODE_MODEL_NAME": "e"}, user_file={}, project_file={},
    )
    assert value == "e"
    assert source == "env"


def test_get_setting_unknown_key_raises():
    import pytest
    with pytest.raises(KeyError):
        get_setting("model.nope", env={}, user_file={}, project_file={})


def test_set_project_setting_writes_toml(tmp_path):
    set_project_setting(tmp_path, "security.mode", "workspace")
    s = load_settings(tmp_path)
    assert s.security.mode == "workspace"
    # value should land in the project config file
    cfg = tmp_path / ".pycode" / "config.toml"
    assert cfg.is_file()
    assert "workspace" in cfg.read_text(encoding="utf-8")


def test_set_project_setting_coerces_types(tmp_path):
    set_project_setting(tmp_path, "agent.max_turns", "5")
    set_project_setting(tmp_path, "security.allow_shell", "false")
    s = load_settings(tmp_path)
    assert s.agent.max_turns == 5
    assert s.security.allow_shell is False


def test_model_settings_compaction_defaults():
    from pycode_agent.config.settings import ModelSettings
    m = ModelSettings()
    assert m.context_budget == 96000
    assert m.compaction_ratio == 0.8
    assert m.keep_recent_turns == 6


def test_agent_settings_persist_sessions_default():
    from pycode_agent.config.settings import AgentSettings
    assert AgentSettings().persist_sessions is True
