from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel
from pycode_agent.core.messages import ToolResult
from .base import Tool, Risk, ToolContext

MEMORY_REL = ".pycode/memory.md"


class NoArgs(BaseModel):
    pass


class MemoryRead(Tool):
    name = "memory_read"
    description = "读取项目记忆 .pycode/memory.md"
    args_model = NoArgs
    risk = Risk.LOW

    def run(self, args: NoArgs, ctx: ToolContext) -> ToolResult:
        p = ctx.project_dir / MEMORY_REL
        if not p.is_file():
            return ToolResult(ok=True, content="(no project memory yet)")
        return ToolResult(ok=True, content=p.read_text(encoding="utf-8"))


class WriteArgs(BaseModel):
    content: str


class MemoryWrite(Tool):
    name = "memory_write"
    description = "写入项目记忆(高风险,需确认)"
    args_model = WriteArgs
    risk = Risk.HIGH

    def run(self, args: WriteArgs, ctx: ToolContext) -> ToolResult:
        p = ctx.project_dir / MEMORY_REL
        pm = ctx.patch_manager
        if pm is not None:
            pm.apply(p, args.content)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args.content, encoding="utf-8")
        return ToolResult(ok=True, content="memory updated")
