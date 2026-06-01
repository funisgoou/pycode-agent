from __future__ import annotations
from pydantic import ValidationError
from pycode_agent.core.messages import ToolResult
from .base import Tool, ToolContext


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        return [t.json_schema() for t in self._tools.values()]

    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def dispatch(self, name: str, arguments: dict, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"unknown tool: {name}")
        try:
            args = tool.args_model.model_validate(arguments)
        except ValidationError as e:
            return ToolResult(ok=False, error=f"invalid arguments: {e}")
        try:
            return tool.run(args, ctx)
        except Exception as e:  # 工具异常不崩溃 Loop
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
