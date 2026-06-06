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


def _git_branch(project_dir: Path) -> str:
    """Return the current git branch name, or '' if not a git repo."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""

_SUMMARY_MAX = 200


def _format_tokens(tokens: int) -> str:
    """Format token count: exact for <1k, abbreviated for >=1k."""
    if tokens >= 1000:
        return f"{tokens // 1000}k"
    return str(tokens)


def _status_parts(agent: Agent, settings: Settings) -> list[str]:
    """Shared status fields: model, mode, and tokens (if a context manager)."""
    parts = [str(agent.provider.model), str(settings.security.mode)]
    cm = getattr(agent, "context_manager", None)
    if cm is not None:
        est = cm.estimate_tokens(agent.messages)
        parts.append(f"{_format_tokens(est)}/{_format_tokens(cm.budget)} tokens")
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

    # Show current git branch if available.
    branch = _git_branch(project_dir)
    if branch:
        body.append("\n")
        body.append("Branch  ", style="dim")
        body.append(branch, style="white")

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


def tool_result_panel(name: str, ok: bool, summary: str, meta: dict | None = None) -> Panel:
    status = "[green]ok[/]" if ok else "[red]error[/]"
    body = (summary or "")[:_SUMMARY_MAX]
    # Surface useful meta info (e.g. exit_code) in the panel subtitle.
    subtitle = ""
    if meta:
        exit_code = meta.get("exit_code")
        if exit_code is not None and exit_code != 0:
            subtitle = f"exit_code={exit_code}"
        timed_out = meta.get("timed_out")
        if timed_out:
            subtitle = (subtitle + "  ·  " if subtitle else "") + "timed out"
    return Panel(Text(body), title=f"🔧 {name}  {status}", title_align="left",
                 subtitle=subtitle or None, subtitle_align="left",
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


class _DynamicLive(Live):
    """A Live subclass that re-evaluates its renderable on every refresh tick.

    The standard ``Live(display)`` captures a static snapshot; on Windows
    the background refresh thread then re-renders the *same* object, so the
    footer timer never ticks.  This subclass calls a factory function on
    each ``get_renderable()`` so elapsed time and token counts stay live.
    """

    def __init__(self, renderable_fn: Callable[[], Text], **kwargs):
        # Must assign _renderable_fn BEFORE super().__init__ because Rich's
        # Live.__init__ calls self.get_renderable() internally.
        self._renderable_fn = renderable_fn
        super().__init__(renderable_fn(), **kwargs)

    def get_renderable(self) -> Text:
        return self._renderable_fn()


class StreamRenderer:
    """Consume a StreamEvent iterator, rendering to a rich Console.

    Terminal: stream raw text via a Live region, then re-render the
    completed assistant message as a Markdown panel. Non-terminal
    (pipes/tests): silently accumulate and print the panel once — no
    control codes, so output is assertable.

    Displays a live timer (and optional token count) in the stream
    footer so the user can see response time as it ticks.

    When *show_tool_details* is False, intermediate tool-result panels
    and "Running..." / "Thinking..." indicators are suppressed — only
    the final assistant answer is displayed.
    """

    def __init__(self, console: Console, token_count_fn: Callable[[], str] | None = None,
                 project_dir: str = "", start_time: float | None = None,
                 show_tool_details: bool = True):
        self.console = console
        self._buffer: list[str] = []
        self._live: Live | None = None
        self._pending_tool: str | None = None
        self.final_text = ""
        # Allow the caller to pass in the time the LLM request *started*
        # (before the first event arrives), so the timer covers the full
        # thinking + tool execution window instead of only the consume phase.
        self._start_time: float = start_time or 0
        self._token_count_fn = token_count_fn
        self._project_dir = project_dir
        self._show_tool_details = show_tool_details

    def consume(self, events: Iterable[StreamEvent]) -> str:
        if self._start_time == 0:
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
            if self._show_tool_details:
                self._show_running(event.name)
        elif isinstance(event, ToolCallEnd):
            pass
        elif isinstance(event, ToolResultEvent):
            if self._show_tool_details:
                elapsed = self._elapsed_ms
                self._stop_live()
                name = self._pending_tool or "tool"
                summary = event.content if event.ok else (event.error or "")
                panel = tool_result_panel(name, event.ok, summary, meta=event.meta or None)
                # Tag on elapsed time so far
                if self._is_terminal() and elapsed > 0:
                    panel.title += f"  ⏱ {elapsed / 1000:.1f}s"
                self.console.print(panel)
                self._show_thinking()
            self._pending_tool = None
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
        # Use a dynamic renderable factory so the footer timer ticks on
        # every Live refresh, even on Windows where the refresh thread
        # re-renders asynchronously.
        def _render() -> Text:
            buffered = "".join(self._buffer)
            footer = self._footer()
            return Text.assemble(
                (buffered, ""),
                ("\n", ""),
                (footer, "dim"),
            )
        if self._live is None:
            self._live = _DynamicLive(_render, console=self.console,
                                      refresh_per_second=12, transient=True)
            self._live.start()
        else:
            # For content changes (new text deltas), force an immediate update
            # via the factory so the buffer content is current.
            self._live.update(_render())

    def _stop_live(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _show_running(self, tool_name: str) -> None:
        """Show a brief 'Running X...' indicator while a tool executes."""
        if not self._is_terminal():
            return
        self._stop_live()

        def _render() -> Text:
            footer = self._footer()
            return Text.assemble(
                (f"  Running {tool_name}...", "dim"),
                ("\n", ""),
                (footer, "dim"),
            )

        self._live = _DynamicLive(_render, console=self.console,
                                  refresh_per_second=4, transient=True)
        self._live.start()

    def _show_thinking(self) -> None:
        """Show a 'Thinking...' indicator while waiting for the next API response."""
        if not self._is_terminal():
            return
        self._stop_live()

        def _render() -> Text:
            footer = self._footer()
            return Text.assemble(
                ("  Thinking...", "dim"),
                ("\n", ""),
                (footer, "dim"),
            )

        self._live = _DynamicLive(_render, console=self.console,
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
