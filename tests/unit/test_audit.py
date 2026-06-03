import json

from pycode_agent.logs.audit import AuditLog


def test_record_writes_jsonl(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    audit = AuditLog(log_path)
    audit.record(event="tool_call", tool="read_file", arguments={"path": "a.py"},
                 decision="allow", ok=True)
    audit.record(event="tool_call", tool="write_file", arguments={"path": "b.py"},
                 decision="confirm", ok=False, error="user rejected")
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["tool"] == "read_file" and first["decision"] == "allow"
    second = json.loads(lines[1])
    assert second["ok"] is False and second["error"] == "user rejected"
