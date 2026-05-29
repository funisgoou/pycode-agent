from pathlib import Path
from pydantic import BaseModel
from pycode_agent.core.agent import Agent
from pycode_agent.core.messages import ToolCall, ToolResult
from pycode_agent.model.fake import FakeLLMProvider
from pycode_agent.model.base import LLMResponse
from pycode_agent.tools.base import Tool, Risk, ToolContext
from pycode_agent.tools.registry import ToolRegistry
from pycode_agent.security.policy import Policy
from pycode_agent.security.approval import Approval
from pycode_agent.utils.diff import PatchManager
from pycode_agent.logs.audit import AuditLog


class EchoArgs(BaseModel):
    text: str

class EchoTool(Tool):
    name = "echo"; description = "echo"; args_model = EchoArgs; risk = Risk.LOW
    def run(self, args, ctx): return ToolResult(ok=True, content=args.text.upper())

class DangerArgs(BaseModel):
    pass

class DangerTool(Tool):
    name = "danger"; description = "high risk"; args_model = DangerArgs; risk = Risk.HIGH
    def __init__(self): self.ran = False
    def run(self, args, ctx):
        self.ran = True
        return ToolResult(ok=True, content="did danger")


def _agent(tmp_path, script, *, tools, mode="confirm", auto_yes=True):
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    ctx = ToolContext(project_dir=tmp_path, patch_manager=PatchManager())
    return Agent(
        provider=FakeLLMProvider(script=script),
        registry=reg,
        policy=Policy(mode=mode),
        approval=Approval(auto_yes=auto_yes),
        audit=AuditLog(tmp_path / "audit.jsonl"),
        ctx=ctx,
        max_turns=8,
    )

def test_loop_runs_low_risk_tool_then_answers(tmp_path):
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "hi"})]),
        LLMResponse(text="final answer"),
    ]
    agent = _agent(tmp_path, script, tools=[EchoTool()])
    result = agent.run("please echo")
    assert result == "final answer"

def test_confirm_yes_runs_high_risk(tmp_path):
    danger = DangerTool()
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="danger", arguments={})]),
        LLMResponse(text="ok done"),
    ]
    agent = _agent(tmp_path, script, tools=[danger], auto_yes=True)
    agent.run("do danger")
    assert danger.ran is True

def test_confirm_no_skips_high_risk(tmp_path):
    danger = DangerTool()
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="danger", arguments={})]),
        LLMResponse(text="understood, skipped"),
    ]
    agent = _agent(tmp_path, script, tools=[danger], auto_yes=False)
    result = agent.run("do danger")
    assert danger.ran is False
    assert result == "understood, skipped"

def test_readonly_denies_high_risk(tmp_path):
    danger = DangerTool()
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="danger", arguments={})]),
        LLMResponse(text="cannot in readonly"),
    ]
    agent = _agent(tmp_path, script, tools=[danger], mode="readonly")
    agent.run("do danger")
    assert danger.ran is False

def test_max_turns_terminates(tmp_path):
    script = [LLMResponse(tool_calls=[ToolCall(id=f"c{i}", name="echo", arguments={"text": "x"})]) for i in range(20)]
    agent = _agent(tmp_path, script, tools=[EchoTool()])
    result = agent.run("loop")
    assert "max turns" in result.lower()

def test_audit_written(tmp_path):
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "hi"})]),
        LLMResponse(text="done"),
    ]
    agent = _agent(tmp_path, script, tools=[EchoTool()])
    agent.run("go")
    assert (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
