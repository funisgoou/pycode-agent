from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from rich.text import Text

from pycode_agent.model.streaming import (
    StreamEvent,
    TextDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolResultEvent,
    TurnEnd,
    UsageEvent,
)

if TYPE_CHECKING:
    from pycode_agent.config.settings import Settings
    from pycode_agent.core.agent import Agent

_SUMMARY_MAX = 200


def _status_parts(agent: Agent, settings: Settings) -> list[str]:
    """Shared status fields: model, mode, and tokens (if a context manager)."""
    parts = [str(agent.provider.model), str(settings.security.mode)]
    cm = getattr(agent, "context_manager", None)
    if cm is not None:
        est = cm.estimate_tokens(agent.messages)
        parts.append(f"{est // 1000}k/{cm.budget // 1000}k tokens")
    return parts


def status_line(agent: Agent, settings: Settings) -> Text:
    """A dim status line shown above each prompt: model · mode · tokens."""
    return Text("  " + "  ·  ".join(_status_parts(agent, settings)), style="dim")


def status_text(agent: Agent, settings: Settings) -> str:
    """Plain-string status for prompt_toolkit bottom_toolbar."""
    return "  ·  ".join(_status_parts(agent, settings))


# ── Welcome banner ──────────────────────────────────────────────────
# Mini terminal icon (left) + project info (right).

def welcome_banner(settings: Settings, project_dir: Path, *, version: str = "") -> Panel:
    """Clean welcome panel: key info at a glance, no decorative cruft."""
    model = str(settings.model.name)
    mode = str(settings.security.mode)
    cwd = str(project_dir)

    body = Text()
    body.append("Model   ", style="dim")
    body.append(model, style="white")
    body.append("\n")
    body.append("Mode    ", style="dim")
    body.append(mode, style="white")
    body.append("\n")
    body.append("CWD     ", style="dim")
    body.append(cwd, style="white")

    title = Text()
    title.append("Py", style="bold bright_magenta")
    title.append("Code", style="bold bright_cyan")
    title.append(" Agent", style="bold white")
    if version:
        title.append(f"  v{version}", style="bright_black")

    return Panel(
        body,
        title=title,
        title_align="left",
        border_style="cyan",
        subtitle="/help 查看命令  ·  Ctrl-C 中断生成",
        subtitle_align="left",
    )


def assistant_panel(text: str, elapsed_ms: float = 0, cwd: str = "") -> Panel:
    title = "assistant"
    if cwd:
        title += f"  ·  {cwd}"
    if elapsed_ms > 0:
        title += f"  ⏱ {elapsed_ms / 1000:.1f}s"
    return Panel(Markdown(text), title=title, title_align="left",
                 border_style="cyan")


def tool_result_panel(name: str, ok: bool, summary: str) -> Panel:
    status = "[green]ok[/]" if ok else "[red]error[/]"
    body = (summary or "")[:_SUMMARY_MAX]
    return Panel(Text(body), title=f"🔧 {name}  {status}", title_align="left",
                 border_style="green" if ok else "red")


def diff_to_renderable(text: str) -> Syntax:
    return Syntax(text or "(no changes)", "diff", theme="ansi_dark",
                  word_wrap=True)


def _looks_like_diff(text: str) -> bool:
    if "\n@@" in text or text.startswith("@@"):
        return True
    has_plus = any(ln.startswith("+") and not ln.startswith("+++")
                   for ln in text.splitlines())
    has_minus = any(ln.startswith("-") and not ln.startswith("---")
                    for ln in text.splitlines())
    return has_plus and has_minus


def make_confirm_printer(console: Console) -> Callable[[str], None]:
    """Return an out_fn(detail) that syntax-highlights diff-like detail."""
    def out_fn(detail: str) -> None:
        if isinstance(detail, str) and _looks_like_diff(detail):
            console.print(diff_to_renderable(detail))
        else:
            console.print(detail)
    return out_fn


