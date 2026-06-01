from __future__ import annotations
from pycode_agent.core.context_manager import ContextManager
from pycode_agent.core.messages import Message, ToolCall


def _cm(**kw):
    defaults = dict(budget=1000, ratio=0.8, keep_recent_turns=2)
    defaults.update(kw)
    return ContextManager(**defaults)


def test_estimate_tokens_counts_content():
    cm = _cm()
    msgs = [Message(role="user", content="a" * 400)]
    # 400 chars / 4 = 100
    assert cm.estimate_tokens(msgs) == 100


def test_estimate_tokens_includes_tool_call_args():
    cm = _cm()
    msgs = [Message(role="assistant", tool_calls=[
        ToolCall(id="1", name="read_file", arguments={"path": "x"})
    ])]
    assert cm.estimate_tokens(msgs) > 0


def test_estimate_tokens_handles_none_content():
    cm = _cm()
    msgs = [Message(role="assistant", content=None)]
    assert cm.estimate_tokens(msgs) == 0
