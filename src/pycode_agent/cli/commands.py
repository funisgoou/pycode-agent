from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Callable
from rich.console import Console


@dataclass
class SlashContext:
    """Context passed to every slash-command handler."""
    args: str
    agent: object  # Agent instance (avoid circular import)
    settings: object
    project_dir: object  # Path
    console: Console


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
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            capture_output=True, text=True, timeout=5,
            cwd=str(ctx.project_dir),
        )
        if result.returncode == 0:
            first_line = result.stdout.strip().split("\n")[0]
            ctx.console.print(f"  Git:      {first_line}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


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
        ("/exit",   "退出 REPL",          _cmd_exit),
        ("/quit",   "退出 REPL",          _cmd_exit),
    ]

    for name, desc, handler in commands:
        registry.register(name, desc, handler)

    # Attach registry to help handler so it can print command list
    _cmd_help._registry = registry  # type: ignore[attr-defined]

    return registry
