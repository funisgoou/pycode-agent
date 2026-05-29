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

import pycode_agent.cli.main as cli_main

def test_prompt_non_interactive_success(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_main, "_make_provider",
                        lambda settings: FakeLLMProvider(script=[LLMResponse(text="answer from fake")]))
    result = runner.invoke(app, ["-p", "hello", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "answer from fake" in result.stdout

def test_prompt_no_tools_empties_registry(tmp_path, monkeypatch):
    captured = {}
    real_build = cli_main.build_agent_with_provider
    def spy_build(**kwargs):
        agent = real_build(**kwargs)
        captured["agent"] = agent
        return agent
    monkeypatch.setattr(cli_main, "_make_provider",
                        lambda settings: FakeLLMProvider(script=[LLMResponse(text="ok")]))
    monkeypatch.setattr(cli_main, "build_agent_with_provider", spy_build)
    result = runner.invoke(app, ["-p", "hi", "--no-tools", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    # after --no-tools, the agent's registry should expose zero tool schemas
    assert captured["agent"].registry.schemas() == []

def test_prompt_error_exit_code_1(tmp_path, monkeypatch):
    class BoomProvider(FakeLLMProvider):
        def chat(self, *, messages, tools):
            raise RuntimeError("boom")
    monkeypatch.setattr(cli_main, "_make_provider",
                        lambda settings: BoomProvider(script=[]))
    result = runner.invoke(app, ["-p", "hi", "--project-dir", str(tmp_path)])
    assert result.exit_code == 1


def test_prompt_rejection_exit_code_2(tmp_path, monkeypatch):
    from pycode_agent.core.messages import ToolCall
    # model asks for a high-risk write, then gives up; user (auto) rejects -> exit 2
    monkeypatch.setattr(cli_main, "_make_provider",
                        lambda settings: FakeLLMProvider(script=[
                            LLMResponse(tool_calls=[ToolCall(id="c1", name="write_file",
                                        arguments={"path": "a.txt", "content": "x\n"})]),
                            LLMResponse(text="cannot proceed without approval"),
                        ]))
    # default confirm mode + no --auto-approve; piped stdin makes Approval deny
    result = runner.invoke(app, ["-p", "write a file", "--project-dir", str(tmp_path)],
                           input="")
    assert result.exit_code == 2


def test_prompt_json_output(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_main, "_make_provider",
                        lambda settings: FakeLLMProvider(script=[LLMResponse(text="hi json")]))
    result = runner.invoke(app, ["-p", "hello", "--json", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    import json as _json
    payload = _json.loads(result.stdout)
    assert payload["result"] == "hi json"
    assert payload["ok"] is True


def test_prompt_max_turns_override(tmp_path, monkeypatch):
    captured = {}
    real_build = cli_main.build_agent_with_provider
    def spy_build(**kwargs):
        agent = real_build(**kwargs)
        captured["agent"] = agent
        return agent
    monkeypatch.setattr(cli_main, "_make_provider",
                        lambda settings: FakeLLMProvider(script=[LLMResponse(text="ok")]))
    monkeypatch.setattr(cli_main, "build_agent_with_provider", spy_build)
    result = runner.invoke(app, ["-p", "hi", "--max-turns", "3", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert captured["agent"].max_turns == 3


def test_prompt_dry_run_sets_flag(tmp_path, monkeypatch):
    captured = {}
    real_build = cli_main.build_agent_with_provider
    def spy_build(**kwargs):
        agent = real_build(**kwargs)
        captured["agent"] = agent
        return agent
    monkeypatch.setattr(cli_main, "_make_provider",
                        lambda settings: FakeLLMProvider(script=[LLMResponse(text="ok")]))
    monkeypatch.setattr(cli_main, "build_agent_with_provider", spy_build)
    result = runner.invoke(app, ["-p", "hi", "--dry-run", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert captured["agent"].dry_run is True
