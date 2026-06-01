from __future__ import annotations
from io import StringIO
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel

from pycode_agent.cli.render import (
    status_line, assistant_panel, tool_result_panel, diff_to_renderable,
    _looks_like_diff,
)
from pycode_agent.cli.render import StreamRenderer
from pycode_agent.model.streaming import (
    TextDelta, ToolCallStart, ToolCallEnd, ToolResultEvent, TurnEnd,
)


def _render(renderable) -> str:
    buf = StringIO()
    Console(file=buf, force_terminal=False, no_color=True, width=80).print(renderable)
    return buf.getvalue()


class _FakeCM:
    budget = 96000
    def estimate_tokens(self, messages):
        return 12000


class _FakeProvider:
    model = "opus-4-8"


class _FakeAgent:
    def __init__(self, with_cm=True):
        self.provider = _FakeProvider()
        self.messages = []
        self.context_manager = _FakeCM() if with_cm else None


class _FakeSecurity:
    mode = "confirm"


class _FakeSettings:
    security = _FakeSecurity()


def test_status_line_includes_model_mode_tokens():
    out = _render(status_line(_FakeAgent(), _FakeSettings()))
    assert "opus-4-8" in out
    assert "confirm" in out
    assert "12" in out and "96" in out


def test_status_line_without_context_manager_omits_tokens():
    out = _render(status_line(_FakeAgent(with_cm=False), _FakeSettings()))
    assert "opus-4-8" in out
    assert "confirm" in out


def test_assistant_panel_renders_markdown_text():
    panel = assistant_panel("hello **world**")
    assert isinstance(panel, Panel)
    out = _render(panel)
    assert "hello" in out and "world" in out
    assert "assistant" in out


def test_tool_result_panel_ok():
    panel = tool_result_panel("read_file", True, "120 lines")
    assert isinstance(panel, Panel)
    out = _render(panel)
    assert "read_file" in out
    assert "ok" in out
    assert "120 lines" in out


def test_tool_result_panel_error():
    panel = tool_result_panel("run_shell", False, "exit code 1")
    out = _render(panel)
    assert "run_shell" in out
    assert "error" in out
    assert "exit code 1" in out


def test_diff_to_renderable_returns_syntax_with_content():
    diff = "--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n"
    r = diff_to_renderable(diff)
    assert isinstance(r, Syntax)
    out = _render(r)
    assert "old" in out and "new" in out


def test_looks_like_diff_true_on_unified_diff():
    assert _looks_like_diff("--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\n") is True


def test_looks_like_diff_false_on_plain_text():
    assert _looks_like_diff("just a normal sentence about code") is False


def _renderer_output(events):
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=80)
    StreamRenderer(console).consume(iter(events))
    return buf.getvalue()


def test_stream_renderer_plain_text_to_markdown_panel():
    out = _renderer_output([
        TextDelta(text="Agent "),
        TextDelta(text="loop **runs**"),
        TurnEnd(text=None),
    ])
    assert "Agent" in out
    assert "loop" in out and "runs" in out
    assert "assistant" in out


def test_stream_renderer_tool_result_panel():
    out = _renderer_output([
        ToolCallStart(id="t1", name="read_file"),
        ToolCallEnd(id="t1", name="read_file", arguments={"path": "x"}),
        ToolResultEvent(tool_call_id="t1", ok=True, content="120 lines", error=None),
        TurnEnd(text=None),
    ])
    assert "read_file" in out
    assert "ok" in out
    assert "120 lines" in out


def test_stream_renderer_flushes_preamble_text_before_tool():
    out = _renderer_output([
        TextDelta(text="let me read the file"),
        ToolCallStart(id="t1", name="read_file"),
        ToolCallEnd(id="t1", name="read_file", arguments={}),
        ToolResultEvent(tool_call_id="t1", ok=True, content="data", error=None),
        TurnEnd(text=None),
    ])
    assert "let me read the file" in out
    assert out.index("let me read the file") < out.index("read_file")


def test_stream_renderer_turnend_text_fallback():
    out = _renderer_output([
        TurnEnd(text="final answer only"),
    ])
    assert "final answer only" in out


def test_stream_renderer_returns_final_text():
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=80)
    final = StreamRenderer(console).consume(iter([
        TextDelta(text="hello"), TurnEnd(text=None),
    ]))
    assert final == "hello"
