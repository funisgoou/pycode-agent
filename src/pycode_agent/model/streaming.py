from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field


class TextDelta(BaseModel):
    """A fragment of assistant text from the LLM stream."""
    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolCallStart(BaseModel):
    """Beginning of a tool call (function name known, arguments pending)."""
    type: Literal["tool_call_start"] = "tool_call_start"
    id: str
    name: str


class ToolCallEnd(BaseModel):
    """A complete tool call with fully assembled arguments."""
    type: Literal["tool_call_end"] = "tool_call_end"
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResultEvent(BaseModel):
    """Result of executing a tool."""
    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    ok: bool
    content: str = ""
    error: str | None = None
    meta: dict = Field(default_factory=dict)


class TurnEnd(BaseModel):
    """The agent's final answer for this run."""
    type: Literal["turn_end"] = "turn_end"
    text: str | None = None


class UsageEvent(BaseModel):
    """Token usage info from the API (emitted once per streaming turn)."""
    type: Literal["usage"] = "usage"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# Discriminated union: callers can match on ``type`` for type-safe dispatch.
StreamEvent = Union[TextDelta, ToolCallStart, ToolCallEnd, ToolResultEvent, TurnEnd, UsageEvent]