class StreamRenderer:
    """Consume a StreamEvent iterator, rendering to a rich Console.

    Terminal: stream raw text via a Live region, then re-render the
    completed assistant message as a Markdown panel. Non-terminal
    (pipes/tests): silently accumulate and print the panel once — no
    control codes, so output is assertable.

    Displays a live timer (and optional token count) in the stream
    footer so the user can see response time as it ticks.
    """

    def __init__(self, console: Console, token_count_fn: Callable[[], str] | None = None,
                 project_dir: str = ""):
        self.console = console
        self._buffer: list[str] = []
        self._live: Live | None = None
        self._pending_tool: str | None = None
        self.final_text = ""
        self._start_time: float = 0
        self._token_count_fn = token_count_fn
        self._project_dir = project_dir

    def consume(self, events: Iterable[StreamEvent]) -> str:
        self._start_time = time.time()
        try:
            for event in events:
                self._handle(event)
        finally:
            self._stop_live()
        return self.final_text

    @property
    def _elapsed_ms(self) -> float:
        if self._start_time == 0:
            return 0
        return (time.time() - self._start_time) * 1000

    def _footer(self) -> str:
        """A dim one-liner showing elapsed time + optional token count."""
        parts = [f"⏱ {self._elapsed_ms / 1000:.1f}s"]
        if self._token_count_fn:
            try:
                tok = self._token_count_fn()
                if tok:
                    parts.append(tok)
            except Exception:
                pass
        return "  ·  ".join(parts)

    def _handle(self, event) -> None:
        if isinstance(event, TextDelta):
            self._buffer.append(event.text)
            self._update_live()
        elif isinstance(event, ToolCallStart):
            self._finalize_text()
            self._pending_tool = event.name
            self._show_running(event.name)
        elif isinstance(event, ToolCallEnd):
            pass
        elif isinstance(event, ToolResultEvent):
            elapsed = self._elapsed_ms
            self._stop_live()
            name = self._pending_tool or "tool"
            summary = event.content if event.ok else (event.error or "")
            panel = tool_result_panel(name, event.ok, summary)
            # Tag on elapsed time so far
            if self._is_terminal() and elapsed > 0:
                panel.title += f"  ⏱ {elapsed / 1000:.1f}s"
            self.console.print(panel)
            self._pending_tool = None
            self._show_thinking()
        elif isinstance(event, TurnEnd):
            elapsed = self._elapsed_ms
            if self._buffer:
                self._finalize_text(elapsed)
            elif event.text:
                self.console.print(assistant_panel(event.text, elapsed, self._project_dir))
                self.final_text += event.text
        elif isinstance(event, UsageEvent):
            pass  # future: store for display

    def _is_terminal(self) -> bool:
        return bool(getattr(self.console, "is_terminal", False))

    def _update_live(self) -> None:
        if not self._is_terminal():
            return
        buffered = "".join(self._buffer)
        footer = self._footer()
        display = Text.assemble(
            (buffered, ""),
            ("\n", ""),
            (footer, "dim"),
        )
        if self._live is None:
            self._live = Live(display, console=self.console,
                              refresh_per_second=12, transient=True)
            self._live.start()
        else:
            self._live.update(display)

    def _stop_live(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _show_running(self, tool_name: str) -> None:
        """Show a brief 'Running X...' indicator while a tool executes."""
        if not self._is_terminal():
            return
        self._stop_live()
        footer = self._footer()
        display = Text.assemble(
            (f"  Running {tool_name}...", "dim"),
            ("\n", ""),
            (footer, "dim"),
        )
        self._live = Live(display, console=self.console,
                          refresh_per_second=4, transient=True)
        self._live.start()

    def _show_thinking(self) -> None:
        """Show a 'Thinking...' indicator while waiting for the next API response."""
        if not self._is_terminal():
            return
        self._stop_live()
        footer = self._footer()
        display = Text.assemble(
            ("  Thinking...", "dim"),
            ("\n", ""),
            (footer, "dim"),
        )
        self._live = Live(display, console=self.console,
                          refresh_per_second=4, transient=True)
        self._live.start()

    def _finalize_text(self, elapsed_ms: float = 0) -> None:
        if not self._buffer:
            return
        text = "".join(self._buffer)
        self._buffer = []
        self._stop_live()
        self.console.print(assistant_panel(text, elapsed_ms, self._project_dir))
        self.final_text += text
