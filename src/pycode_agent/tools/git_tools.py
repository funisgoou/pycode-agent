from __future__ import annotations

from pydantic import BaseModel

from pycode_agent.core.messages import ToolResult
from pycode_agent.utils.proc import run_command

from .base import NoArgs, Risk, Tool, ToolContext


def _git(ctx: ToolContext, *git_args: str) -> ToolResult:
    res = run_command(["git", *git_args], cwd=ctx.project_dir, timeout=30)
    if res.error is not None:
        return ToolResult(ok=False, error="git not found" if "git" in res.error else res.error)
    if res.returncode != 0:
        return ToolResult(ok=False, error=res.stderr.strip() or "git failed")
    return ToolResult(ok=True, content=res.stdout or "(empty)")


class GitStatus(Tool[NoArgs]):
    name = "git_status"
    description = "查看 git 工作区状态"
    args_model = NoArgs
    risk = Risk.LOW

    def run(self, args: NoArgs, ctx: ToolContext) -> ToolResult:
        return _git(ctx, "status", "--short", "--branch")


class DiffArgs(BaseModel):
    staged: bool = False


class GitDiff(Tool[DiffArgs]):
    name = "git_diff"
    description = "查看 git diff(可选 staged)"
    args_model = DiffArgs
    risk = Risk.LOW

    def run(self, args: DiffArgs, ctx: ToolContext) -> ToolResult:
        extra = ["--staged"] if args.staged else []
        return _git(ctx, "diff", *extra)
