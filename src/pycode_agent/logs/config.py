from __future__ import annotations

import logging
import os

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_configured = False


def setup_logging(level: int | str | None = None) -> None:
    """Configure root logging for the pycode_agent package, once.

    Level resolution order: explicit *level* arg, then the ``PYCODE_LOG_LEVEL``
    env var (e.g. ``DEBUG``), defaulting to ``WARNING`` so a normal run stays
    quiet. Logs go to stderr to avoid corrupting tool/stdout output.
    """
    global _configured
    if _configured:
        return
    if level is None:
        level = os.environ.get("PYCODE_LOG_LEVEL", "WARNING")
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())
    logging.basicConfig(level=level, format=_DEFAULT_FORMAT)
    _configured = True
