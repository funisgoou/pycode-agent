from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from pycode_agent.core.messages import ToolResult
from pycode_agent.security.paths import is_sensitive
from pycode_agent.utils.proc import run_command

from .base import Risk, Tool, ToolContext

logger = logging.getLogger(__name__)

MAX_READ_BYTES = 200_000
MAX_LINES = 2000


class PathOutsideProjectError(Exception):
    ...


def _resolve(ctx: ToolContext, rel: str) -> Path:
    base = Path(ctx.project_dir).resolve()
    target = (base / rel).resolve()
    if target != base and base not in target.parents:
        raise PathOutsideProjectError(f"path escapes project root: {rel}")
    return target


def _patch_manager(ctx: ToolContext):
    """Return the context's PatchManager, or a fresh default if none was set."""
    from pycode_agent.utils.diff import PatchManager
    return ctx.patch_manager or PatchManager()


def _preview_write(ctx: ToolContext, path: str, content: str) -> str:
    """Shared diff-preview used by the full-file write/edit tools."""
    try:
        return _patch_manager(ctx).preview(_resolve(ctx, path), content)
    except Exception:
        logger.debug("write preview failed for %s", path, exc_info=True)
        return ""


class ReadArgs(BaseModel):
    path: str = Field(description="项目内相对路径")
    start_line: int | None = Field(default=None, description="起始行号(1-based, 包含)")
    end_line: int | None = Field(default=None, description="结束行号(1-based, 包含)")


