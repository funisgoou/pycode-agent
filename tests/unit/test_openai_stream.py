from __future__ import annotations

import json

import httpx
import pytest

from pycode_agent.core.messages import Message
from pycode_agent.model.errors import AuthError, RateLimitError
from pycode_agent.model.openai_compatible import OpenAICompatibleProvider
from pycode_agent.model.streaming import TextDelta, ToolCallEnd, ToolCallStart, TurnEnd


def _sse_body(chunks: list[dict], final_done: bool = True) -> bytes:
    """Build an SSE response body from a list of chunk dicts."""
    lines = []
    for chunk in chunks:
        lines.append(f"data: {json.dumps(chunk)}")
    if final_done:
        lines.append("data: [DONE]")
    return "\n".join(lines).encode()


def _text_chunk(content: str, index: int = 0) -> dict:
    return {
        "choices": [{
            "index": index,
            "delta": {"role": "assistant", "content": content},
            "finish_reason": None,
        }]
    }


def _tool_call_start_chunk(tc_id: str, name: str, index: int = 0) -> dict:
    return {
        "choices": [{
            "index": 0,
            "delta": {
                "tool_calls": [{
                    "index": index,
                    "id": tc_id,
                    "type": "function",
                    "function": {"name": name, "arguments": ""},
                }]
            },
            "finish_reason": None,
        }]
    }


def _tool_call_delta_chunk(arguments: str, index: int = 0) -> dict:
    return {
        "choices": [{
            "index": 0,
            "delta": {
                "tool_calls": [{
                    "index": index,
                    "function": {"arguments": arguments},
                }]
            },
            "finish_reason": None,
        }]
    }


class TestOpenAIStream:
    def test_text_stream_produces_text_deltas(self):
        body = _sse_body([
            _text_chunk("hello "),
            _text_chunk("world"),
        ])
        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=body))
        client = httpx.Client(transport=transport, base_url="http://test/v1")
        provider = OpenAICompatibleProvider(
            model="test", api_key="k", client=client, stream=True,
        )
        events = list(provider.chat_stream(
            messages=[Message(role="user", content="hi")], tools=[]
        ))
        deltas = [e for e in events if isinstance(e, TextDelta)]
        assert len(deltas) == 2
        assert deltas[0].text == "hello "
        assert deltas[1].text == "world"
        turn_ends = [e for e in events if isinstance(e, TurnEnd)]
        assert len(turn_ends) == 1

    def test_tool_call_stream_assembles_arguments(self):
        body = _sse_body([
            _tool_call_start_chunk("c1", "read_file", index=0),
            _tool_call_delta_chunk('{"pa', index=0),
            _tool_call_delta_chunk('th": "a.py"}', index=0),
        ])
        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=body))
        client = httpx.Client(transport=transport, base_url="http://test/v1")
        provider = OpenAICompatibleProvider(
            model="test", api_key="k", client=client, stream=True,
        )
        events = list(provider.chat_stream(
            messages=[Message(role="user", content="read")], tools=[]
        ))
        starts = [e for e in events if isinstance(e, ToolCallStart)]
        ends = [e for e in events if isinstance(e, ToolCallEnd)]
        assert len(starts) == 1
        assert starts[0].name == "read_file"
        assert len(ends) == 1
        assert ends[0].arguments == {"path": "a.py"}

    def test_auth_error_during_stream(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(401, content=b"unauthorized")
        )
        client = httpx.Client(transport=transport, base_url="http://test/v1")
        provider = OpenAICompatibleProvider(
            model="test", api_key="k", client=client, stream=True,
            max_retries=0,
        )
        with pytest.raises(AuthError):
            list(provider.chat_stream(
                messages=[Message(role="user", content="hi")], tools=[]
            ))

    def test_rate_limit_during_stream(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(429, content=b"slow down")
        )
        client = httpx.Client(transport=transport, base_url="http://test/v1")
        provider = OpenAICompatibleProvider(
            model="test", api_key="k", client=client, stream=True,
            max_retries=0, sleep_fn=lambda s: None,
        )
        with pytest.raises(RateLimitError):
            list(provider.chat_stream(
                messages=[Message(role="user", content="hi")], tools=[]
            ))

    def test_stream_false_falls_back_to_chat(self):
        """When stream=False, chat_stream should use fallback (non-streaming)."""
        body = json.dumps({
            "choices": [{"message": {"content": "hi back", "tool_calls": None}}]
        }).encode()
        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=body))
        client = httpx.Client(transport=transport, base_url="http://test/v1")
        provider = OpenAICompatibleProvider(
            model="test", api_key="k", client=client, stream=False,
        )
        events = list(provider.chat_stream(
            messages=[Message(role="user", content="hi")], tools=[]
        ))
        turn_ends = [e for e in events if isinstance(e, TurnEnd)]
        assert len(turn_ends) == 1
        assert turn_ends[0].text == "hi back"
