from __future__ import annotations

from collections.abc import Callable


class Approval:
    """确认交互。可注入 input/output 以便测试。

    ``out_fn`` 默认用裸 ``print``（保持本模块不依赖 Rich）；交互式 REPL
    会通过 builder 注入一个 Rich 渲染器（见 ``make_confirm_printer``），
    使确认提示与 diff 走同一套控制台输出。
    """

    def __init__(self, prompt_fn: Callable[[str], str] = input,
                 out_fn: Callable[[str], None] = print, auto_yes: bool = False):
        self._prompt = prompt_fn
        self._out = out_fn
        self._auto_yes = auto_yes

    def ask(self, title: str, detail: str = "") -> bool:
        if self._auto_yes:
            return True
        self._out(f"\n[确认] {title}")
        if detail:
            self._out(detail)
        try:
            ans = self._prompt("继续? [y] 应用 / [n] 跳过 ").strip().lower()
        except (EOFError, OSError):
            return False
        return ans in ("y", "yes")
