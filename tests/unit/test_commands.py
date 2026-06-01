from __future__ import annotations
import pytest
from io import StringIO
from pathlib import Path
from rich.console import Console

from pycode_agent.cli.commands import (
    SlashCommandRegistry, SlashContext, build_builtin_registry,
)
from pycode_agent.model.base import LLMResponse
from pycode_agent.model.fake import FakeLLMProvider
from pycode_agent.core.agent import Agent
from pycode_agent.core.messages import Message
from pycode_agent.tools.registry import ToolRegistry
from pycode_agent.tools.base import ToolContext
from pycode_agent.security.policy import Policy
from pycode_agent.security.approval import Approval
from pycode_agent.logs.audit import AuditLog
from pycode_agent.utils.diff import PatchManager
from pycode_agent.config.loader import load_settings


def _make_ctx(tmp_path, console=None, agent=None):
    """Create a minimal SlashContext for testing."""
    if console is None:
        console = Console(file=StringIO(), force_terminal=False, no_color=True)
    if agent is None:
        provider = FakeLLMProvider([LLMResponse(text="ok")])
        pm = PatchManager()
        tctx = ToolContext(project_dir=tmp_path, settings=None, patch_manager=pm)
        agent = Agent(
            provider=provider,
            registry=ToolRegistry(),
            policy=Policy(mode="confirm"),
            approval=Approval(auto_yes=True),
            audit=AuditLog(tmp_path / ".pycode" / "audit.jsonl"),
            ctx=tctx,
        )
    settings = load_settings(tmp_path)
    return SlashContext(
        args="", agent=agent, settings=settings,
        project_dir=tmp_path, console=console,
    )


