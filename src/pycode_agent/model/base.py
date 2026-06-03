from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from pydantic import BaseModel, Field

from pycode_agent.core.messages import Message, ToolCall


class LLMResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMProvider(ABC):
    """Abstract chat provider. Concrete subclasses set ``model`` and implement chat()."""

    #: Identifier of the underlying model (e.g. "gpt-4o"). Set by subclasses.
    model: str

    @abstractmethod
    def chat(self, *, messages: list[Message], tools: list[dict]) -> LLMResponse:
        """Single turn. tools is a list of JSON-schema tool specs."""
        ...

    def chat_stream(self, *, messages: list[Message], tools: list[dict]) -> Iterator:
        """Streaming turn. Yields StreamEvent objects.

        Default implementation falls back to chat() and emits a single
        TurnEnd or ToolCallStart+ToolCallEnd sequence.  Subclasses that
        support true SSE streaming should override this.
        """
        from pycode_agent.model.streaming import (
            ToolCallEnd,
            ToolCallStart,
            TurnEnd,
        )
        resp = self.chat(messages=messages, tools=tools)
        if resp.tool_calls:
            for tc in resp.tool_calls:
                yield ToolCallStart(id=tc.id, name=tc.name)
                yield ToolCallEnd(id=tc.id, name=tc.name, arguments=tc.arguments)
        else:
            yield TurnEnd(text=resp.text or "")
