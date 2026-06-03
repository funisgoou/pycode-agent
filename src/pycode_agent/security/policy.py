from __future__ import annotations

from enum import Enum
from typing import Literal, get_args

from pycode_agent.tools.base import Risk

PolicyMode = Literal["readonly", "confirm", "workspace", "dangerous"]
_VALID_MODES = frozenset(get_args(PolicyMode))


class Decision(str, Enum):
    """Outcome of evaluating a tool's risk against the active policy."""

    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class Policy:
    """Maps a tool's :class:`Risk` to an allow/confirm/deny :class:`Decision`.

    Four modes: ``readonly`` (only LOW-risk allowed), ``confirm`` (LOW auto,
    rest needs confirmation), ``workspace`` (LOW/MEDIUM auto, HIGH confirms),
    and ``dangerous`` (everything auto-allowed). An unknown mode raises
    ``ValueError`` rather than silently falling back.
    """

    def __init__(self, mode: PolicyMode = "confirm"):
        if mode not in _VALID_MODES:
            raise ValueError(
                f"invalid policy mode: {mode!r} (expected one of {sorted(_VALID_MODES)})"
            )
        self.mode = mode

    def evaluate(self, risk: Risk) -> Decision:
        """Return the access Decision for a tool of the given risk tier."""
        if self.mode == "dangerous":
            return Decision.ALLOW
        if self.mode == "readonly":
            return Decision.ALLOW if risk == Risk.LOW else Decision.DENY
        if self.mode == "workspace":
            if risk <= Risk.MEDIUM:
                return Decision.ALLOW
            return Decision.CONFIRM
        # confirm (default)
        return Decision.ALLOW if risk == Risk.LOW else Decision.CONFIRM
