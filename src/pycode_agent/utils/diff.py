from __future__ import annotations
import difflib
from dataclasses import dataclass
from pathlib import Path


class ConflictError(Exception):
    ...


@dataclass
class RollbackToken:
    path: Path
    existed_before: bool
    old_content: str | None


class PatchManager:
    """整文件替换模型:预览 unified diff、应用、回滚最近一次变更。"""

    def __init__(self) -> None:
        self._last: RollbackToken | None = None

    def preview(self, path: Path, new_content: str) -> str:
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
        return "".join(diff)

    def apply(self, path: Path, new_content: str, expected_old: str | None = None) -> RollbackToken:
        existed = path.is_file()
        old = path.read_text(encoding="utf-8") if existed else None
        if expected_old is not None and (old or "") != expected_old:
            raise ConflictError(f"expected_old does not match current content of {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        token = RollbackToken(path=path, existed_before=existed, old_content=old)
        self._last = token
        return token

    def rollback(self, token: RollbackToken) -> None:
        if token.existed_before:
            token.path.write_text(token.old_content or "", encoding="utf-8")
        else:
            if token.path.exists():
                token.path.unlink()

    def rollback_last(self) -> bool:
        if self._last is None:
            return False
        self.rollback(self._last)
        self._last = None
        return True
