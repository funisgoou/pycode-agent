from __future__ import annotations
import re
import subprocess
from pydantic import BaseModel, Field
from pycode_agent.core.messages import ToolResult
from .base import Tool, Risk, ToolContext

_BLACKLIST = [
    r"\brm\s+-rf\s+/",
    r"\bsudo\b",
    r"\bmkfs\b",
    r":\(\)\s*\{.*:\|:&.*\}",   # fork bomb
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\bchmod\s+-R\s+777\s+/",
]
_BL = [re.compile(p) for p in _BLACKLIST]

MAX_OUTPUT = 50_000


def is_blacklisted(command: str) -> bool:
    return any(rx.search(command) for rx in _BL)


_GIT_PUSH = re.compile(r"\bgit\s+push\b")


def is_git_push(command: str) -> bool:
    return bool(_GIT_PUSH.search(command))


class ShellArgs(BaseModel):
    command: str
    timeout: int = Field(default=60, le=600)


class RunShell(Tool):
    name = "run_shell"
    description = "执行 shell 命令(高风险,受黑名单与权限约束)"
    args_model = ShellArgs
    risk = Risk.HIGH

    def run(self, args: ShellArgs, ctx: ToolContext) -> ToolResult:
        if is_blacklisted(args.command):
            return ToolResult(ok=False, error="refused: command matches blacklist")
        if is_git_push(args.command):
            allowed = bool(getattr(getattr(ctx.settings, "security", None), "allow_git_push", False))
            if not allowed:
                return ToolResult(ok=False, error="refused: git push disabled (set security.allow_git_push)")
        try:
            proc = subprocess.run(
                args.command, shell=True, cwd=str(ctx.project_dir),
                capture_output=True, text=True, timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error="timed out", meta={"timed_out": True})
        out = (proc.stdout + (("\n[stderr]\n" + proc.stderr) if proc.stderr else ""))[:MAX_OUTPUT]
        return ToolResult(
            ok=proc.returncode == 0,
            content=out,
            error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
            meta={"exit_code": proc.returncode},
        )
