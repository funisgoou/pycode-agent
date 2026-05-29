from __future__ import annotations
import json
import time
import httpx
from typing import Callable
from pycode_agent.core.messages import Message, ToolCall
from .base import LLMProvider, LLMResponse
from .errors import (
    AuthError, RateLimitError, TimeoutError, NetworkError, ProviderError,
)


def _message_to_dict(m: Message) -> dict:
    d: dict = {"role": m.role}
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
                 sleep_fn: Callable[[float], None] = time.sleep):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep_fn

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
            resp = self._client.post("/chat/completions", json=payload, headers=headers)
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

        msg = resp.json()["choices"][0]["message"]
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc["function"]
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn["name"], arguments=arguments))
        return LLMResponse(text=msg.get("content"), tool_calls=tool_calls)
