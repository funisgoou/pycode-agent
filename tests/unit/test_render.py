from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from pycode_agent.cli.render import (
    StreamRenderer,
    _looks_like_diff,
    assistant_panel,
    diff_to_renderable,
    status_line,
    status_text,
    tool_result_panel,
    welcome_banner,
)
from pycode_agent.model.streaming import (
    TextDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolResultEvent,
    TurnEnd,
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


def test_status_text_includes_model_mode_tokens():
    s = status_text(_FakeAgent(), _FakeSettings())
    assert isinstance(s, str)
    assert "opus-4-8" in s
    assert "confirm" in s
    assert "12" in s and "96" in s


def test_status_text_without_context_manager_omits_tokens():
    s = status_text(_FakeAgent(with_cm=False), _FakeSettings())
    assert "opus-4-8" in s
    assert "confirm" in s
    assert "token" not in s.lower()


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


def test_stream_renderer_interleaved_text_tool_text():
    out = _renderer_output([
        TextDelta(text="first part"),
        ToolCallStart(id="t1", name="read_file"),
        ToolCallEnd(id="t1", name="read_file", arguments={}),
        ToolResultEvent(tool_call_id="t1", ok=True, content="data", error=None),
        TextDelta(text="second part"),
        TurnEnd(text=None),
    ])
    # both text segments rendered, tool panel between them, correct order
    assert "first part" in out
    assert "second part" in out
    assert "read_file" in out
    assert out.index("first part") < out.index("read_file") < out.index("second part")


class _FakeLive:
    """Records constructor kwargs; no-op start/stop/update."""
    instances = []

    def __init__(self, renderable=None, **kwargs):
        self.initial_renderable = renderable
        self.renderable = renderable
        self.kwargs = kwargs
        _FakeLive.instances.append(self)

    def start(self):
        pass

    def stop(self):
        pass

    def update(self, renderable):
        self.renderable = renderable


def test_stream_renderer_live_is_transient(monkeypatch):
    """In terminal mode the raw-text Live must be transient, so it is cleared
    on stop and does not duplicate the final Markdown panel."""
    import pycode_agent.cli.render as render_mod

    _FakeLive.instances = []
    monkeypatch.setattr(render_mod, "Live", _FakeLive)

    buf = StringIO()
    console = Console(file=buf, force_terminal=True, no_color=True, width=80)
    StreamRenderer(console).consume(iter([
        TextDelta(text="你好"),
        TurnEnd(text=None),
    ]))

    assert _FakeLive.instances, "Live should be used in terminal mode"
    assert _FakeLive.instances[0].kwargs.get("transient") is True


def test_stream_renderer_shows_thinking_after_tool_result(monkeypatch):
    """After a ToolResultEvent, a 'Thinking...' Live is started to indicate
    the agent is waiting for the next API response."""
    import pycode_agent.cli.render as render_mod

    _FakeLive.instances = []
    monkeypatch.setattr(render_mod, "Live", _FakeLive)

    buf = StringIO()
    console = Console(file=buf, force_terminal=True, no_color=True, width=80)
    StreamRenderer(console).consume(iter([
        ToolCallStart(id="t1", name="list_dir"),
        ToolCallEnd(id="t1", name="list_dir", arguments={}),
        ToolResultEvent(tool_call_id="t1", ok=True, content="file.py", error=None),
        # At this point, a "Thinking..." Live should be active.
        # The next TextDelta replaces it with actual content.
        TextDelta(text="here is the file"),
        TurnEnd(text=None),
    ]))

    # Should have at least 2 Live instances: "Running list_dir..." and "Thinking..."
    live_texts = [str(inst.initial_renderable) for inst in _FakeLive.instances if inst.initial_renderable]
    assert any("Running list_dir" in t for t in live_texts), \
        f"Expected 'Running list_dir' in lives: {live_texts}"
    assert any("Thinking" in t for t in live_texts), \
        f"Expected 'Thinking' in lives: {live_texts}"


# ── Welcome banner ──────────────────────────────────────────────────

from pathlib import Path

from rich.table import Table


def test_welcome_banner_renders_version_and_info():
    from pycode_agent.config.settings import Settings
    s = Settings()
    table = welcome_banner(s, Path("/my/project"), version="1.2.3")
    assert isinstance(table, Table)
    out = _render(table)
    assert "Py" in out and "Code" in out
    assert "1.2.3" in out
    assert s.model.name in out
    assert s.security.mode in out


def test_welcome_banner_renders_icon():
    from pycode_agent.config.settings import Settings
    s = Settings()
    table = welcome_banner(s, Path("/tmp"))
    out = _render(table)
    # icon contains terminal-ish text
    assert "python" in out or "import" in out
    assert "ready" in out


def test_welcome_banner_without_version():
    from pycode_agent.config.settings import Settings
    s = Settings()
    table = welcome_banner(s, Path("/tmp"))
    out = _render(table)
    assert "Py" in out
    assert "1." not in out  # no version snippet
