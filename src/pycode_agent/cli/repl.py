from __future__ import annotations

from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown

from pycode_agent.cli.builder import build_agent_with_provider
from pycode_agent.cli.commands import SlashContext, build_builtin_registry
from pycode_agent.model.streaming import (
    StreamEvent, TextDelta, ToolCallStart, ToolCallEnd, ToolResultEvent, TurnEnd,
)


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


def run_repl(*, project_dir: Path, settings, provider_factory):
    # Create Console inside the function so it picks up the UTF-8
    # reconfiguration done by _fix_windows_encoding() in main.py.
    console = Console()

    console.print("[bold green]PyCodeAgent[/] - 输入 /help 查看可用命令, /exit 退出")

    # Lazy-init: agent is only built on first real user query, so startup
    # (printing the welcome message + prompt) is instant.
    agent = None
    slash_ctx: SlashContext | None = None
    registry = build_builtin_registry()

    commands = ["/help", "/model", "/config", "/status", "/clear", "/undo",
                "/tools", "/tokens", "/memory", "/diff", "/exit", "/quit"]
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
                    project_dir, settings, provider_factory, console
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
                    project_dir, settings, provider_factory, console
                )

        # Normal agent interaction via streaming.
        # Spinner only covers waiting for the FIRST event; once it arrives we
        # drop the spinner and print immediately so the first token is not
        # visually delayed behind the spinner.
        try:
            answer_parts: list[str] = []

            with console.status("[dim]Thinking...[/]", spinner="dots"):
                stream_iter = agent.run_stream(user)
                first_event = next(stream_iter)

            _handle_event(first_event, console, answer_parts)
            for event in stream_iter:
                _handle_event(event, console, answer_parts)

        except StopIteration:
            pass
        except SystemExit:
            return
        except Exception as e:  # noqa
            console.print(f"\n[bold red]Error:[/] {e}")
            continue


def _init_agent(project_dir, settings, provider_factory, console):
    """Build provider + agent + slash context. Called lazily on first use."""
    provider = provider_factory(settings)
    agent = build_agent_with_provider(
        provider=provider, project_dir=project_dir, settings=settings, auto_yes=False
    )
    ctx = SlashContext(
        args="", agent=agent, settings=settings,
        project_dir=project_dir, console=console,
    )
    return agent, ctx


def _handle_event(event: StreamEvent, console: Console, answer_parts: list[str]):
    if isinstance(event, TextDelta):
        console.print(event.text, end="")
        answer_parts.append(event.text)

    elif isinstance(event, ToolCallStart):
        console.print(f"\n[dim]  Tool: {event.name}(...)[/dim]")

    elif isinstance(event, ToolCallEnd):
        pass  # tool call assembled, will be executed

    elif isinstance(event, ToolResultEvent):
        icon = "[green]ok[/]" if event.ok else "[red]error[/]"
        brief = event.content[:80] if event.ok else (event.error or "")
        console.print(f"  {icon} {brief}")

    elif isinstance(event, TurnEnd):
        # If we accumulated text via TextDelta, it's already printed.
        # If the provider used fallback (no TextDelta), print now.
        text = event.text
        if text and not answer_parts:
            console.print(Markdown(text))
        elif answer_parts:
            console.print()  # final newline after streamed text
