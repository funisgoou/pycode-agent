from __future__ import annotations

import logging
import re
import shlex
import subprocess

from pydantic import BaseModel, Field

from pycode_agent.core.messages import ToolResult

from .base import Risk, Tool, ToolContext

logger = logging.getLogger(__name__)

# Patterns matched against the raw command string. The blacklist is a
# defence-in-depth layer, not the primary safety boundary (that is the
# approval/policy system). It aims to stop obvious destructive or
# self-escalating commands even when the user has loosened the policy.
_BLACKLIST = [
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+/",   # rm -rf / and flag variants
    r"\bsudo\b",
    r"\bdoas\b",
    r"\bmkfs\b",
    r":\(\)\s*\{.*:\|:&.*\}",                # fork bomb
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\bchmod\s+-R\s+0?777\s+/",
    # Self-escalation: piping a network download straight into a shell.
    r"\b(curl|wget|fetch)\b[^|]*\|\s*(ba|z|fi|da|t?c|k|a)?sh\b",
    # Piping arbitrary output into an interpreter shell.
    r"\|\s*(ba|z|fi|da|t?c|k|a)?sh\b",
    # Reverse / bind shells via netcat.
    r"\bnc\b.*-e\b",
    r"\bncat\b.*-e\b",
    # ── Windows-specific dangerous commands ──
    r"\bformat\s+[a-zA-Z]:",                  # format C:
    r"\bdiskpart\b",                           # disk partitioning tool
    r"\breg\s+(delete|add)\b",                # registry modification
    r"\brd\s+/[a-zA-Z]*s[a-zA-Z]*\s+[a-zA-Z]:\\\s*$",  # rd /s /q C:\
    r"\bdel\s+/[a-zA-Z]*s[a-zA-Z]*\s+[a-zA-Z]:\\",    # del /s C:\
    r"\bnetsh\s+advfirewall\s+reset\b",       # reset firewall
    r"\bbcdedit\b",                            # boot config editor
    r"\bshutdown\s+-[srf]",                   # shutdown/restart
]
_BL = [re.compile(p, re.IGNORECASE) for p in _BLACKLIST]

# Shell metacharacters that enable command chaining / substitution.
# These are not auto-refused (legitimate commands use them) but are
# surfaced so the structured git-push / blacklist checks see through them.
_SHELL_OPERATORS = re.compile(r"[;&|]|\$\(|`|&&|\|\|")

MAX_OUTPUT = 50_000


def is_blacklisted(command: str) -> bool:
    return any(rx.search(command) for rx in _BL)


def _iter_subcommands(command: str) -> list[list[str]]:
    """Split a shell command into individual argv lists, best-effort.

    Splits on the common shell separators (``;``, ``&&``, ``||``, ``|``)
    and tokenises each segment with ``shlex`` so that structured checks
    (e.g. git push) can inspect the actual program + args rather than
    pattern-matching the raw string. Tokens that fail to parse (unbalanced
    quotes, etc.) are skipped — the raw-string blacklist still applies.
    """
    segments = re.split(r"&&|\|\||[;&|]", command)
    out: list[list[str]] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        try:
            tokens = shlex.split(seg)
        except ValueError:
            continue
        if tokens:
            out.append(tokens)
    return out


def _program_name(token: str) -> str:
    """Normalise an argv[0] to a bare program name (strip path)."""
    # Handle both / and \ separators; lower-case for case-insensitive match.
    base = re.split(r"[\\/]", token)[-1]
    return base.lower()


def is_git_push(command: str) -> bool:
    """True if any sub-command invokes ``git push``.

    Tokenises the command so that ``/usr/bin/git  push``, ``GIT push``
    chained after ``&&``, and extra whitespace are all detected, instead of
    relying on a single brittle regex over the raw string.
    """
    for tokens in _iter_subcommands(command):
        # Skip leading `VAR=value` environment assignments (e.g. GIT_EDITOR=vi git ...).
        i = 0
        while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
            i += 1
        if i >= len(tokens):
            continue
        if _program_name(tokens[i]) == "git":
            # First non-flag arg after `git` is the subcommand.
            for arg in tokens[i + 1:]:
                if arg.startswith("-"):
                    continue
                if arg == "push":
                    return True
                break  # a different git subcommand; check other segments
    return False


class ShellArgs(BaseModel):
    command: str
    timeout: int = Field(default=60, le=600)


class RunShell(Tool[ShellArgs]):
    """Execute a shell command. High risk: gated by blacklist + policy."""

    name = "run_shell"
    description = "执行 shell 命令(高风险,受黑名单与权限约束)"
    args_model = ShellArgs
    risk = Risk.HIGH

    def run(self, args: ShellArgs, ctx: ToolContext) -> ToolResult:
        if is_blacklisted(args.command):
            logger.warning("refused blacklisted command: %r", args.command)
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
        except OSError as e:
            logger.warning("shell command failed to start: %s", e)
            return ToolResult(ok=False, error=f"failed to run command: {e}")
        out = (proc.stdout + (("\n[stderr]\n" + proc.stderr) if proc.stderr else ""))[:MAX_OUTPUT]
        return ToolResult(
            ok=proc.returncode == 0,
            content=out,
            error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
            meta={"exit_code": proc.returncode},
        )
