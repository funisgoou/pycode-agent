from __future__ import annotations
from pycode_agent.core.messages import Message
from .base import LLMProvider, LLMResponse


class FakeLLMProvider(LLMProvider):
    """Deterministic provider driven by a scripted list of responses."""

    def __init__(self, script: list[LLMResponse], *, model: str = "fake"):
        self.model = model
        self._script = list(script)
        self._i = 0
        self.calls: list[list[Message]] = []

    def chat(self, *, messages: list[Message], tools: list[dict]) -> LLMResponse:
        self.calls.append(list(messages))
        resp = self._script[self._i]  # raises IndexError when exhausted
        self._i += 1
        return resp