class ReadFile(Tool[ReadArgs]):
    name = "read_file"
    description = "读取文本文件内容(相对项目根目录, 可选行号范围)"
    args_model = ReadArgs
    risk = Risk.LOW

    def run(self, args: ReadArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        p = _resolve(ctx, args.path)
        if not p.is_file():
            return ToolResult(ok=False, error=f"not a file: {args.path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        # Optional line-range slicing (1-based, inclusive on both ends).
        if args.start_line is not None or args.end_line is not None:
            lines = text.splitlines(keepends=True)
            start = max((args.start_line or 1) - 1, 0)
            end = args.end_line if args.end_line is not None else len(lines)
            selected = lines[start:end]
            total = len(lines)
            header = f"[lines {start + 1}-{start + len(selected)} of {total}]\n"
            text = header + "".join(selected)
        else:
            text = text[:MAX_READ_BYTES]
        return ToolResult(ok=True, content=text)


class ListArgs(BaseModel):
    path: str = "."


class ListDir(Tool[ListArgs]):
    name = "list_dir"
    description = "列出目录下的文件与子目录"
    args_model = ListArgs
    risk = Risk.LOW

    def run(self, args: ListArgs, ctx: ToolContext) -> ToolResult:
        p = _resolve(ctx, args.path)
        if not p.is_dir():
            return ToolResult(ok=False, error=f"not a dir: {args.path}")
        entries = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
        return ToolResult(ok=True, content="\n".join(entries))


class SearchArgs(BaseModel):
    query: str
    path: str = "."


class SearchText(Tool[SearchArgs]):
    name = "search_text"
    description = "在项目中搜索文本(优先 ripgrep,回退 Python)"
    args_model = SearchArgs
    risk = Risk.LOW

    def run(self, args: SearchArgs, ctx: ToolContext) -> ToolResult:
        base = _resolve(ctx, args.path)
        out = run_command(
            ["rg", "-n", "--no-heading", args.query, str(base)], timeout=30,
        )
        # rg exits 0 (matches) or 1 (no matches); both are successful searches.
        if out.error is None and out.returncode in (0, 1):
            return ToolResult(ok=True, content=out.stdout[:MAX_READ_BYTES] or "(no matches)")
        # Python fallback (rg missing, timed out, or errored)
        hits: list[str] = []
        for f in base.rglob("*"):
            if not f.is_file() or is_sensitive(str(f)):
                continue
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if args.query in line:
                        hits.append(f"{f.relative_to(ctx.project_dir)}:{i}:{line}")
            except OSError:
                continue
        return ToolResult(ok=True, content="\n".join(hits[:500]) or "(no matches)")


class WriteArgs(BaseModel):
    path: str
    content: str


class WriteFile(Tool[WriteArgs]):
    name = "write_file"
    description = "写入或覆盖文件(高风险,需确认)"
    args_model = WriteArgs
    risk = Risk.HIGH

    def run(self, args: WriteArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        p = _resolve(ctx, args.path)
        _patch_manager(ctx).apply(p, args.content)
        return ToolResult(ok=True, content=f"wrote {args.path}")

    def preview(self, args: WriteArgs, ctx: ToolContext) -> str:
        return _preview_write(ctx, args.path, args.content)


class EditArgs(BaseModel):
    path: str
    content: str = Field(description="文件的完整新内容")
    expected_old: str | None = Field(default=None, description="期望的旧内容,用于冲突检测")


class EditFile(Tool[EditArgs]):
    name = "edit_file"
    description = "用新内容替换文件(展示 diff,高风险,需确认)"
    args_model = EditArgs
    risk = Risk.HIGH

    def run(self, args: EditArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        from pycode_agent.utils.diff import ConflictError
        p = _resolve(ctx, args.path)
        try:
            _patch_manager(ctx).apply(p, args.content, expected_old=args.expected_old)
        except ConflictError as e:
            return ToolResult(ok=False, error=str(e))
        return ToolResult(ok=True, content=f"edited {args.path}")

    def preview(self, args: EditArgs, ctx: ToolContext) -> str:
        return _preview_write(ctx, args.path, args.content)


class StrReplaceArgs(BaseModel):
    path: str = Field(description="项目内相对路径")
    old_string: str = Field(description="要替换的原文本,必须在文件中唯一出现")
    new_string: str = Field(description="替换后的新文本")


class StrReplace(Tool[StrReplaceArgs]):
    name = "str_replace"
    description = "在文件中把唯一出现的 old_string 替换为 new_string(展示 diff,高风险,需确认)"
    args_model = StrReplaceArgs
    risk = Risk.HIGH

    def _new_content(self, args: StrReplaceArgs, ctx: ToolContext) -> tuple[str | None, str | None]:
        """Returns (new_content, error). Exactly one is non-None."""
        p = _resolve(ctx, args.path)
        if not p.is_file():
            return None, f"not a file: {args.path}"
        text = p.read_text(encoding="utf-8", errors="replace")
        count = text.count(args.old_string)
        if count == 0:
            return None, f"old_string not found in {args.path}"
        if count > 1:
            return None, f"old_string is not unique ({count} matches) in {args.path}; add more context"
        return text.replace(args.old_string, args.new_string, 1), None

    def run(self, args: StrReplaceArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        new_content, error = self._new_content(args, ctx)
        if new_content is None:
            return ToolResult(ok=False, error=error)
        p = _resolve(ctx, args.path)
        _patch_manager(ctx).apply(p, new_content)
        return ToolResult(ok=True, content=f"replaced in {args.path}")

    def preview(self, args: StrReplaceArgs, ctx: ToolContext) -> str:
        if is_sensitive(args.path):
            return ""
        new_content, error = self._new_content(args, ctx)
        if new_content is None:
            return error or ""
        return _preview_write(ctx, args.path, new_content)


# ---------------------------------------------------------------------------
# grep_search — regex-aware text search (rg preferred, Python fallback)
# ---------------------------------------------------------------------------

class GrepArgs(BaseModel):
    pattern: str = Field(description="正则表达式搜索模式")
    path: str = "."
    case_sensitive: bool = Field(default=True, description="是否区分大小写")


class GrepSearch(Tool[GrepArgs]):
    name = "grep_search"
    description = "在项目中用正则表达式搜索文本(优先 ripgrep, 回退 Python)"
    args_model = GrepArgs
    risk = Risk.LOW

    def run(self, args: GrepArgs, ctx: ToolContext) -> ToolResult:
        base = _resolve(ctx, args.path)
        # Try ripgrep first — it is much faster than pure Python.
        flags = [] if args.case_sensitive else ["-i"]
        out = run_command(
            ["rg", "-n", "--no-heading", *flags, args.pattern, str(base)],
            timeout=30,
        )
        if out.error is None and out.returncode in (0, 1):
            return ToolResult(ok=True, content=out.stdout[:MAX_READ_BYTES] or "(no matches)")
        # Python fallback: compile the regex and walk the tree.
        try:
            rx = re.compile(args.pattern, 0 if args.case_sensitive else re.IGNORECASE)
        except re.error as e:
            return ToolResult(ok=False, error=f"invalid regex: {e}")
        hits: list[str] = []
        for f in base.rglob("*"):
            if not f.is_file() or is_sensitive(str(f)):
                continue
            try:
                for i, line in enumerate(
                    f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
                ):
                    if rx.search(line):
                        hits.append(f"{f.relative_to(ctx.project_dir)}:{i}:{line}")
                        if len(hits) >= 500:
                            break
            except OSError:
                continue
            if len(hits) >= 500:
                break
        return ToolResult(ok=True, content="\n".join(hits) or "(no matches)")


# ---------------------------------------------------------------------------
# glob_search — find files by filename pattern
# ---------------------------------------------------------------------------

class GlobArgs(BaseModel):
    pattern: str = Field(description="文件名 glob 模式, 如 '*.py' 或 '**/*.ts'")
    path: str = "."


class GlobSearch(Tool[GlobArgs]):
    name = "glob_search"
    description = "按文件名 glob 模式查找文件(如 *.py, **/*.ts)"
    args_model = GlobArgs
    risk = Risk.LOW

    def run(self, args: GlobArgs, ctx: ToolContext) -> ToolResult:
        base = _resolve(ctx, args.path)
        matches: list[str] = []
        for p in base.glob(args.pattern):
            if p.is_file() and not is_sensitive(str(p)):
                matches.append(str(p.relative_to(ctx.project_dir)))
                if len(matches) >= 200:
                    break
        if not matches:
            return ToolResult(ok=True, content="(no matches)")
        matches.sort()
        return ToolResult(ok=True, content="\n".join(matches))
