from typer.testing import CliRunner
from pycode_agent.cli.main import app

runner = CliRunner()

def test_config_list_runs(tmp_path):
    result = runner.invoke(app, ["config", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "mode" in result.stdout.lower()


def test_config_get_shows_value_and_source(tmp_path):
    result = runner.invoke(app, ["config", "get", "security.mode", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "confirm" in result.stdout
    assert "default" in result.stdout.lower()


def test_config_get_unknown_key_exit_1(tmp_path):
    result = runner.invoke(app, ["config", "get", "model.nope", "--project-dir", str(tmp_path)])
    assert result.exit_code == 1


def test_config_set_then_get(tmp_path):
    r1 = runner.invoke(app, ["config", "set", "security.mode", "workspace", "--project-dir", str(tmp_path)])
    assert r1.exit_code == 0
    r2 = runner.invoke(app, ["config", "get", "security.mode", "--project-dir", str(tmp_path)])
    assert "workspace" in r2.stdout
    assert "project" in r2.stdout.lower()

def test_version():
    from pycode_agent import __version__
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout

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


def test_builder_injects_context_manager(tmp_path):
    from pycode_agent.cli.builder import build_agent_with_provider
    from pycode_agent.config.settings import Settings
    from pycode_agent.model.fake import FakeLLMProvider
    from pycode_agent.model.base import LLMResponse

    provider = FakeLLMProvider([LLMResponse(text="ok")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings(),
    )
    assert agent.context_manager is not None
    assert agent.context_manager.budget == 96000


def test_builder_registers_str_replace(tmp_path):
    from pycode_agent.cli.builder import _build_registry
    from pycode_agent.config.settings import Settings
    reg = _build_registry(Settings())
    assert reg.get("str_replace") is not None


def test_read_input_falls_back_without_prompt_toolkit(monkeypatch, tmp_path):
    import builtins, importlib
    from pycode_agent.cli import repl as repl_mod
    importlib.reload(repl_mod)

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("prompt_toolkit"):
            raise ImportError("simulated")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    reader, _has = repl_mod._make_prompt_reader(tmp_path, ["/help", "/exit"], status_fn=lambda: "")
    assert callable(reader)


def test_builder_creates_sink_when_persist_enabled(tmp_path):
    from pycode_agent.cli.builder import build_agent_with_provider
    from pycode_agent.config.settings import Settings
    from pycode_agent.model.fake import FakeLLMProvider
    from pycode_agent.model.base import LLMResponse
    provider = FakeLLMProvider([LLMResponse(text="ok")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings())
    assert agent.session_sink is not None


def test_builder_no_sink_when_persist_disabled(tmp_path):
    from pycode_agent.cli.builder import build_agent_with_provider
    from pycode_agent.config.settings import Settings
    from pycode_agent.model.fake import FakeLLMProvider
    from pycode_agent.model.base import LLMResponse
    settings = Settings()
    settings.agent.persist_sessions = False
    provider = FakeLLMProvider([LLMResponse(text="ok")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=settings)
    assert agent.session_sink is None


def test_builder_injects_resumed_messages(tmp_path):
    from pycode_agent.cli.builder import build_agent_with_provider
    from pycode_agent.config.settings import Settings
    from pycode_agent.core.session import Session
    from pycode_agent.core.messages import Message
    from pycode_agent.model.fake import FakeLLMProvider
    from pycode_agent.model.base import LLMResponse
    sess = Session(id="s1", title="t", created_at="2026", messages=[
        Message(role="system", content="OLD SYS"),
        Message(role="user", content="earlier"),
        Message(role="assistant", content="reply"),
    ])
    provider = FakeLLMProvider([LLMResponse(text="ok")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings(), session=sess)
    assert agent.messages[0].content == "OLD SYS"
    assert any(m.content == "earlier" for m in agent.messages)


def test_builder_sink_writes_session_file(tmp_path):
    from pycode_agent.cli.builder import build_agent_with_provider
    from pycode_agent.config.settings import Settings
    from pycode_agent.core.session import SessionStore
    from pycode_agent.model.fake import FakeLLMProvider
    from pycode_agent.model.base import LLMResponse
    store = SessionStore(tmp_path / ".pycode" / "sessions")
    sess = store.new_session()
    provider = FakeLLMProvider([LLMResponse(text="answer")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings(),
        session_store=store, session=sess)
    agent.run("question")
    reloaded = store.load(sess.id)
    assert any(m.content == "question" for m in reloaded.messages)
    assert reloaded.title == "question"


def test_sessions_list_outputs_titles(tmp_path):
    from typer.testing import CliRunner
    from pycode_agent.cli.main import app
    from pycode_agent.core.session import SessionStore
    from pycode_agent.core.messages import Message
    store = SessionStore(tmp_path / ".pycode" / "sessions")
    s = store.new_session()
    s.messages = [Message(role="user", content="my first task")]
    s.title = "my first task"
    store.save(s)
    runner = CliRunner()
    result = runner.invoke(app, ["sessions", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "my first task" in result.stdout


def test_sessions_list_empty(tmp_path):
    from typer.testing import CliRunner
    from pycode_agent.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["sessions", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "no sessions" in result.stdout.lower()


def test_resume_unknown_id_exits_1(tmp_path):
    from typer.testing import CliRunner
    from pycode_agent.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["-p", "hi", "--resume", "nope", "--project-dir", str(tmp_path)])
    assert result.exit_code == 1
    # message may go to stderr depending on click version; check all available streams
    combined = result.output + str(result.exception)
    for attr in ("stderr",):
        try:
            combined += getattr(result, attr) or ""
        except (ValueError, AttributeError):
            pass
    assert "not found" in combined.lower()


def test_builder_confirm_console_highlights_diff(tmp_path):
    from io import StringIO
    from rich.console import Console
    from pycode_agent.cli.builder import build_agent_with_provider
    from pycode_agent.config.settings import Settings
    from pycode_agent.model.fake import FakeLLMProvider
    from pycode_agent.model.base import LLMResponse

    buf = StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=80)
    provider = FakeLLMProvider([LLMResponse(text="ok")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings(),
        confirm_console=console)
    agent.approval._prompt = lambda _: "n"
    agent.approval._auto_yes = False
    approved = agent.approval.ask("apply?", "--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\n")
    assert approved is False
    out = buf.getvalue()
    assert "x" in out and "y" in out


def test_builder_no_confirm_console_keeps_default(tmp_path):
    from pycode_agent.cli.builder import build_agent_with_provider
    from pycode_agent.config.settings import Settings
    from pycode_agent.model.fake import FakeLLMProvider
    from pycode_agent.model.base import LLMResponse
    provider = FakeLLMProvider([LLMResponse(text="ok")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings())
    assert agent.approval._out is print


def test_repl_smoke_renders_response(tmp_path, monkeypatch):
    # Drive run_repl with one user line then EOF; assert the assistant panel renders.
    import io
    from rich.console import Console
    from pycode_agent.cli import repl as repl_mod
    from pycode_agent.config.settings import Settings
    from pycode_agent.model.fake import FakeLLMProvider
    from pycode_agent.model.base import LLMResponse

    settings = Settings()
    # provider factory returns a fake provider with one scripted answer
    def factory(_settings):
        return FakeLLMProvider([LLMResponse(text="hello from agent")])

    # feed one line then EOF via a fake reader
    lines = iter(["say hi"])
    def fake_reader(project_dir, commands, status_fn=None):
        def _read(prompt):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError
        return _read, False
    monkeypatch.setattr(repl_mod, "_make_prompt_reader", fake_reader)

    buf = io.StringIO()
    monkeypatch.setattr(repl_mod, "Console",
                        lambda *a, **k: Console(file=buf, force_terminal=False, no_color=True, width=80))

    repl_mod.run_repl(project_dir=tmp_path, settings=settings, provider_factory=factory)
    out = buf.getvalue()
    assert "hello from agent" in out
    assert "assistant" in out  # panel rendered


def test_make_prompt_reader_returns_tuple_with_toolbar(tmp_path):
    from pycode_agent.cli.repl import _make_prompt_reader
    reader, has_toolbar = _make_prompt_reader(tmp_path, ["/help"], status_fn=lambda: "X")
    assert callable(reader)
    assert has_toolbar is True  # prompt_toolkit installed in dev env


def test_make_prompt_reader_fallback_without_prompt_toolkit(monkeypatch, tmp_path):
    import builtins
    from pycode_agent.cli.repl import _make_prompt_reader
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("prompt_toolkit"):
            raise ImportError("simulated")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    reader, has_toolbar = _make_prompt_reader(tmp_path, ["/help"], status_fn=lambda: "X")
    assert callable(reader)
    assert has_toolbar is False


def test_repl_interrupt_during_stream(tmp_path, monkeypatch):
    import io
    from rich.console import Console
    from pycode_agent.cli import repl as repl_mod
    from pycode_agent.config.settings import Settings

    class _InterruptingAgent:
        # minimal stand-in: run_stream raises KeyboardInterrupt mid-turn
        def __init__(self):
            self.messages = []
            self.context_manager = None
            class _P: model = "fake"
            self.provider = _P()
        def run_stream(self, user):
            raise KeyboardInterrupt()

    def fake_init_agent(project_dir, settings, provider_factory, console,
                        session_store=None, resumed_session=None):
        agent = _InterruptingAgent()
        return agent, None
    monkeypatch.setattr(repl_mod, "_init_agent", fake_init_agent)

    lines = iter(["do something"])
    def fake_reader(project_dir, commands, status_fn=None):
        def _read(prompt):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError
        return _read, False
    monkeypatch.setattr(repl_mod, "_make_prompt_reader", fake_reader)

    buf = io.StringIO()
    monkeypatch.setattr(repl_mod, "Console",
                        lambda *a, **k: Console(file=buf, force_terminal=False, no_color=True, width=80))

    # must not raise; must print interrupt notice
    repl_mod.run_repl(project_dir=tmp_path, settings=Settings(),
                      provider_factory=lambda s: None)
    out = buf.getvalue()
    assert "已中断" in out
