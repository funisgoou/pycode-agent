from __future__ import annotations
import json
from pycode_agent.core.messages import Message
from pycode_agent.model.base import LLMProvider

_SUMMARY_SYSTEM = (
    "You are compressing an earlier portion of a coding-assistant conversation. "
    "Produce a concise summary that PRESERVES: key decisions made, files created or "
    "modified (with paths), tool results that matter, and any unresolved tasks. "
    "Omit pleasantries. Output plain text, no preamble."
)


class ContextManager:
    """Char-heuristic token budgeting + LLM-summary compaction.

    Token estimate is ~chars/4 (model-agnostic). When the running message
    list exceeds budget*ratio, the earliest messages (everything except the
    system message and the most recent keep_recent_turns turns) are summarized
    by the same provider into a single system "conversation summary" message.
    If the summary call fails, falls back to plain truncation.
    """

    def __init__(self, *, budget: int, ratio: float, keep_recent_turns: int):
        self.budget = budget
        self.ratio = ratio
        self.keep_recent_turns = keep_recent_turns

    def estimate_tokens(self, messages: list[Message]) -> int:
        chars = 0
        for m in messages:
            if m.content:
                chars += len(m.content)
            if m.tool_calls:
                for tc in m.tool_calls:
                    chars += len(tc.name) + len(json.dumps(tc.arguments))
        return chars // 4

    def should_compact(self, messages: list[Message]) -> bool:
        return self.estimate_tokens(messages) > int(self.budget * self.ratio)

    def compact(self, messages: list[Message], provider: LLMProvider) -> list[Message]:
        if not messages:
            return messages
        system = messages[0] if messages[0].role == "system" else None
        rest = messages[1:] if system is not None else messages
        keep = self.keep_recent_turns * 2
        if keep <= 0:
            split = len(rest)  # keep nothing recent; summarize all non-system
        else:
            if len(rest) <= keep:
                return messages  # nothing old enough to summarize
            split = len(rest) - keep
            # Never let the recent slice begin on a tool message whose parent
            # assistant (with tool_calls) would be summarized away. Advance the
            # boundary forward until recent[0] is not an orphaned tool message.
            while split < len(rest) and rest[split].role == "tool":
                split += 1
        if split >= len(rest):
            # keep==0 path, or everything advanced into 'old': recent is empty.
            old, recent = rest, []
        else:
            old, recent = rest[:split], rest[split:]
        if not old:
            return messages  # nothing to summarize after boundary adjustment

        transcript = "\n".join(
            f"{m.role}: {m.content}" for m in old if m.content
        )
        head: list[Message] = [system] if system is not None else []
        try:
            resp = provider.chat(
                messages=[
                    Message(role="system", content=_SUMMARY_SYSTEM),
                    Message(role="user", content=transcript),
                ],
                tools=[],
            )
            summary = resp.text or ""
            if summary:
                head.append(Message(
                    role="system",
                    content="Summary of earlier conversation:\n" + summary,
                ))
        except Exception:
            # Fall back to plain truncation: drop old messages entirely.
            pass
        return head + recent
