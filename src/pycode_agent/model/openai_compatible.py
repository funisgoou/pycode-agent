from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator

import httpx

from pycode_agent.core.messages import Message, ToolCall

from .base import LLMProvider, LLMResponse
from .errors import (
    AuthError,
    NetworkError,
    ProviderError,
    RateLimitError,
    TimeoutError,
)
from .streaming import TextDelta, ToolCallEnd, ToolCallStart, TurnEnd


def _message_to_dict(m: Message) -> dict:
    d: dict = {"role": m.role}
    # Omit a null content when the message instead carries tool calls — some
    # strict OpenAI-compatible backends reject `content: null`.
    if m.content is not None or not m.tool_calls:
        d["content"] = m.content
    if m.tool_calls:
        d["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
            for tc in m.tool_calls
        ]
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d


class OpenAICompatibleProvider(LLMProvider):
    # Errors worth retrying with exponential backoff (transient).
    _RETRYABLE = (RateLimitError, NetworkError, TimeoutError)

    def __init__(self, *, model: str, api_key: str | None, base_url: str = "",
                 timeout: int = 120, client: httpx.Client | None = None,
                 max_retries: int = 3, backoff_base: float = 0.5,
                 sleep_fn: Callable[[float], None] = time.sleep,
                 stream: bool = True):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep_fn
        self._stream = stream
        self._endpoint = self._resolve_endpoint()

    def _resolve_endpoint(self) -> str:
        """Build the absolute chat-completions URL.

        Accepts a base_url that either already ends in /chat/completions
        or points at the API root (e.g. .../v1). Avoids httpx relative-join
        surprises by always posting an absolute URL.
        """
        base = str(self._client.base_url).rstrip("/")
        if not base:
            return "/chat/completions"
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def chat(self, *, messages: list[Message], tools: list[dict]) -> LLMResponse:
        attempt = 0
        while True:
            try:
                return self._chat_once(messages=messages, tools=tools)
            except self._RETRYABLE:
                if attempt >= self.max_retries:
                    raise
                # exponential backoff: base * 2**attempt
                self._sleep(self.backoff_base * (2 ** attempt))
                attempt += 1

    def _chat_once(self, *, messages: list[Message], tools: list[dict]) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [_message_to_dict(m) for m in messages],
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            resp = self._client.post(self._endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise TimeoutError(str(e)) from e
        except httpx.HTTPError as e:
            raise NetworkError(str(e)) from e

        if resp.status_code == 401:
            raise AuthError("authentication failed")
        if resp.status_code == 429:
            raise RateLimitError("rate limited")
        if resp.status_code >= 400:
            raise ProviderError(f"http {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError(f"invalid JSON in response: {resp.text[:200]}") from e
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"unexpected response shape: {str(data)[:200]}") from e
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc["function"]
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn["name"], arguments=arguments))
        return LLMResponse(text=msg.get("content"), tool_calls=tool_calls)

    def chat_stream(self, *, messages: list[Message], tools: list[dict]) -> Iterator:
        """Streaming turn using SSE. Yields StreamEvent objects."""
        if not self._stream:
            yield from super().chat_stream(messages=messages, tools=tools)
            return

        payload: dict = {
            "model": self.model,
            "messages": [_message_to_dict(m) for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        attempt = 0
        while True:
            try:
                yield from self._stream_once(payload, headers)
                return
            except self._RETRYABLE:
                if attempt >= self.max_retries:
                    raise
                self._sleep(self.backoff_base * (2 ** attempt))
                attempt += 1

    def _stream_once(self, payload: dict, headers: dict) -> Iterator:
        """Execute one streaming request, yielding StreamEvent objects."""
        try:
            with self._client.stream("POST", self._endpoint, json=payload, headers=headers) as resp:
                if resp.status_code == 401:
                    resp.read()
                    raise AuthError("authentication failed")
                if resp.status_code == 429:
                    resp.read()
                    raise RateLimitError("rate limited")
                if resp.status_code >= 400:
                    resp.read()
                    raise ProviderError(f"http {resp.status_code}: {resp.text[:200]}")

                # Accumulate tool call deltas across chunks.
                # Keyed by tool call index: {index: {id, name, arguments_str}}
                tc_accum: dict[int, dict] = {}
                has_tool_calls = False

                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}

                    # Text content delta
                    content = delta.get("content")
                    if content:
                        yield TextDelta(text=content)

                    # Tool call deltas
                    for tc_delta in delta.get("tool_calls") or []:
                        has_tool_calls = True
                        idx = tc_delta.get("index", 0)
                        if idx not in tc_accum:
                            tc_accum[idx] = {"id": "", "name": "", "arguments": ""}
                        entry = tc_accum[idx]
                        fn = tc_delta.get("function") or {}
                        if tc_delta.get("id"):
                            entry["id"] = tc_delta["id"]
                        if fn.get("name"):
                            entry["name"] = fn["name"]
                        if fn.get("arguments"):
                            entry["arguments"] += fn["arguments"]

                # Emit completed tool call events
                for idx in sorted(tc_accum):
                    entry = tc_accum[idx]
                    yield ToolCallStart(id=entry["id"], name=entry["name"])
                    try:
                        args = json.loads(entry["arguments"]) if entry["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    yield ToolCallEnd(id=entry["id"], name=entry["name"], arguments=args)

                if not has_tool_calls:
                    yield TurnEnd(text=None)

        except httpx.TimeoutException as e:
            raise TimeoutError(str(e)) from e
        except httpx.HTTPError as e:
            raise NetworkError(str(e)) from e
