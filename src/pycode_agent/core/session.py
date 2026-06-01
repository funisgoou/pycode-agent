from __future__ import annotations
from dataclasses import dataclass, field
from pycode_agent.core.messages import Message

_TITLE_MAX = 50


@dataclass
class Session:
    id: str
    title: str
    created_at: str
    messages: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "messages": [m.model_dump(exclude_none=True) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            id=data["id"],
            title=data.get("title", "(empty)"),
            created_at=data.get("created_at", ""),
            messages=[Message.model_validate(m) for m in data.get("messages", [])],
        )

    @staticmethod
    def make_title(messages: list[Message]) -> str:
        for m in messages:
            if m.role == "user" and m.content:
                first_line = m.content.replace("\n", " ").strip()
                return first_line[:_TITLE_MAX] if first_line else "(empty)"
        return "(empty)"
