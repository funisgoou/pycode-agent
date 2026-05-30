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
