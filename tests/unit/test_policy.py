from pycode_agent.tools.base import Risk
from pycode_agent.security.policy import Policy, Decision

def test_readonly_blocks_high_risk():
    p = Policy(mode="readonly")
    assert p.evaluate(Risk.LOW) == Decision.ALLOW
    assert p.evaluate(Risk.HIGH) == Decision.DENY

def test_confirm_requires_confirm_for_high():
    p = Policy(mode="confirm")
    assert p.evaluate(Risk.LOW) == Decision.ALLOW
    assert p.evaluate(Risk.HIGH) == Decision.CONFIRM

def test_workspace_allows_medium_confirms_high():
    p = Policy(mode="workspace")
    assert p.evaluate(Risk.MEDIUM) == Decision.ALLOW
    assert p.evaluate(Risk.HIGH) == Decision.CONFIRM

def test_dangerous_allows_all():
    p = Policy(mode="dangerous")
    assert p.evaluate(Risk.HIGH) == Decision.ALLOW
