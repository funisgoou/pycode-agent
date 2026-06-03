from __future__ import annotations

from pydantic import BaseModel, Field


class StreamEvent(BaseModel):
    """Base class for all stream events emitted during an agent run."""
    type: str = "stream_event"


class TextDelta(StreamEvent):
    """A fragment of assistant text from the LLM stream."""
    type: str = "text_delta"
    text: str


class ToolCallStart(StreamEvent):
    """Beginning of a tool call (function name known, arguments pending)."""
    type: str = "tool_call_start"
    id: str
    name: str


class ToolCallEnd(StreamEvent):
    """A complete tool call with fully assembled arguments."""
    type: str = "tool_call_end"
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResultEvent(StreamEvent):
    """Result of executing a tool."""
    type: str = "tool_result"
    tool_call_id: str
    ok: bool
    content: str = ""
    error: str | None = None


class TurnEnd(StreamEvent):
    """The agent's final answer for this run."""
    type: str = "turn_end"
    text: str | None = None
