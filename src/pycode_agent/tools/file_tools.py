from __future__ import annotations
import subprocess
from pathlib import Path
from pydantic import BaseModel, Field
from pycode_agent.core.messages import ToolResult
from pycode_agent.security.paths import is_sensitive
from .base import Tool, Risk, ToolContext

MAX_READ_BYTES = 200_000


class PathOutsideProjectError(Exception):
    ...


def _resolve(ctx: ToolContext, rel: str) -> Path:
    base = Path(ctx.project_dir).resolve()
    target = (base / rel).resolve()
    if target != base and base not in target.parents:
        raise PathOutsideProjectError(f"path escapes project root: {rel}")
    return target


class ReadArgs(BaseModel):
    path: str = Field(description="项目内相对路径")


class ReadFile(Tool):
    name = "read_file"
    description = "读取文本文件内容(相对项目根目录)"
    args_model = ReadArgs
    risk = Risk.LOW

    def run(self, args: ReadArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        p = _resolve(ctx, args.path)
        if not p.is_file():
            return ToolResult(ok=False, error=f"not a file: {args.path}")
        data = p.read_text(encoding="utf-8", errors="replace")[:MAX_READ_BYTES]
        return ToolResult(ok=True, content=data)


class ListArgs(BaseModel):
    path: str = "."


class ListDir(Tool):
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


class SearchText(Tool):
    name = "search_text"
    description = "在项目中搜索文本(优先 ripgrep,回退 Python)"
    args_model = SearchArgs
    risk = Risk.LOW

    def run(self, args: SearchArgs, ctx: ToolContext) -> ToolResult:
        base = _resolve(ctx, args.path)
        try:
            out = subprocess.run(
                ["rg", "-n", "--no-heading", args.query, str(base)],
                capture_output=True, text=True, timeout=30,
            )
            if out.returncode in (0, 1):
                return ToolResult(ok=True, content=out.stdout[:MAX_READ_BYTES] or "(no matches)")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Python fallback
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


class WriteFile(Tool):
    name = "write_file"
    description = "写入或覆盖文件(高风险,需确认)"
    args_model = WriteArgs
    risk = Risk.HIGH

    def run(self, args: WriteArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        p = _resolve(ctx, args.path)
        pm = ctx.patch_manager
        pm.apply(p, args.content)
        return ToolResult(ok=True, content=f"wrote {args.path}")

    def preview(self, args: WriteArgs, ctx: ToolContext) -> str:
        from pycode_agent.utils.diff import PatchManager
        try:
            return (ctx.patch_manager or PatchManager()).preview(_resolve(ctx, args.path), args.content)
        except Exception:
            return ""


class EditArgs(BaseModel):
    path: str
    content: str = Field(description="文件的完整新内容")
    expected_old: str | None = Field(default=None, description="期望的旧内容,用于冲突检测")


class EditFile(Tool):
    name = "edit_file"
    description = "用新内容替换文件(展示 diff,高风险,需确认)"
    args_model = EditArgs
    risk = Risk.HIGH

    def run(self, args: EditArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        from pycode_agent.utils.diff import ConflictError
        p = _resolve(ctx, args.path)
        pm = ctx.patch_manager
        try:
            pm.apply(p, args.content, expected_old=args.expected_old)
        except ConflictError as e:
            return ToolResult(ok=False, error=str(e))
        return ToolResult(ok=True, content=f"edited {args.path}")

    def preview(self, args: EditArgs, ctx: ToolContext) -> str:
        from pycode_agent.utils.diff import PatchManager
        try:
            return (ctx.patch_manager or PatchManager()).preview(_resolve(ctx, args.path), args.content)
        except Exception:
            return ""
