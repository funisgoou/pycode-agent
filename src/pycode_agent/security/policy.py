from __future__ import annotations
from enum import Enum
from pycode_agent.tools.base import Risk


class Decision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class Policy:
    def __init__(self, mode: str = "confirm"):
        self.mode = mode

    def evaluate(self, risk: Risk) -> Decision:
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
