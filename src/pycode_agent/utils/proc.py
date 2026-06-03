from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ProcResult:
    """Outcome of a subprocess run.

    Exactly one failure mode is signalled via ``error`` (the program was
    missing or timed out); otherwise ``error`` is ``None`` and ``returncode``
    reflects the process exit status.
    """

    ok: bool
    returncode: int
    stdout: str
    stderr: str
    error: str | None = None


def run_command(
    cmd: list[str] | str,
    *,
    cwd: str | Path | None = None,
    timeout: int = 30,
    shell: bool = False,
) -> ProcResult:
    """Run a subprocess, capturing output and normalising the common failures.

    Translates ``FileNotFoundError`` (program missing) and
    ``TimeoutExpired`` into a ``ProcResult`` with ``ok=False`` and a populated
    ``error`` field, instead of letting them propagate. Callers that need the
    raw exit code inspect ``returncode``.
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
        )
    except FileNotFoundError as e:
        return ProcResult(ok=False, returncode=-1, stdout="", stderr="", error=str(e))
    except subprocess.TimeoutExpired:
        return ProcResult(ok=False, returncode=-1, stdout="", stderr="", error="timed out")
    except OSError as e:
        logger.warning("subprocess failed to start: %s", e)
        return ProcResult(ok=False, returncode=-1, stdout="", stderr="", error=str(e))
    return ProcResult(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
