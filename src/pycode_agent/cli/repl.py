from __future__ import annotations

from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown

from pycode_agent.cli.builder import build_agent_with_provider
from pycode_agent.cli.commands import SlashContext, build_builtin_registry
from pycode_agent.model.streaming import (
    StreamEvent, TextDelta, ToolCallStart, ToolCallEnd, ToolResultEvent, TurnEnd,
)


def run_repl(*, project_dir: Path, settings, provider_factory):
    # Create Console inside the function so it picks up the UTF-8
    # reconfiguration done by _fix_windows_encoding() in main.py.
    console = Console()

    console.print("[bold green]PyCodeAgent[/] - 输入 /help 查看可用命令, /exit 退出")
    provider = provider_factory(settings)
    agent = build_agent_with_provider(
        provider=provider, project_dir=project_dir, settings=settings, auto_yes=False
    )

    registry = build_builtin_registry()
    slash_ctx = SlashContext(
        args="", agent=agent, settings=settings,
        project_dir=project_dir, console=console,
    )

    while True:
        try:
            user = console.input("[bold cyan]You >[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nbye")
            return

        if not user:
            continue

        # Slash commands
        if user.startswith("/"):
            try:
                handled = registry.dispatch(user, slash_ctx)
            except SystemExit:
                return
            if not handled:
                console.print("[red]未知命令, 输入 /help 查看可用命令[/]")
            continue

        # Normal agent interaction via streaming
        try:
            answer_parts: list[str] = []

            with console.status("[dim]Thinking...[/]", spinner="dots"):
                stream_iter = agent.run_stream(user)
                first_event = next(stream_iter)

            # Process first event
            _handle_event(first_event, console, answer_parts)

            for event in stream_iter:
                _handle_event(event, console, answer_parts)

        except StopAsyncIteration:
            pass
        except StopIteration:
            pass
        except SystemExit:
            return
        except Exception as e:  # noqa
            console.print(f"\n[bold red]Error:[/] {e}")
            continue


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
