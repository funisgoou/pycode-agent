from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pycode_agent.core.messages import Message

_TITLE_MAX = 50


@dataclass
class Session:
    """A persisted conversation: an id, a derived title, and its message log."""

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
    def from_dict(cls, data: dict) -> Session:
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


class SessionStore:
    """Atomic per-session JSON storage under a sessions directory."""

    def __init__(self, sessions_dir: Path):
        self.dir = Path(sessions_dir)

    def new_id(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]

    def new_session(self) -> Session:
        return Session(
            id=self.new_id(),
            title="(empty)",
            created_at=datetime.now().isoformat(timespec="seconds"),
            messages=[],
        )

    def _path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.json"

    def save(self, session: Session) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        target = self._path(session.id)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(session.to_dict(), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)

    def load(self, session_id: str) -> Session:
        p = self._path(session_id)
        if not p.is_file():
            raise KeyError(session_id)
        return Session.from_dict(json.loads(p.read_text(encoding="utf-8")))

    def latest(self) -> Session | None:
        files = list(self.dir.glob("*.json")) if self.dir.is_dir() else []
        if not files:
            return None
        newest = max(files, key=lambda p: p.stat().st_mtime)
        return Session.from_dict(json.loads(newest.read_text(encoding="utf-8")))

    def list_meta(self) -> list[dict]:
        out: list[dict] = []
        if not self.dir.is_dir():
            return out
        for p in self.dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                msgs = data.get("messages", [])
                turns = sum(1 for m in msgs if m.get("role") == "user")
                out.append({
                    "id": data.get("id", p.stem),
                    "mtime": p.stat().st_mtime,
                    "title": data.get("title", "(empty)"),
                    "turns": turns,
                })
            except (json.JSONDecodeError, OSError):
                continue
        out.sort(key=lambda m: m["mtime"], reverse=True)
        return out
