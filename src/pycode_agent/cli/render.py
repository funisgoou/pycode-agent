from __future__ import annotations
from typing import Callable
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.live import Live
from pycode_agent.model.streaming import (
    TextDelta, ToolCallStart, ToolCallEnd, ToolResultEvent, TurnEnd,
)

_SUMMARY_MAX = 200


def _status_parts(agent, settings) -> list[str]:
    """Shared status fields: model, mode, and tokens (if a context manager)."""
    parts = [str(agent.provider.model), str(settings.security.mode)]
    cm = getattr(agent, "context_manager", None)
    if cm is not None:
        est = cm.estimate_tokens(agent.messages)
        parts.append(f"{est // 1000}k/{cm.budget // 1000}k tokens")
    return parts


def status_line(agent, settings) -> Text:
    """A dim status line shown above each prompt: model · mode · tokens."""
    return Text("  " + "  ·  ".join(_status_parts(agent, settings)), style="dim")


def status_text(agent, settings) -> str:
    """Plain-string status for prompt_toolkit bottom_toolbar."""
    return "  ·  ".join(_status_parts(agent, settings))


def assistant_panel(text: str) -> Panel:
    return Panel(Markdown(text), title="assistant", title_align="left",
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


def make_confirm_printer(console) -> Callable[[str], None]:
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
    """

    def __init__(self, console):
        self.console = console
        self._buffer: list[str] = []
        self._live = None
        self._pending_tool: str | None = None
        self.final_text = ""

    def consume(self, events) -> str:
        try:
            for event in events:
                self._handle(event)
        finally:
            self._stop_live()
        return self.final_text

    def _handle(self, event) -> None:
        if isinstance(event, TextDelta):
            self._buffer.append(event.text)
            self._update_live()
        elif isinstance(event, ToolCallStart):
            self._finalize_text()
            self._pending_tool = event.name
        elif isinstance(event, ToolCallEnd):
            pass
        elif isinstance(event, ToolResultEvent):
            self._stop_live()
            name = self._pending_tool or "tool"
            summary = event.content if event.ok else (event.error or "")
            self.console.print(tool_result_panel(name, event.ok, summary))
            self._pending_tool = None
        elif isinstance(event, TurnEnd):
            if self._buffer:
                self._finalize_text()
            elif event.text:
                self.console.print(assistant_panel(event.text))
                self.final_text += event.text

    def _is_terminal(self) -> bool:
        return bool(getattr(self.console, "is_terminal", False))

    def _update_live(self) -> None:
        if not self._is_terminal():
            return
        text = Text("".join(self._buffer))
        if self._live is None:
            # transient=True so the raw streamed text is erased when the Live
            # stops; _finalize_text then prints the Markdown panel in its place
            # (otherwise the message renders twice — raw stream + panel).
            self._live = Live(text, console=self.console,
                              refresh_per_second=12, transient=True)
            self._live.start()
        else:
            self._live.update(text)

    def _stop_live(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _finalize_text(self) -> None:
        if not self._buffer:
            return
        text = "".join(self._buffer)
        self._buffer = []
        self._stop_live()
        self.console.print(assistant_panel(text))
        self.final_text += text
