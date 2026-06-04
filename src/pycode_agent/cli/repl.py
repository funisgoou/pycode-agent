from __future__ import annotations

import itertools
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console

from pycode_agent import __version__
from pycode_agent.cli.builder import build_agent_with_provider
from pycode_agent.cli.commands import SlashContext, build_builtin_registry
from pycode_agent.cli.render import StreamRenderer, status_line, status_text, welcome_banner
from pycode_agent.config.settings import Settings
from pycode_agent.core.agent import Agent
from pycode_agent.core.session import Session, SessionStore
from pycode_agent.model.base import LLMProvider


def _make_prompt_reader(
    project_dir: Path,
    commands: list[str],
    status_fn: Callable[[], str] | None = None,
) -> tuple[Callable[[str], str], bool]:
    """Return (reader, has_toolbar).

    reader is a callable(prompt_str) -> str. With prompt_toolkit available we
    get history, slash completion, a persistent bottom toolbar (status_fn),
    and multiline input (Enter submits, Alt+Enter inserts newline). Falls back
    to plain input() when prompt_toolkit is unavailable.
    """
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings

        hist_path = project_dir / ".pycode" / "history"
        hist_path.parent.mkdir(parents=True, exist_ok=True)

        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            event.current_buffer.validate_and_handle()

        @kb.add("escape", "enter")
        def _(event):
            event.current_buffer.insert_text("\n")

        # Build the session lazily on first read: PromptSession() eagerly
        # creates terminal output, which only works in a real console (it
        # raises under pipes/tests). Deferring keeps the factory usable in
        # non-interactive contexts while real reads get the full UI.
        session: dict[str, Any] = {"obj": None}

        def _read(prompt_str: str) -> str:
            if session["obj"] is None:
                try:
                    session["obj"] = PromptSession(
                        history=FileHistory(str(hist_path)),
                        completer=WordCompleter(commands, sentence=True),
                        bottom_toolbar=status_fn,
                        multiline=True,
                        key_bindings=kb,
                    )
                except Exception:
                    # No usable terminal (pipe/redirect): degrade to input().
                    return input(prompt_str)
            return session["obj"].prompt(prompt_str)

        return _read, True
    except Exception:
        def _read(prompt_str: str) -> str:
            return input(prompt_str)
        return _read, False


def run_repl(
    *,
    project_dir: Path,
    settings: Settings,
    provider_factory: Callable[[Settings], LLMProvider],
    session_store: SessionStore | None = None,
    resumed_session: Session | None = None,
) -> None:
    # Create Console inside the function so it picks up the UTF-8
    # reconfiguration done by _fix_windows_encoding() in main.py.
    console = Console()

    if session_store is None:
        session_store = SessionStore(project_dir / ".pycode" / "sessions")

    console.print(welcome_banner(settings, project_dir, version=__version__))
    console.print()

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
    def _status_fn():
        return status_text(agent, settings) if agent is not None else ""
    read_input, has_toolbar = _make_prompt_reader(project_dir, commands, status_fn=_status_fn)

    while True:
        try:
            user = read_input(f"{project_dir.name} > ").strip()
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
            assert slash_ctx is not None  # set alongside agent above
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
        # With a bottom toolbar the status is already persistent; only the
        # fallback (no prompt_toolkit) needs the scrolling status line.
        if not has_toolbar:
            console.print(status_line(agent, settings))

        # Normal agent interaction via streaming.
        try:
            with console.status("[dim]Thinking...[/]", spinner="dots"):
                stream_iter = agent.run_stream(user)
                first_event = next(stream_iter)

            def token_str() -> str:
                cm = getattr(agent, "context_manager", None)
                if cm is not None:
                    est = cm.estimate_tokens(agent.messages)
                    return f"📊 {est // 1000}k/{cm.budget // 1000}k tokens"
                return ""

            StreamRenderer(console, token_count_fn=token_str,
                           project_dir=str(project_dir)).consume(
                itertools.chain([first_event], stream_iter)
            )
        except KeyboardInterrupt:
            console.print("\n[dim][已中断][/]")
            continue
        except StopIteration:
            pass
        except SystemExit:
            return
        except Exception as e:  # noqa
            console.print(f"\n[bold red]Error:[/] {e}")
            continue


def _init_agent(
    project_dir: Path,
    settings: Settings,
    provider_factory: Callable[[Settings], LLMProvider],
    console: Console,
    session_store: SessionStore | None = None,
    resumed_session: Session | None = None,
) -> tuple[Agent, SlashContext]:
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
