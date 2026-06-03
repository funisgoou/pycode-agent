from __future__ import annotations

import json
from pathlib import Path


class AuditLog:
    """Append-only JSONL record of tool calls and their permission decisions."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, **fields) -> None:
        """Append one event as a JSON line."""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fields, ensure_ascii=False) + "\n")
