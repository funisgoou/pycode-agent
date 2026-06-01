from __future__ import annotations
from pycode_agent.core.context_manager import ContextManager
from pycode_agent.core.messages import Message, ToolCall
from pycode_agent.model.base import LLMProvider, LLMResponse


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


def test_should_compact_below_threshold():
    cm = _cm(budget=1000, ratio=0.8)
    # 2000 chars => 500 tokens; threshold = 800 => no compaction
    msgs = [Message(role="user", content="a" * 2000)]
    assert cm.should_compact(msgs) is False


def test_should_compact_above_threshold():
    cm = _cm(budget=1000, ratio=0.8)
    # 4000 chars => 1000 tokens; threshold = 800 => compact
    msgs = [Message(role="user", content="a" * 4000)]
    assert cm.should_compact(msgs) is True


class _FakeProvider(LLMProvider):
    def __init__(self, summary="SUMMARY", fail=False):
        self.model = "fake"
        self._summary = summary
        self._fail = fail
        self.calls = 0

    def chat(self, *, messages, tools):
        self.calls += 1
        if self._fail:
            raise RuntimeError("boom")
        return LLMResponse(text=self._summary)


def _conversation(n_old=6):
    msgs = [Message(role="system", content="SYS")]
    for i in range(n_old):
        msgs.append(Message(role="user", content=f"old user {i}"))
        msgs.append(Message(role="assistant", content=f"old asst {i}"))
    return msgs


def test_compact_keeps_system_and_recent_turns():
    cm = _cm(keep_recent_turns=2)
    msgs = _conversation(n_old=6)  # 1 system + 12 msgs
    provider = _FakeProvider(summary="COMPRESSED")
    out = cm.compact(msgs, provider)
    assert out[0].role == "system" and out[0].content == "SYS"
    assert out[1].role == "system"
    assert "COMPRESSED" in out[1].content
    assert out[-1].content == "old asst 5"
    assert out[-4].content == "old user 4"
    assert provider.calls == 1


def test_compact_falls_back_to_truncation_on_error():
    cm = _cm(keep_recent_turns=2)
    msgs = _conversation(n_old=6)
    provider = _FakeProvider(fail=True)
    out = cm.compact(msgs, provider)
    assert out[0].content == "SYS"
    assert all("old user 0" not in (m.content or "") for m in out)
    assert out[-1].content == "old asst 5"
    assert len(out) == 1 + 4  # system + keep_recent_turns*2


def test_compact_noop_when_nothing_to_summarize():
    cm = _cm(keep_recent_turns=10)
    msgs = _conversation(n_old=2)  # fewer than keep_recent_turns
    provider = _FakeProvider()
    out = cm.compact(msgs, provider)
    assert out == msgs
    assert provider.calls == 0
