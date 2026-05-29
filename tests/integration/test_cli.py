from typer.testing import CliRunner
from pycode_agent.cli.main import app

runner = CliRunner()

def test_config_list_runs(tmp_path):
    result = runner.invoke(app, ["config", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "mode" in result.stdout.lower()

def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout

from pathlib import Path
from pycode_agent.cli.builder import build_agent_with_provider
from pycode_agent.model.fake import FakeLLMProvider
from pycode_agent.model.base import LLMResponse
from pycode_agent.config.settings import Settings

def test_build_agent_runs_with_fake(tmp_path):
    provider = FakeLLMProvider(script=[LLMResponse(text="hi from fake")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings(), auto_yes=True
    )
    assert agent.run("hello") == "hi from fake"

def test_build_agent_registers_core_tools(tmp_path):
    provider = FakeLLMProvider(script=[LLMResponse(text="x")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings(), auto_yes=True
    )
    names = {s["function"]["name"] for s in agent.registry.schemas()}
    assert {"read_file", "list_dir", "search_text", "write_file", "edit_file",
            "run_shell", "git_status", "git_diff", "memory_read", "memory_write"} <= names
