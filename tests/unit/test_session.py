from __future__ import annotations
from pycode_agent.core.session import Session
from pycode_agent.core.messages import Message, ToolCall


def test_session_roundtrip_preserves_messages():
    msgs = [
        Message(role="system", content="SYS"),
        Message(role="user", content="hi"),
        Message(role="assistant", tool_calls=[ToolCall(id="t1", name="read_file", arguments={"path": "x"})]),
        Message(role="tool", tool_call_id="t1", content="data"),
        Message(role="assistant", content="done"),
    ]
    s = Session(id="s1", title="t", created_at="2026-06-01T00:00:00", messages=msgs)
    data = s.to_dict()
    s2 = Session.from_dict(data)
    assert s2.id == "s1"
    assert s2.title == "t"
    assert [m.role for m in s2.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert s2.messages[2].tool_calls[0].name == "read_file"
    assert s2.messages[3].tool_call_id == "t1"


def test_make_title_from_first_user_message():
    msgs = [Message(role="system", content="S"), Message(role="user", content="explain the project structure")]
    assert Session.make_title(msgs) == "explain the project structure"


def test_make_title_truncates_to_50_chars_and_strips_newlines():
    long = "a" * 80
    msgs = [Message(role="user", content="line1\n" + long)]
    title = Session.make_title(msgs)
    assert "\n" not in title
    assert len(title) <= 50


def test_make_title_empty_when_no_user_message():
    msgs = [Message(role="system", content="S")]
    assert Session.make_title(msgs) == "(empty)"
