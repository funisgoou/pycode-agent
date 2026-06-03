from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from pycode_agent.core.messages import Message, ToolCall

if TYPE_CHECKING:
    from pycode_agent.core.messages import ToolResult
from pycode_agent.core.context_manager import ContextManager
from pycode_agent.logs.audit import AuditLog
from pycode_agent.model.base import LLMProvider
from pycode_agent.model.streaming import (
    StreamEvent,
    TextDelta,
    ToolCallEnd,
    ToolResultEvent,
    TurnEnd,
)
from pycode_agent.security.approval import Approval
from pycode_agent.security.policy import Decision, Policy
from pycode_agent.tools.base import ToolContext
from pycode_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are PyCodeAgent, a terminal coding assistant. "
    "Only use tools when the user's request requires reading, searching, or modifying code. "
    "For casual conversation (greetings, general questions), respond directly without tools. "
    "High-risk actions require user confirmation. Be concise."
)


class Agent:
    """Drives the LLM tool-use loop.

    Each ``run``/``run_stream`` call appends the user turn, then repeatedly
    asks the provider for the next step: plain text terminates the loop, while
    tool calls are gated through the :class:`Policy`/:class:`Approval` layer,
    dispatched, and fed back as tool messages. Bounded by ``max_turns`` and
    ``max_tool_calls``; optionally compacts context and persists the session.
    """

    def __init__(self, *, provider: LLMProvider, registry: ToolRegistry,
                 policy: Policy, approval: Approval, audit: AuditLog,
                 ctx: ToolContext, max_turns: int = 12, max_tool_calls: int = 40,
                 system_prefix: str = "", dry_run: bool = False,
                 context_manager: ContextManager | None = None,
                 session_sink: Callable[[list[Message]], None] | None = None):
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
        self.context_manager = context_manager
        self.session_sink = session_sink
        self.rejections = 0
        self._project_scanned = False
        self.messages: list[Message] = [
            Message(role="system", content=SYSTEM_PROMPT)
        ]

    def _ensure_project_profile(self) -> None:
        """Lazily scan project and inject profile into the system message.

        Only runs once, and only when the LLM actually calls a tool.
        Simple greetings skip this entirely.
        """
        if self._project_scanned:
            return
        self._project_scanned = True
        from pycode_agent.context.scanner import scan_project
        profile = scan_project(self.ctx.project_dir)
        if profile.tree:
            prefix = "Project profile:\n" + profile.summary()
            self.messages[0] = Message(
                role="system",
                content=SYSTEM_PROMPT + "\n\n" + prefix,
            )

    def _maybe_compact(self) -> None:
        cm = self.context_manager
        if cm is not None and cm.should_compact(self.messages):
            self.messages = cm.compact(self.messages, self.provider)

    def _persist(self) -> None:
        if self.session_sink is None:
            return
        try:
            self.session_sink(self.messages)
        except Exception:
            # persistence must never break the agent loop
            logger.warning("session persistence failed", exc_info=True)

    def run(self, user_input: str) -> str:
        """Run the loop to completion and return the assistant's final text."""
        self.messages.append(Message(role="user", content=user_input))
        tool_call_count = 0
        for _ in range(self.max_turns):
            self._maybe_compact()
            resp = self.provider.chat(messages=self.messages, tools=self.registry.schemas())
            if not resp.tool_calls:
                text = resp.text or ""
                self.messages.append(Message(role="assistant", content=text))
                self._persist()
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
            self._persist()
        return "Stopped: reached max turns without a final answer."

    def _handle_call(self, call: ToolCall):
        # First tool call ever → lazily scan project and enrich system prompt.
        self._ensure_project_profile()
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
                logger.debug("tool preview failed for %s", call.name, exc_info=True)
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
    def _render(result: ToolResult) -> str:
        if result.ok:
            return result.content
        return f"ERROR: {result.error}"

    def run_stream(self, user_input: str) -> Iterator[StreamEvent]:
        """Streaming variant of run(). Yields StreamEvent objects.

        Does NOT modify the existing run() method.  The caller consumes
        events via iteration; the final TurnEnd.text carries the answer.
        """
        self.messages.append(Message(role="user", content=user_input))
        tool_call_count = 0
        for _ in range(self.max_turns):
            self._maybe_compact()
            text_parts: list[str] = []
            completed_calls: list[ToolCall] = []
            got_turn_end = False
            turn_end_text: str | None = None

            for event in self.provider.chat_stream(
                messages=self.messages, tools=self.registry.schemas()
            ):
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                elif isinstance(event, ToolCallEnd):
                    completed_calls.append(
                        ToolCall(id=event.id, name=event.name, arguments=event.arguments)
                    )
                elif isinstance(event, TurnEnd):
                    got_turn_end = True
                    turn_end_text = event.text
                else:
                    # ToolCallStart — yield immediately
                    pass
                yield event

            if not completed_calls:
                # Final text answer
                text = "".join(text_parts) if text_parts else (turn_end_text or "")
                if not got_turn_end:
                    yield TurnEnd(text=text)
                elif turn_end_text is None:
                    # Provider emitted a TurnEnd with None text but we have TextDeltas
                    pass  # text was already printed via TextDeltas
                self.messages.append(Message(role="assistant", content=text))
                self._persist()
                return

            # Tool calls — append assistant message with tool_calls
            self.messages.append(Message(role="assistant", tool_calls=completed_calls))

            for call in completed_calls:
                tool_call_count += 1
                if tool_call_count > self.max_tool_calls:
                    yield TurnEnd(text="Stopped: reached max tool calls.")
                    return
                result = self._handle_call(call)
                yield ToolResultEvent(
                    tool_call_id=call.id,
                    ok=result.ok,
                    content=result.content,
                    error=result.error,
                )
                self.messages.append(
                    Message(role="tool", tool_call_id=call.id, content=self._render(result))
                )
            self._persist()

        yield TurnEnd(text="Stopped: reached max turns without a final answer.")
