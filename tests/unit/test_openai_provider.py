import json
import httpx
from pycode_agent.core.messages import Message
from pycode_agent.model.openai_compatible import OpenAICompatibleProvider
from pycode_agent.model.errors import AuthError, RateLimitError

def _provider(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.test/v1")
    return OpenAICompatibleProvider(model="m", api_key="k", client=client)

def test_parses_text_response():
    def handler(req):
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hello"}}]
        })
    p = _provider(handler)
    r = p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert r.text == "hello" and r.tool_calls == []

def test_parses_tool_calls():
    def handler(req):
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "read_file", "arguments": json.dumps({"path": "a.py"})}}
            ]}}]
        })
    p = _provider(handler)
    r = p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert r.tool_calls[0].name == "read_file"
    assert r.tool_calls[0].arguments == {"path": "a.py"}

def test_auth_error_mapped():
    def handler(req):
        return httpx.Response(401, json={"error": "bad key"})
    p = _provider(handler)
    try:
        p.chat(messages=[Message(role="user", content="hi")], tools=[])
        assert False, "should have raised"
    except AuthError:
        pass

def test_rate_limit_mapped():
    def handler(req):
        return httpx.Response(429, json={"error": "slow down"})
    p = _provider(handler)
    try:
        p.chat(messages=[Message(role="user", content="hi")], tools=[])
        assert False
    except RateLimitError:
        pass
