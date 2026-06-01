from __future__ import annotations

import itertools
from pathlib import Path
from rich.console import Console

from pycode_agent.cli.builder import build_agent_with_provider
from pycode_agent.cli.commands import SlashContext, build_builtin_registry
from pycode_agent.cli.render import status_line, StreamRenderer
from pycode_agent.core.session import SessionStore


def _make_prompt_reader(project_dir: Path, commands: list[str]):
    """Return a callable(prompt_str) -> str for reading user input.

    Uses prompt_toolkit (history + slash-command completion) when available;
    falls back to a plain input() if prompt_toolkit can't be imported or
    initialized (e.g. non-interactive terminals).
    """
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.completion import WordCompleter

        hist_path = project_dir / ".pycode" / "history"
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        session = PromptSession(
            history=FileHistory(str(hist_path)),
            completer=WordCompleter(commands, sentence=True),
        )

        def _read(prompt_str: str) -> str:
            return session.prompt(prompt_str)

        return _read
    except Exception:
        def _read(prompt_str: str) -> str:
            return input(prompt_str)
        return _read


def run_repl(*, project_dir: Path, settings, provider_factory,
             session_store=None, resumed_session=None):
    # Create Console inside the function so it picks up the UTF-8
    # reconfiguration done by _fix_windows_encoding() in main.py.
    console = Console()

    if session_store is None:
        session_store = SessionStore(project_dir / ".pycode" / "sessions")

    console.print("[bold green]PyCodeAgent[/] - 输入 /help 查看可用命令, /exit 退出")

    if resumed_session is not None:
        console.print(f"[dim]已恢复会话 {resumed_session.id}({len(resumed_session.messages)} 条消息)[/]")

    # Lazy-init: agent is only built on first real user query, so startup
    # (printing the welcome message + prompt) is instant.
    agent = None
    slash_ctx: SlashContext | None = None
    registry = build_builtin_registry()

    commands = ["/help", "/model", "/config", "/status", "/clear", "/undo",
                "/tools", "/tokens", "/memory", "/diff", "/sessions", "/resume",
                "/exit", "/quit"]
    read_input = _make_prompt_reader(project_dir, commands)

    while True:
        try:
            user = read_input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nbye")
            return

        if not user:
            continue

        # Slash commands (these don't need a fully-built agent for most cases)
        if user.startswith("/"):
            # Build agent lazily if the command needs it (e.g. /status)
            if agent is None:
                agent, slash_ctx = _init_agent(
                    project_dir, settings, provider_factory, console,
                    session_store=session_store, resumed_session=resumed_session,
                )
            try:
                handled = registry.dispatch(user, slash_ctx)
            except SystemExit:
                return
            if not handled:
                console.print("[red]未知命令, 输入 /help 查看可用命令[/]")
            continue

        # First real query — build agent now, then stream the response.
        if agent is None:
            with console.status("[dim]Initializing...[/]", spinner="dots"):
                agent, slash_ctx = _init_agent(
                    project_dir, settings, provider_factory, console,
                    session_store=session_store, resumed_session=resumed_session,
                )

        # Status line (scrolls with content) above the streamed response.
        console.print(status_line(agent, settings))

        # Normal agent interaction via streaming.
        try:
            with console.status("[dim]Thinking...[/]", spinner="dots"):
                stream_iter = agent.run_stream(user)
                first_event = next(stream_iter)
            StreamRenderer(console).consume(
                itertools.chain([first_event], stream_iter)
            )
        except StopIteration:
            pass
        except SystemExit:
            return
        except Exception as e:  # noqa
            console.print(f"\n[bold red]Error:[/] {e}")
            continue


def _init_agent(project_dir, settings, provider_factory, console,
                session_store=None, resumed_session=None):
    """Build provider + agent + slash context. Called lazily on first use."""
    provider = provider_factory(settings)
    agent = build_agent_with_provider(
        provider=provider, project_dir=project_dir, settings=settings, auto_yes=False,
        session_store=session_store, session=resumed_session,
        confirm_console=console,
    )
    ctx = SlashContext(
        args="", agent=agent, settings=settings,
        project_dir=project_dir, console=console,
        session_store=session_store,
    )
    return agent, ctx
