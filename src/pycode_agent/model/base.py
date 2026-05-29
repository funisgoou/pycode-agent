from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from pycode_agent.core.messages import Message, ToolCall


class LLMResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, *, messages: list[Message], tools: list[dict]) -> LLMResponse:
        """Single turn. tools is a list of JSON-schema tool specs."""
        ...
