from __future__ import annotations
from pycode_agent.core.messages import Message
from pycode_agent.model.base import LLMProvider
from pycode_agent.tools.registry import ToolRegistry
from pycode_agent.tools.base import ToolContext
from pycode_agent.security.policy import Policy, Decision
from pycode_agent.security.approval import Approval
from pycode_agent.logs.audit import AuditLog

SYSTEM_PROMPT = (
    "You are PyCodeAgent, a terminal coding assistant. "
    "Use the provided tools to read, search, and modify the project. "
    "High-risk actions require user confirmation. Be concise."
)


class Agent:
    def __init__(self, *, provider: LLMProvider, registry: ToolRegistry,
                 policy: Policy, approval: Approval, audit: AuditLog,
                 ctx: ToolContext, max_turns: int = 12, max_tool_calls: int = 40,
                 system_prefix: str = "", dry_run: bool = False):
        self.provider = provider
        self.registry = registry
        self.policy = policy
        self.approval = approval
        self.audit = audit
        self.ctx = ctx
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.system_prefix = system_prefix
        self.dry_run = dry_run
        self.rejections = 0
        self.messages: list[Message] = [
            Message(role="system", content=SYSTEM_PROMPT + ("\n\n" + system_prefix if system_prefix else ""))
        ]

    def run(self, user_input: str) -> str:
        self.messages.append(Message(role="user", content=user_input))
        tool_call_count = 0
        for _ in range(self.max_turns):
            resp = self.provider.chat(messages=self.messages, tools=self.registry.schemas())
            if not resp.tool_calls:
                text = resp.text or ""
                self.messages.append(Message(role="assistant", content=text))
                return text
            self.messages.append(Message(role="assistant", tool_calls=resp.tool_calls))
            for call in resp.tool_calls:
                tool_call_count += 1
                result = self._handle_call(call)
                self.messages.append(
                    Message(role="tool", tool_call_id=call.id, content=self._render(result))
                )
                if tool_call_count >= self.max_tool_calls:
                    return "Stopped: reached max tool calls."
        return "Stopped: reached max turns without a final answer."

    def _handle_call(self, call):
        tool = self.registry.get(call.name)
        if tool is None:
            from pycode_agent.core.messages import ToolResult
            res = ToolResult(ok=False, error=f"unknown tool: {call.name}")
            self.audit.record(event="tool_call", tool=call.name, arguments=call.arguments,
                              decision="deny", ok=False, error=res.error)
            return res
        decision = self.policy.evaluate(tool.risk)
        if decision == Decision.DENY:
            from pycode_agent.core.messages import ToolResult
            res = ToolResult(ok=False, error="denied by permission policy")
        elif decision == Decision.CONFIRM:
            detail = str(call.arguments)
            preview = ""
            try:
                parsed = tool.args_model.model_validate(call.arguments)
                preview = tool.preview(parsed, self.ctx)
                if preview:
                    detail = preview
            except Exception:
                pass
            if self.dry_run:
                from pycode_agent.core.messages import ToolResult
                res = ToolResult(ok=True, content=f"[dry-run] would run {call.name}; not executed.\n{preview}".rstrip())
            else:
                approved = self.approval.ask(f"运行工具 {call.name}", detail)
                if not approved:
                    from pycode_agent.core.messages import ToolResult
                    self.rejections += 1
                    res = ToolResult(ok=False, error="user rejected")
                else:
                    res = self.registry.dispatch(call.name, call.arguments, self.ctx)
        else:
            res = self.registry.dispatch(call.name, call.arguments, self.ctx)
        self.audit.record(event="tool_call", tool=call.name, arguments=call.arguments,
                          decision=decision.value, ok=res.ok, error=res.error)
        return res

    @staticmethod
    def _render(result) -> str:
        if result.ok:
            return result.content
        return f"ERROR: {result.error}"
