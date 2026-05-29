import json
import httpx
from pycode_agent.core.messages import Message
from pycode_agent.model.openai_compatible import OpenAICompatibleProvider
from pycode_agent.model.errors import AuthError, RateLimitError, NetworkError

def _provider(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.test/v1")
    kwargs.setdefault("sleep_fn", lambda s: None)  # no real sleeping in tests
    return OpenAICompatibleProvider(model="m", api_key="k", client=client, **kwargs)

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
    p = _provider(handler, max_retries=0)
    try:
        p.chat(messages=[Message(role="user", content="hi")], tools=[])
        assert False
    except RateLimitError:
        pass


def test_retries_then_succeeds_on_429():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "slow down"})
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}]
        })
    slept = []
    p = _provider(handler, max_retries=3, sleep_fn=slept.append)
    r = p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert r.text == "ok"
    assert calls["n"] == 3          # 2 failures + 1 success
    assert len(slept) == 2          # backoff slept twice
    assert slept[0] < slept[1]      # exponential growth


def test_retries_exhausted_raises_rate_limit():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, json={"error": "slow down"})
    p = _provider(handler, max_retries=2, sleep_fn=lambda s: None)
    try:
        p.chat(messages=[Message(role="user", content="hi")], tools=[])
        assert False
    except RateLimitError:
        pass
    assert calls["n"] == 3          # initial + 2 retries


def test_auth_error_not_retried():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})
    p = _provider(handler, max_retries=5, sleep_fn=lambda s: None)
    try:
        p.chat(messages=[Message(role="user", content="hi")], tools=[])
        assert False
    except AuthError:
        pass
    assert calls["n"] == 1          # no retries on auth failure


def test_network_error_retried_then_raises():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        raise httpx.ConnectError("boom")
    p = _provider(handler, max_retries=2, sleep_fn=lambda s: None)
    try:
        p.chat(messages=[Message(role="user", content="hi")], tools=[])
        assert False
    except NetworkError:
        pass
    assert calls["n"] == 3


def _capture_url_provider(base_url):
    seen = {}
    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}]
        })
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url=base_url)
    p = OpenAICompatibleProvider(model="m", api_key="k", client=client,
                                 sleep_fn=lambda s: None)
    return p, seen


def test_base_url_without_path_appends_endpoint():
    p, seen = _capture_url_provider("https://api.test/v1")
    p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert seen["url"] == "https://api.test/v1/chat/completions"


def test_base_url_with_full_endpoint_not_duplicated():
    # user configured the full endpoint including /chat/completions
    p, seen = _capture_url_provider("https://api.test/v1/chat/completions")
    p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert seen["url"] == "https://api.test/v1/chat/completions"


def test_base_url_with_trailing_slash():
    p, seen = _capture_url_provider("https://api.test/v1/")
    p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert seen["url"] == "https://api.test/v1/chat/completions"
