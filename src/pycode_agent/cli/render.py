from __future__ import annotations
from typing import Callable
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax

_SUMMARY_MAX = 200


def status_line(agent, settings) -> Text:
    """A dim status line shown above each prompt: model · mode · tokens."""
    parts = [str(agent.provider.model), str(settings.security.mode)]
    cm = getattr(agent, "context_manager", None)
    if cm is not None:
        est = cm.estimate_tokens(agent.messages)
        parts.append(f"{est // 1000}k/{cm.budget // 1000}k tokens")
    return Text("  " + "  ·  ".join(parts), style="dim")


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
