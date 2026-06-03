from pycode_agent.core.messages import Message, ToolCall, ToolResult


def test_toolcall_roundtrip():
    tc = ToolCall(id="c1", name="read_file", arguments={"path": "a.py"})
    assert tc.name == "read_file"
    assert tc.arguments["path"] == "a.py"

def test_tool_message_carries_call_id():
    m = Message(role="tool", content="ok", tool_call_id="c1")
    assert m.role == "tool"
    assert m.tool_call_id == "c1"

def test_toolresult_defaults():
    r = ToolResult(ok=True, content="done")
    assert r.error is None
    assert r.meta == {}
