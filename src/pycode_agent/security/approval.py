from __future__ import annotations

from collections.abc import Callable


class Approval:
    """确认交互。可注入 input/output 以便测试。

    当提供 ``console`` (Rich Console) 时，使用带样式的提示，快捷键清晰可见。
    ``out_fn`` 默认用裸 ``print``（保持本模块不依赖 Rich）；交互式 REPL
    会通过 builder 注入一个 Rich 渲染器（见 ``make_confirm_printer``），
    使确认提示与 diff 走同一套控制台输出。
    """

    def __init__(self, prompt_fn: Callable[[str], str] = input,
                 out_fn: Callable[[str], None] = print, auto_yes: bool = False,
                 console=None):
        self._prompt = prompt_fn
        self._out = out_fn
        self._auto_yes = auto_yes
        self._console = console

    def ask(self, title: str, detail: str = "") -> bool:
        if self._auto_yes:
            return True

        # ── Rich styled prompt ──
        if self._console is not None:
            from rich.panel import Panel
            from rich.text import Text

            body = Text()
            body.append(title, style="bold white")
            if detail:
                body.append("\n")
                body.append(detail, style="dim")

            hints = Text()
            hints.append("Y", style="bold green")
            hints.append(" 允许  ", style="white")
            hints.append("N", style="bold red")
            hints.append(" 拒绝", style="white")

            panel = Panel(
                body,
                title="[bold yellow]⏳ 确认[/]",
                title_align="left",
                subtitle=hints,
                subtitle_align="left",
                border_style="yellow",
            )
            self._console.print(panel)
            try:
                if self._console.is_terminal:
                    ans = self._console.input("> ").strip().lower()
                else:
                    ans = input("> ").strip().lower()
            except (EOFError, OSError):
                return False
            return ans in ("y", "yes")

        # ── plain fallback ──
        self._out(f"\n[确认] {title}")
        if detail:
            self._out(detail)
        try:
            ans = self._prompt("继续? [y] 允许 / [n] 拒绝 ").strip().lower()
        except (EOFError, OSError):
            return False
        return ans in ("y", "yes")
