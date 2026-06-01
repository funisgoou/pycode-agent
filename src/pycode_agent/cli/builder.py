from __future__ import annotations
from pathlib import Path
from pycode_agent.config.settings import Settings
from pycode_agent.core.agent import Agent
from pycode_agent.model.base import LLMProvider
from pycode_agent.tools.base import ToolContext
from pycode_agent.tools.registry import ToolRegistry
from pycode_agent.tools.file_tools import ReadFile, ListDir, SearchText, WriteFile, EditFile, StrReplace
from pycode_agent.tools.shell_tools import RunShell
from pycode_agent.tools.git_tools import GitStatus, GitDiff
from pycode_agent.tools.memory_tools import MemoryRead, MemoryWrite
from pycode_agent.security.policy import Policy
from pycode_agent.security.approval import Approval
from pycode_agent.logs.audit import AuditLog
from pycode_agent.utils.diff import PatchManager
from pycode_agent.core.context_manager import ContextManager
from pycode_agent.core.session import Session, SessionStore


def _build_registry(settings: Settings) -> ToolRegistry:
    reg = ToolRegistry()
    for tool in (ReadFile(), ListDir(), SearchText(), WriteFile(), EditFile(), StrReplace(),
                 GitStatus(), GitDiff(), MemoryRead(), MemoryWrite()):
        reg.register(tool)
    if settings.security.allow_shell:
        reg.register(RunShell())
    return reg


def _make_session_sink(store: SessionStore, session: Session):
    def sink(messages):
        session.messages = list(messages)
        session.title = Session.make_title(messages)
        store.save(session)
    return sink


def build_agent_with_provider(*, provider: LLMProvider, project_dir: Path,
                              settings: Settings, auto_yes: bool = False,
                              dry_run: bool = False, max_turns: int | None = None,
                              session_store: SessionStore | None = None,
                              session: Session | None = None) -> Agent:
    project_dir = Path(project_dir)
    pm = PatchManager()
    ctx = ToolContext(project_dir=project_dir, settings=settings, patch_manager=pm)
    cm = ContextManager(
        budget=settings.model.context_budget,
        ratio=settings.model.compaction_ratio,
        keep_recent_turns=settings.model.keep_recent_turns,
    )
    sink = None
    if settings.agent.persist_sessions:
        if session_store is None:
            session_store = SessionStore(project_dir / ".pycode" / "sessions")
        if session is None:
            session = session_store.new_session()
        sink = _make_session_sink(session_store, session)
    agent = Agent(
        provider=provider,
        registry=_build_registry(settings),
        policy=Policy(mode=settings.security.mode),
        approval=Approval(auto_yes=auto_yes),
        audit=AuditLog(project_dir / ".pycode" / "audit.jsonl"),
        ctx=ctx,
        max_turns=max_turns if max_turns is not None else settings.agent.max_turns,
        max_tool_calls=settings.agent.max_tool_calls,
        system_prefix="",
        dry_run=dry_run,
        context_manager=cm,
        session_sink=sink,
    )
    if session is not None and session.messages:
        agent.messages = list(session.messages)
    return agent
