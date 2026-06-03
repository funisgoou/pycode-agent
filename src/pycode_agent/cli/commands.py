from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from pycode_agent.utils.proc import run_command

if TYPE_CHECKING:
    from pycode_agent.config.settings import Settings
    from pycode_agent.core.agent import Agent
    from pycode_agent.core.session import SessionStore


@dataclass
class SlashContext:
    """Context passed to every slash-command handler."""
    args: str
    agent: Agent
    settings: Settings
    project_dir: Path
    console: Console
    session_store: SessionStore | None = None


@dataclass
class SlashCommand:
    name: str
    description: str
    handler: Callable[[SlashContext], None]


class SlashCommandRegistry:
    """Registry for REPL slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}

    def register(self, name: str, description: str, handler: Callable[[SlashContext], None]) -> None:
        self._commands[name] = SlashCommand(name=name, description=description, handler=handler)

    def dispatch(self, line: str, ctx: SlashContext) -> bool:
        """Parse *line* and dispatch to the matching handler.

        Returns True if the line was a recognised slash command, False otherwise.
        """
        if not line.startswith("/"):
            return False
        parts = line.split(None, 1)
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        cmd = self._commands.get(name)
        if cmd is None:
            return False
        cmd.handler(SlashContext(
            args=args,
            agent=ctx.agent,
            settings=ctx.settings,
            project_dir=ctx.project_dir,
            console=ctx.console,
            session_store=ctx.session_store,
        ))
        return True

    def help_text(self) -> str:
        lines = []
        for name, cmd in sorted(self._commands.items()):
            lines.append(f"  {name:<16} {cmd.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in command handlers
# ---------------------------------------------------------------------------

def _cmd_help(ctx: SlashContext) -> None:
    """显示可用命令列表"""
    ctx.console.print("[bold]可用命令:[/]")
    # Access the registry that dispatched to us (stored on the context is not
    # available directly, so we accept it via closure in build_builtin_registry).
    # We use a small trick: attach the registry to the handler at registration.
    registry = _cmd_help._registry  # type: ignore[attr-defined]
    ctx.console.print(registry.help_text())


def _cmd_model(ctx: SlashContext) -> None:
    """切换当前会话模型"""
    if not ctx.args:
        ctx.console.print(f"[dim]当前模型: {ctx.agent.provider.model}[/]")
        return
    old = ctx.agent.provider.model
    ctx.agent.provider.model = ctx.args.strip()
    ctx.console.print(f"[green]模型已切换:[/] {old} → {ctx.agent.provider.model}")


def _cmd_config(ctx: SlashContext) -> None:
    """查看配置"""
    from pycode_agent.config.loader import get_setting_for_dir
    if not ctx.args:
        # Show key settings
        s = ctx.settings
        ctx.console.print(f"  model.name     = {s.model.name}")
        ctx.console.print(f"  model.base_url = {s.model.base_url}")
        ctx.console.print(f"  security.mode  = {s.security.mode}")
        ctx.console.print(f"  allow_shell    = {s.security.allow_shell}")
        return
    key = ctx.args.strip()
    try:
        value, source = get_setting_for_dir(ctx.project_dir, key)
    except KeyError as e:
        ctx.console.print(f"[red]错误:[/] {e}")
        return
    ctx.console.print(f"  {key} = {value}  (来源: {source})")


def _cmd_status(ctx: SlashContext) -> None:
    """显示当前会话状态"""
    ctx.console.print(f"  模型:     {ctx.agent.provider.model}")
    ctx.console.print(f"  安全模式: {ctx.settings.security.mode}")
    ctx.console.print(f"  消息数:   {len(ctx.agent.messages)}")
    ctx.console.print(f"  项目目录: {ctx.project_dir}")
    # Try git status
    result = run_command(
        ["git", "status", "--short", "--branch"], cwd=ctx.project_dir, timeout=5,
    )
    if result.error is None and result.returncode == 0:
        first_line = result.stdout.strip().split("\n")[0]
        ctx.console.print(f"  Git:      {first_line}")


def _cmd_clear(ctx: SlashContext) -> None:
    """清空对话上下文"""
    from pycode_agent.core.agent import SYSTEM_PROMPT
    prefix = ctx.agent.system_prefix
    ctx.agent.messages = [
        __import__("pycode_agent.core.messages", fromlist=["Message"]).Message(
            role="system",
            content=SYSTEM_PROMPT + ("\n\n" + prefix if prefix else ""),
        )
    ]
    ctx.console.print("[green]对话上下文已清空[/]")


def _cmd_undo(ctx: SlashContext) -> None:
    """撤销最近一次文件修改"""
    pm = ctx.agent.ctx.patch_manager
    if pm is not None and pm.rollback_last():
        ctx.console.print("[green]已撤销最近一次文件修改[/]")
    else:
        ctx.console.print("[yellow]没有可撤销的修改[/]")


def _cmd_exit(ctx: SlashContext) -> None:
    """退出 REPL"""
    raise SystemExit(0)


def _cmd_tools(ctx: SlashContext) -> None:
    """列出已注册工具及风险等级"""
    registry = ctx.agent.registry
    for tool in registry.tools():
        ctx.console.print(f"  {tool.name:<14} [dim]risk={tool.risk.name}[/]  {tool.description}")


def _cmd_tokens(ctx: SlashContext) -> None:
    """显示当前上下文估算 token 数与预算"""
    cm = getattr(ctx.agent, "context_manager", None)
    if cm is None:
        ctx.console.print("[yellow]未启用上下文管理[/]")
        return
    est = cm.estimate_tokens(ctx.agent.messages)
    ctx.console.print(f"  估算 tokens: {est} / 预算 {cm.budget}  (压缩阈值 {int(cm.budget * cm.ratio)})")


def _cmd_memory(ctx: SlashContext) -> None:
    """显示项目记忆 .pycode/memory.md"""
    p = ctx.project_dir / ".pycode" / "memory.md"
    if not p.is_file():
        ctx.console.print("[dim](no project memory yet)[/]")
        return
    ctx.console.print(p.read_text(encoding="utf-8"))


def _cmd_diff(ctx: SlashContext) -> None:
    """显示最近一次文件修改的 diff"""
    pm = ctx.agent.ctx.patch_manager
    token = pm.peek_last() if pm is not None else None
    if token is None:
        ctx.console.print("[yellow]没有可显示的修改[/]")
        return
    # token.old_content is the pre-edit state; diff it against the file's current content.
    current = token.path.read_text(encoding="utf-8") if token.path.is_file() else ""
    old = token.old_content or ""
    rendered = "".join(difflib.unified_diff(
        old.splitlines(keepends=True), current.splitlines(keepends=True),
        fromfile=str(token.path), tofile=str(token.path),
    ))
    if not rendered:
        ctx.console.print("[dim](no textual diff)[/]")
    else:
        from pycode_agent.cli.render import diff_to_renderable
        ctx.console.print(diff_to_renderable(rendered))


def _cmd_sessions(ctx: SlashContext) -> None:
    """列出本项目的会话"""
    store = ctx.session_store
    if store is None:
        ctx.console.print("[yellow]会话存储未启用[/]")
        return
    from datetime import datetime
    meta = store.list_meta()
    if not meta:
        ctx.console.print("[dim](no sessions)[/]")
        return
    for m in meta:
        when = datetime.fromtimestamp(m["mtime"]).strftime("%Y-%m-%d %H:%M")
        ctx.console.print(f'  {m["id"]}  {when}  turns={m["turns"]}  {m["title"]}')


def _cmd_resume(ctx: SlashContext) -> None:
    """切换到指定会话: /resume <id>"""
    store = ctx.session_store
    if store is None:
        ctx.console.print("[yellow]会话存储未启用[/]")
        return
    sid = ctx.args.strip()
    if not sid:
        ctx.console.print("[yellow]用法: /resume <id>[/]")
        return
    try:
        session = store.load(sid)
    except KeyError:
        ctx.console.print(f"[yellow]未找到会话: {sid}[/]")
        return
    ctx.agent.messages = list(session.messages)
    # Rebind the persistence sink so subsequent turns write to THIS session's
    # file, not the agent's original one.
    from pycode_agent.cli.builder import _make_session_sink
    ctx.agent.session_sink = _make_session_sink(store, session)
    ctx.console.print(f"[green]已切换到会话 {sid}({len(session.messages)} 条消息)[/]")


# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------

def build_builtin_registry() -> SlashCommandRegistry:
    """Create a SlashCommandRegistry with all built-in commands."""
    registry = SlashCommandRegistry()

    commands = [
        ("/help",   "显示可用命令列表",   _cmd_help),
        ("/model",  "切换当前会话模型",   _cmd_model),
        ("/config", "查看配置",           _cmd_config),
        ("/status", "显示当前会话状态",   _cmd_status),
        ("/clear",  "清空对话上下文",     _cmd_clear),
        ("/undo",   "撤销最近一次文件修改", _cmd_undo),
        ("/tools",  "列出已注册工具",     _cmd_tools),
        ("/tokens", "显示上下文 token 估算", _cmd_tokens),
        ("/memory", "显示项目记忆",       _cmd_memory),
        ("/diff",   "显示最近一次修改 diff", _cmd_diff),
        ("/sessions", "列出本项目会话",   _cmd_sessions),
        ("/resume",   "切换到指定会话",   _cmd_resume),
        ("/exit",   "退出 REPL",          _cmd_exit),
        ("/quit",   "退出 REPL",          _cmd_exit),
    ]

    for name, desc, handler in commands:
        registry.register(name, desc, handler)

    # Attach registry to help handler so it can print command list
    _cmd_help._registry = registry  # type: ignore[attr-defined]

    return registry
