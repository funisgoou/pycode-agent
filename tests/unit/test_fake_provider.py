from pycode_agent.core.messages import Message, ToolCall
from pycode_agent.model.fake import FakeLLMProvider
from pycode_agent.model.base import LLMResponse

def test_fake_returns_scripted_text():
    p = FakeLLMProvider(script=[LLMResponse(text="hello")])
    r = p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert r.text == "hello"
    assert r.tool_calls == []

def test_fake_returns_scripted_tool_calls_then_text():
    p = FakeLLMProvider(script=[
        LLMResponse(tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "a.py"})]),
        LLMResponse(text="done"),
    ])
    msgs = [Message(role="user", content="read a.py")]
    r1 = p.chat(messages=msgs, tools=[])
    assert r1.tool_calls[0].name == "read_file"
    r2 = p.chat(messages=msgs, tools=[])
    assert r2.text == "done"

def test_fake_exhausted_raises():
    import pytest
    p = FakeLLMProvider(script=[LLMResponse(text="only")])
    p.chat(messages=[], tools=[])
    with pytest.raises(IndexError):
        p.chat(messages=[], tools=[])
