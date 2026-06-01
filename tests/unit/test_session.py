from __future__ import annotations
from pycode_agent.core.session import Session
from pycode_agent.core.session import SessionStore
from pycode_agent.core.messages import Message, ToolCall


def test_session_roundtrip_preserves_messages():
    msgs = [
        Message(role="system", content="SYS"),
        Message(role="user", content="hi"),
        Message(role="assistant", tool_calls=[ToolCall(id="t1", name="read_file", arguments={"path": "x"})]),
        Message(role="tool", tool_call_id="t1", content="data"),
        Message(role="assistant", content="done"),
    ]
    s = Session(id="s1", title="t", created_at="2026-06-01T00:00:00", messages=msgs)
    data = s.to_dict()
    s2 = Session.from_dict(data)
    assert s2.id == "s1"
    assert s2.title == "t"
    assert [m.role for m in s2.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert s2.messages[2].tool_calls[0].name == "read_file"
    assert s2.messages[3].tool_call_id == "t1"


def test_make_title_from_first_user_message():
    msgs = [Message(role="system", content="S"), Message(role="user", content="explain the project structure")]
    assert Session.make_title(msgs) == "explain the project structure"


def test_make_title_truncates_to_50_chars_and_strips_newlines():
    long = "a" * 80
    msgs = [Message(role="user", content="line1\n" + long)]
    title = Session.make_title(msgs)
    assert "\n" not in title
    assert len(title) <= 50


def test_make_title_empty_when_no_user_message():
    msgs = [Message(role="system", content="S")]
    assert Session.make_title(msgs) == "(empty)"


def _tmp_sessions(tmp=None):
    import tempfile
    from pathlib import Path
    return Path(tempfile.mkdtemp()) / "sessions"


def test_store_new_id_format():
    store = SessionStore(_tmp_sessions())
    sid = store.new_id()
    parts = sid.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 8 and len(parts[1]) == 6 and len(parts[2]) == 4


def test_store_new_session_has_id_and_timestamp():
    store = SessionStore(_tmp_sessions())
    s = store.new_session()
    assert s.id and s.created_at
    assert s.messages == []
    assert s.title == "(empty)"


def test_store_save_then_load_roundtrip(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    s = store.new_session()
    s.messages.append(Message(role="user", content="hello"))
    s.title = Session.make_title(s.messages)
    store.save(s)
    loaded = store.load(s.id)
    assert loaded.id == s.id
    assert loaded.messages[0].content == "hello"
    assert loaded.title == "hello"


def test_store_save_is_atomic_no_tmp_left(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    s = store.new_session()
    store.save(s)
    files = list((tmp_path / "sessions").iterdir())
    assert any(f.name == f"{s.id}.json" for f in files)
    assert not any(f.suffix == ".tmp" for f in files)


def test_store_load_unknown_raises_keyerror(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    import pytest
    with pytest.raises(KeyError):
        store.load("nope")


def _touch_mtime(path, ts):
    import os
    os.utime(path, (ts, ts))


def test_store_latest_returns_most_recent(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    a = store.new_session(); a.id = "20260101-000000-aaaa"; store.save(a)
    b = store.new_session(); b.id = "20260101-000000-bbbb"; store.save(b)
    _touch_mtime(store._path(a.id), 1000)
    _touch_mtime(store._path(b.id), 2000)
    assert store.latest().id == b.id


def test_store_latest_none_when_empty(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    assert store.latest() is None


def test_store_list_meta_sorted_desc_with_fields(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    a = store.new_session(); a.id = "20260101-000000-aaaa"
    a.messages = [Message(role="user", content="first task"), Message(role="assistant", content="ok"),
                  Message(role="user", content="second")]
    a.title = Session.make_title(a.messages); store.save(a)
    b = store.new_session(); b.id = "20260101-000000-bbbb"
    b.messages = [Message(role="user", content="other")]
    b.title = Session.make_title(b.messages); store.save(b)
    _touch_mtime(store._path(a.id), 1000)
    _touch_mtime(store._path(b.id), 2000)
    meta = store.list_meta()
    assert [m["id"] for m in meta] == [b.id, a.id]
    a_meta = next(m for m in meta if m["id"] == a.id)
    assert a_meta["title"] == "first task"
    assert a_meta["turns"] == 2


def test_store_list_meta_skips_corrupt_files(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    s = store.new_session(); store.save(s)
    (tmp_path / "sessions" / "broken.json").write_text("{not json", encoding="utf-8")
    meta = store.list_meta()
    assert len(meta) == 1
    assert meta[0]["id"] == s.id
