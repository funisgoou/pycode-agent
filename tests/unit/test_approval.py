from __future__ import annotations

from pycode_agent.security.approval import Approval


def test_ask_yes():
    outputs = []
    a = Approval(prompt_fn=lambda p: "y", out_fn=outputs.append, auto_yes=False)
    assert a.ask("运行工具 write_file", "--- a\n+++ b") is True


def test_ask_no():
    a = Approval(prompt_fn=lambda p: "n", out_fn=lambda s: None, auto_yes=False)
    assert a.ask("运行工具 write_file", "") is False


def test_ask_auto_yes():
    a = Approval(prompt_fn=lambda p: (_ for _ in ()).throw(AssertionError("should not prompt")),
                 out_fn=lambda s: None, auto_yes=True)
    assert a.ask("x", "y") is True


def test_ask_prompt_text_is_clear():
    seen = {}
    def prompt_fn(p):
        seen["prompt"] = p
        return "n"
    a = Approval(prompt_fn=prompt_fn, out_fn=lambda s: None, auto_yes=False)
    a.ask("运行工具 write_file", "")
    assert "继续" in seen["prompt"]
    assert "y" in seen["prompt"] and "n" in seen["prompt"]


def test_ask_outputs_title_and_detail():
    outputs = []
    a = Approval(prompt_fn=lambda p: "n", out_fn=outputs.append, auto_yes=False)
    a.ask("运行工具 write_file", "DETAIL_DIFF")
    joined = "\n".join(outputs)
    assert "write_file" in joined
    assert "DETAIL_DIFF" in joined
