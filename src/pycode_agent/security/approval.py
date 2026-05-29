from __future__ import annotations
from typing import Callable


class Approval:
    """确认交互。可注入 input/output 以便测试。"""

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
        ans = self._prompt("应用? [y/N] ").strip().lower()
        return ans in ("y", "yes")
