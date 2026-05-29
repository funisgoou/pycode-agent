from __future__ import annotations
import subprocess
from pydantic import BaseModel
from pycode_agent.core.messages import ToolResult
from .base import Tool, Risk, ToolContext


def _git(ctx: ToolContext, *git_args: str) -> ToolResult:
    try:
        proc = subprocess.run(
            ["git", *git_args], cwd=str(ctx.project_dir),
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return ToolResult(ok=False, error="git not found")
    if proc.returncode != 0:
        return ToolResult(ok=False, error=proc.stderr.strip() or "git failed")
    return ToolResult(ok=True, content=proc.stdout or "(empty)")


class NoArgs(BaseModel):
    pass


class GitStatus(Tool):
    name = "git_status"
    description = "查看 git 工作区状态"
    args_model = NoArgs
    risk = Risk.LOW

    def run(self, args: NoArgs, ctx: ToolContext) -> ToolResult:
        return _git(ctx, "status", "--short", "--branch")


class DiffArgs(BaseModel):
    staged: bool = False


class GitDiff(Tool):
    name = "git_diff"
    description = "查看 git diff(可选 staged)"
    args_model = DiffArgs
    risk = Risk.LOW

    def run(self, args: DiffArgs, ctx: ToolContext) -> ToolResult:
        extra = ["--staged"] if args.staged else []
        return _git(ctx, "diff", *extra)
