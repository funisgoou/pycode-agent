from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

from pycode_agent.core.messages import ToolResult

if TYPE_CHECKING:
    from pycode_agent.config.settings import Settings
    from pycode_agent.utils.diff import PatchManager

ArgsT = TypeVar("ArgsT", bound=BaseModel)


class Risk(IntEnum):
    """Risk tier of a tool, used by the permission policy to decide gating."""

    LOW = 0
    MEDIUM = 1
    HIGH = 2


class NoArgs(BaseModel):
    """Empty argument model for tools that take no parameters."""


@dataclass
class ToolContext:
    """Shared execution context passed to every tool's ``run``/``preview``."""

    project_dir: Path
    settings: Settings | None = None
    patch_manager: PatchManager | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Tool(ABC, Generic[ArgsT]):
    """Base class for all tools: a name, an args schema, a risk tier, and run().

    Generic over the tool's pydantic argument model so subclasses can declare
    concrete ``run``/``preview`` parameter types without violating LSP.
    """

    name: str
    description: str
    args_model: type[ArgsT]
    risk: Risk

    @abstractmethod
    def run(self, args: ArgsT, ctx: ToolContext) -> ToolResult: ...

    def json_schema(self) -> dict:
        """OpenAI-style function schema derived from ``args_model``."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    def preview(self, args: ArgsT, ctx: ToolContext) -> str:
        """Human-readable preview shown at confirmation time. Default: none."""
        return ""