class TestSlashCommandRegistry:
    def test_non_slash_returns_false(self, tmp_path):
        reg = build_builtin_registry()
        ctx = _make_ctx(tmp_path)
        assert reg.dispatch("hello", ctx) is False

    def test_unknown_command_returns_false(self, tmp_path):
        reg = build_builtin_registry()
        ctx = _make_ctx(tmp_path)
        assert reg.dispatch("/foo", ctx) is False

    def test_help_prints_commands(self, tmp_path):
        reg = build_builtin_registry()
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        assert reg.dispatch("/help", ctx) is True
        output = buf.getvalue()
        assert "/help" in output
        assert "/exit" in output

    def test_clear_resets_messages(self, tmp_path):
        reg = build_builtin_registry()
        ctx = _make_ctx(tmp_path)
        # Add a user message to the agent
        ctx.agent.messages.append(Message(role="user", content="test"))
        assert len(ctx.agent.messages) == 2
        reg.dispatch("/clear", ctx)
        # Only system prompt should remain
        assert len(ctx.agent.messages) == 1
        assert ctx.agent.messages[0].role == "system"

    def test_model_switches_provider(self, tmp_path):
        reg = build_builtin_registry()
        ctx = _make_ctx(tmp_path)
        assert ctx.agent.provider.model != "gpt-4o"
        reg.dispatch("/model gpt-4o", ctx)
        assert ctx.agent.provider.model == "gpt-4o"

    def test_model_no_args_shows_current(self, tmp_path):
        reg = build_builtin_registry()
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        reg.dispatch("/model", ctx)
        output = buf.getvalue()
        assert "当前模型" in output

    def test_config_shows_key(self, tmp_path):
        reg = build_builtin_registry()
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        reg.dispatch("/config security.mode", ctx)
        output = buf.getvalue()
        assert "confirm" in output

    def test_status_shows_model(self, tmp_path):
        reg = build_builtin_registry()
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        reg.dispatch("/status", ctx)
        output = buf.getvalue()
        assert "模型" in output
        assert "安全模式" in output

    def test_exit_raises_system_exit(self, tmp_path):
        reg = build_builtin_registry()
        ctx = _make_ctx(tmp_path)
        with pytest.raises(SystemExit):
            reg.dispatch("/exit", ctx)

    def test_quit_raises_system_exit(self, tmp_path):
        reg = build_builtin_registry()
        ctx = _make_ctx(tmp_path)
        with pytest.raises(SystemExit):
            reg.dispatch("/quit", ctx)

    def test_undo_nothing(self, tmp_path):
        reg = build_builtin_registry()
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        reg.dispatch("/undo", ctx)
        output = buf.getvalue()
        assert "没有可撤销的修改" in output

    def test_help_text_lists_commands(self):
        reg = build_builtin_registry()
        text = reg.help_text()
        assert "/help" in text
        assert "/exit" in text
        assert "/clear" in text

    def test_tools_lists_tools(self, tmp_path):
        from pycode_agent.cli.builder import build_agent_with_provider
        from pycode_agent.config.settings import Settings
        from pycode_agent.model.fake import FakeLLMProvider
        from pycode_agent.model.base import LLMResponse
        provider = FakeLLMProvider([LLMResponse(text="ok")])
        agent = build_agent_with_provider(
            provider=provider, project_dir=tmp_path, settings=Settings())
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console, agent=agent)
        reg = build_builtin_registry()
        assert reg.dispatch("/tools", ctx) is True
        out = buf.getvalue()
        assert "read_file" in out and "str_replace" in out

    def test_tokens_shows_estimate(self, tmp_path):
        from pycode_agent.cli.builder import build_agent_with_provider
        from pycode_agent.config.settings import Settings
        from pycode_agent.model.fake import FakeLLMProvider
        from pycode_agent.model.base import LLMResponse
        provider = FakeLLMProvider([LLMResponse(text="ok")])
        agent = build_agent_with_provider(
            provider=provider, project_dir=tmp_path, settings=Settings())
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console, agent=agent)
        reg = build_builtin_registry()
        assert reg.dispatch("/tokens", ctx) is True
        assert "token" in buf.getvalue().lower()

    def test_memory_shows_content(self, tmp_path):
        (tmp_path / ".pycode").mkdir()
        (tmp_path / ".pycode" / "memory.md").write_text("MEMO123", encoding="utf-8")
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        reg = build_builtin_registry()
        assert reg.dispatch("/memory", ctx) is True
        assert "MEMO123" in buf.getvalue()

    def test_diff_no_changes(self, tmp_path):
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        reg = build_builtin_registry()
        assert reg.dispatch("/diff", ctx) is True
        assert "没有" in buf.getvalue()

    def test_sessions_lists(self, tmp_path):
        from pycode_agent.core.session import SessionStore
        from pycode_agent.core.messages import Message
        store = SessionStore(tmp_path / ".pycode" / "sessions")
        s = store.new_session()
        s.messages = [Message(role="user", content="task one")]
        s.title = "task one"
        store.save(s)
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        ctx.session_store = store
        reg = build_builtin_registry()
        assert reg.dispatch("/sessions", ctx) is True
        assert "task one" in buf.getvalue()

    def test_resume_switches_messages(self, tmp_path):
        from pycode_agent.core.session import SessionStore
        from pycode_agent.core.messages import Message
        store = SessionStore(tmp_path / ".pycode" / "sessions")
        s = store.new_session()
        s.messages = [Message(role="system", content="S"), Message(role="user", content="restored msg")]
        s.title = "restored msg"
        store.save(s)
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        ctx.session_store = store
        reg = build_builtin_registry()
        assert reg.dispatch(f"/resume {s.id}", ctx) is True
        assert any(m.content == "restored msg" for m in ctx.agent.messages)

    def test_resume_unknown_id_warns(self, tmp_path):
        from pycode_agent.core.session import SessionStore
        store = SessionStore(tmp_path / ".pycode" / "sessions")
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, no_color=True)
        ctx = _make_ctx(tmp_path, console=console)
        ctx.session_store = store
        reg = build_builtin_registry()
        assert reg.dispatch("/resume nope", ctx) is True
        assert "未找到" in buf.getvalue() or "not found" in buf.getvalue().lower()
