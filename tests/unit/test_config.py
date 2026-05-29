from pycode_agent.config.loader import merge_config
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
