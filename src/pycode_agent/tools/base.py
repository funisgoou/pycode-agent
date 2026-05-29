from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from pydantic import BaseModel
from pycode_agent.core.messages import ToolResult


class Risk(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


@dataclass
class ToolContext:
    project_dir: Path
    settings: object | None = None
    patch_manager: object | None = None
    extra: dict = field(default_factory=dict)


class Tool(ABC):
    name: str
    description: str
    args_model: type[BaseModel]
    risk: Risk

    @abstractmethod
    def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...

    def json_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }
