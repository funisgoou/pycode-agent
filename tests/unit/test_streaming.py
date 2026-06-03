from __future__ import annotations

import pytest

from pycode_agent.core.messages import Message, ToolCall
from pycode_agent.model.base import LLMResponse
from pycode_agent.model.fake import FakeLLMProvider
from pycode_agent.model.streaming import (
    TextDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolResultEvent,
    TurnEnd,
)

# ---------------------------------------------------------------------------
# FakeLLMProvider.chat_stream (inherited default from LLMProvider)
# ---------------------------------------------------------------------------

class TestFakeProviderStream:
    def test_text_response_emits_turn_end(self):
        provider = FakeLLMProvider([LLMResponse(text="hello")])
        events = list(provider.chat_stream(
            messages=[Message(role="user", content="hi")], tools=[]
        ))
        assert len(events) == 1
        assert isinstance(events[0], TurnEnd)
        assert events[0].text == "hello"

    def test_tool_call_response_emits_start_and_end(self):
        provider = FakeLLMProvider([
            LLMResponse(tool_calls=[
                ToolCall(id="c1", name="read_file", arguments={"path": "a.py"}),
            ])
        ])
        events = list(provider.chat_stream(
            messages=[Message(role="user", content="read")], tools=[]
        ))
        assert len(events) == 2
        assert isinstance(events[0], ToolCallStart)
        assert events[0].name == "read_file"
        assert isinstance(events[1], ToolCallEnd)
        assert events[1].arguments == {"path": "a.py"}

    def test_multiple_tool_calls(self):
        provider = FakeLLMProvider([
            LLMResponse(tool_calls=[
                ToolCall(id="c1", name="read_file", arguments={"path": "a.py"}),
                ToolCall(id="c2", name="list_dir", arguments={"path": "."}),
            ])
        ])
        events = list(provider.chat_stream(
            messages=[Message(role="user", content="go")], tools=[]
        ))
        assert len(events) == 4
        types = [e.type for e in events]
        assert types == ["tool_call_start", "tool_call_end",
                         "tool_call_start", "tool_call_end"]


# ---------------------------------------------------------------------------
# Agent.run_stream
# ---------------------------------------------------------------------------

def _agent(tmp_path, script, tools=None, auto_yes=False, max_turns=12):
    """Build an Agent with FakeLLMProvider for testing."""
    from pycode_agent.core.agent import SYSTEM_PROMPT, Agent
    from pycode_agent.logs.audit import AuditLog
    from pycode_agent.security.approval import Approval
    from pycode_agent.security.policy import Policy
    from pycode_agent.tools.base import Risk, Tool, ToolContext
    from pycode_agent.tools.registry import ToolRegistry
    from pycode_agent.utils.diff import PatchManager

    provider = FakeLLMProvider(script)
    reg = ToolRegistry()
    for t in (tools or []):
        reg.register(t)
    pm = PatchManager()
    ctx = ToolContext(project_dir=tmp_path, settings=None, patch_manager=pm)
    return Agent(
        provider=provider,
        registry=reg,
        policy=Policy(mode="confirm"),
        approval=Approval(auto_yes=auto_yes, prompt_fn=lambda t, d="": "y",
                          out_fn=lambda t, d="": None),
        audit=AuditLog(tmp_path / ".pycode" / "audit.jsonl"),
        ctx=ctx,
        max_turns=max_turns,
    )


class _EchoTool:
    """A simple LOW-risk tool for testing."""
    from pydantic import BaseModel

    from pycode_agent.tools.base import Risk, Tool, ToolContext, ToolResult

    class _Args(__import__("pydantic").BaseModel):
        text: str = ""

    @property
    def name(self):
        return "echo"

    @property
    def description(self):
        return "echo"

    @property
    def args_model(self):
        return self._Args

    @property
    def risk(self):
        from pycode_agent.tools.base import Risk
        return Risk.LOW

    def run(self, args, ctx):
        from pycode_agent.tools.base import ToolResult
        return ToolResult(ok=True, content=args.text)

    def preview(self, args, ctx):
        return ""

    def json_schema(self):
        return self._Args.model_json_schema()


class TestAgentRunStream:
    def test_text_only_answer(self, tmp_path):
        agent = _agent(tmp_path, [LLMResponse(text="hello world")])
        events = list(agent.run_stream("say hi"))
        turn_ends = [e for e in events if isinstance(e, TurnEnd)]
        assert len(turn_ends) == 1
        assert turn_ends[0].text == "hello world"

    def test_tool_call_then_answer(self, tmp_path):
        script = [
            LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "hi"})]),
            LLMResponse(text="done"),
        ]
        agent = _agent(tmp_path, script, tools=[_EchoTool()])
        events = list(agent.run_stream("echo hi"))
        # Should have: ToolCallStart, ToolCallEnd, ToolResultEvent, TurnEnd
        types = [e.type for e in events]
        assert "tool_call_start" in types
        assert "tool_call_end" in types
        assert "tool_result" in types
        turn_ends = [e for e in events if isinstance(e, TurnEnd)]
        assert len(turn_ends) == 1
        assert turn_ends[0].text == "done"

    def test_max_turns_respected(self, tmp_path):
        # 4 tool-call responses, but max_turns=2
        script = [
            LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "a"})]),
            LLMResponse(tool_calls=[ToolCall(id="c2", name="echo", arguments={"text": "b"})]),
            LLMResponse(tool_calls=[ToolCall(id="c3", name="echo", arguments={"text": "c"})]),
            LLMResponse(text="final"),
        ]
        agent = _agent(tmp_path, script, tools=[_EchoTool()], max_turns=2)
        events = list(agent.run_stream("go"))
        turn_ends = [e for e in events if isinstance(e, TurnEnd)]
        assert len(turn_ends) == 1
        assert "max turns" in (turn_ends[0].text or "").lower()

    def test_messages_appended_correctly(self, tmp_path):
        agent = _agent(tmp_path, [LLMResponse(text="answer")])
        list(agent.run_stream("question"))
        # system + user + assistant
        assert len(agent.messages) == 3
        assert agent.messages[1].role == "user"
        assert agent.messages[2].role == "assistant"
        assert agent.messages[2].content == "answer"

    def test_tool_result_event_captures_ok(self, tmp_path):
        script = [
            LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "x"})]),
            LLMResponse(text="final"),
        ]
        agent = _agent(tmp_path, script, tools=[_EchoTool()])
        events = list(agent.run_stream("go"))
        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].ok is True
        assert result_events[0].content == "x"
