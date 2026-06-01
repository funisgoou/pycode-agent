from pydantic import BaseModel
from pycode_agent.tools.base import Tool, Risk, ToolContext
from pycode_agent.tools.registry import ToolRegistry
from pycode_agent.core.messages import ToolResult

class EchoArgs(BaseModel):
    text: str

class EchoTool(Tool):
    name = "echo"
    description = "echo back"
    args_model = EchoArgs
    risk = Risk.LOW
    def run(self, args: EchoArgs, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, content=args.text)

def test_register_and_schema():
    reg = ToolRegistry()
    reg.register(EchoTool())
    schemas = reg.schemas()
    assert schemas[0]["function"]["name"] == "echo"
    assert "text" in schemas[0]["function"]["parameters"]["properties"]

def test_dispatch_validates_and_runs(tmp_path):
    reg = ToolRegistry()
    reg.register(EchoTool())
    ctx = ToolContext(project_dir=tmp_path)
    res = reg.dispatch("echo", {"text": "hi"}, ctx)
    assert res.ok and res.content == "hi"

def test_dispatch_unknown_tool_returns_error(tmp_path):
    reg = ToolRegistry()
    ctx = ToolContext(project_dir=tmp_path)
    res = reg.dispatch("nope", {}, ctx)
    assert not res.ok and "unknown tool" in res.error.lower()

def test_dispatch_bad_args_returns_error(tmp_path):
    reg = ToolRegistry()
    reg.register(EchoTool())
    ctx = ToolContext(project_dir=tmp_path)
    res = reg.dispatch("echo", {}, ctx)  # missing 'text'
    assert not res.ok and res.error

def test_registry_tools_lists_registered():
    from pycode_agent.tools.registry import ToolRegistry
    from pycode_agent.tools.file_tools import ReadFile
    reg = ToolRegistry()
    reg.register(ReadFile())
    tools = reg.tools()
    assert any(t.name == "read_file" for t in tools)
