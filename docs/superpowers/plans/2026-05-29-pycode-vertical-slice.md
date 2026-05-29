# PyCodeAgent 垂直切片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个可真实运行的 Claude Code-like Python CLI 垂直切片:CLI → 配置 → 模型 Provider(含 Fake)→ Agent Loop → 文件/搜索/Shell/Git/记忆工具(diff + 权限确认)→ 非交互模式 → 审计日志。

**Architecture:** 分层(CLI/REPL → 会话 → Agent Engine → {Provider, ToolRegistry, ContextManager} + security/logs)。同步核心(httpx 同步 + 流式),原生 function-calling 工具机制。Provider 与 Tool 均为抽象基类 + 具体实现,`FakeLLMProvider` 用脚本化响应确定性驱动 Loop 以便测试。

**Tech Stack:** Python 3.11+, Typer, Pydantic v2, pydantic-settings, httpx, rich, pytest。

依据规格:`docs/superpowers/specs/2026-05-29-pycode-design.md`

---

## 文件结构(决策锁定)

| 文件 | 职责 |
|---|---|
| `pyproject.toml` | 包元数据、依赖、入口点 `pycode`、pytest 配置 |
| `src/pycode_agent/core/messages.py` | `Message` / `ToolCall` / `ToolResult` 数据模型 |
| `src/pycode_agent/config/settings.py` | `Settings` pydantic-settings 模型 |
| `src/pycode_agent/config/loader.py` | 多来源配置合并(CLI > 项目 > 用户 > 环境) |
| `src/pycode_agent/model/errors.py` | Provider 分类异常 |
| `src/pycode_agent/model/base.py` | `LLMProvider` 抽象 + `LLMResponse` |
| `src/pycode_agent/model/fake.py` | `FakeLLMProvider`(脚本化) |
| `src/pycode_agent/model/openai_compatible.py` | OpenAI 兼容 Provider |
| `src/pycode_agent/security/paths.py` | 敏感文件判定、路径安全 |
| `src/pycode_agent/security/policy.py` | 四权限模式 + 风险判定 |
| `src/pycode_agent/security/approval.py` | 确认交互 |
| `src/pycode_agent/utils/diff.py` | `PatchManager`(diff 应用/回滚) |
| `src/pycode_agent/tools/base.py` | `Tool` 抽象 + `Risk` + `ToolContext` |
| `src/pycode_agent/tools/registry.py` | `ToolRegistry` |
| `src/pycode_agent/tools/file_tools.py` | read/list/search/write/edit |
| `src/pycode_agent/tools/shell_tools.py` | run_shell + 黑名单 |
| `src/pycode_agent/tools/git_tools.py` | git_status / git_diff |
| `src/pycode_agent/tools/memory_tools.py` | memory_read / memory_write |
| `src/pycode_agent/context/scanner.py` | 项目扫描 + 忽略规则 |
| `src/pycode_agent/logs/audit.py` | JSONL 审计 |
| `src/pycode_agent/core/agent.py` | Agent Loop |
| `src/pycode_agent/cli/main.py` | Typer 入口 |
| `src/pycode_agent/cli/repl.py` | 交互式 REPL |

---

### Task 1: 项目骨架

**Files:**
- Create: `pyproject.toml`
- Create: `src/pycode_agent/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
import pycode_agent

def test_version_exposed():
    assert isinstance(pycode_agent.__version__, str)
    assert pycode_agent.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL (ModuleNotFoundError: pycode_agent)

- [ ] **Step 3: Write pyproject.toml and package init**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pycode-agent"
version = "0.1.0"
description = "Clean-room Claude Code-like coding CLI (vertical slice)"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "httpx>=0.27",
    "rich>=13.7",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
pycode = "pycode_agent.cli.main:app"

[tool.hatch.build.targets.wheel]
packages = ["src/pycode_agent"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

```python
# src/pycode_agent/__init__.py
__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/pycode_agent/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "feat: project scaffold with pyproject and smoke test"
```

---

### Task 2: 核心数据模型 messages.py

**Files:**
- Create: `src/pycode_agent/core/__init__.py`
- Create: `src/pycode_agent/core/messages.py`
- Test: `tests/unit/test_messages.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_messages.py
from pycode_agent.core.messages import Message, ToolCall, ToolResult

def test_toolcall_roundtrip():
    tc = ToolCall(id="c1", name="read_file", arguments={"path": "a.py"})
    assert tc.name == "read_file"
    assert tc.arguments["path"] == "a.py"

def test_tool_message_carries_call_id():
    m = Message(role="tool", content="ok", tool_call_id="c1")
    assert m.role == "tool"
    assert m.tool_call_id == "c1"

def test_toolresult_defaults():
    r = ToolResult(ok=True, content="done")
    assert r.error is None
    assert r.meta == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_messages.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/core/__init__.py
```

```python
# src/pycode_agent/core/messages.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    ok: bool
    content: str = ""
    error: str | None = None
    meta: dict = Field(default_factory=dict)


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_messages.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/core tests/unit/test_messages.py
git commit -m "feat: core message data models"
```

---

### Task 3: 配置系统

**Files:**
- Create: `src/pycode_agent/config/__init__.py`
- Create: `src/pycode_agent/config/settings.py`
- Create: `src/pycode_agent/config/loader.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config.py
from pycode_agent.config.loader import merge_config
from pycode_agent.config.settings import Settings

def test_cli_overrides_env():
    s = merge_config(
        env={"PYCODE_MODEL_NAME": "env-model"},
        user_file={"model": {"name": "user-model"}},
        project_file={"model": {"name": "proj-model"}},
        cli={"model": {"name": "cli-model"}},
    )
    assert s.model.name == "cli-model"

def test_project_overrides_user():
    s = merge_config(
        env={},
        user_file={"model": {"name": "user-model"}},
        project_file={"model": {"name": "proj-model"}},
        cli={},
    )
    assert s.model.name == "proj-model"

def test_defaults_when_empty():
    s = merge_config(env={}, user_file={}, project_file={}, cli={})
    assert s.security.mode == "confirm"
    assert s.model.timeout == 120
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/config/__init__.py
```

```python
# src/pycode_agent/config/settings.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ModelSettings(BaseModel):
    provider: str = "openai_compatible"
    name: str = "default-coding-model"
    base_url: str = "https://api.example.com/v1"
    api_key: str | None = None
    timeout: int = 120
    stream: bool = True


class SecuritySettings(BaseModel):
    mode: Literal["readonly", "confirm", "workspace", "dangerous"] = "confirm"
    allow_shell: bool = True
    allow_git_push: bool = False


class ContextSettings(BaseModel):
    max_files: int = 200
    max_tokens: int = 120000
    enable_project_memory: bool = True


class AgentSettings(BaseModel):
    max_turns: int = 12
    max_tool_calls: int = 40


class Settings(BaseModel):
    model: ModelSettings = Field(default_factory=ModelSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
```

```python
# src/pycode_agent/config/loader.py
from __future__ import annotations
import os
import tomllib
from pathlib import Path
from .settings import Settings


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env_to_nested(env: dict[str, str]) -> dict:
    """PYCODE_MODEL_NAME=x -> {'model': {'name': 'x'}}; only known top sections."""
    sections = {"model", "security", "context", "agent"}
    out: dict = {}
    for key, val in env.items():
        if not key.startswith("PYCODE_"):
            continue
        parts = key[len("PYCODE_"):].lower().split("_", 1)
        if len(parts) != 2 or parts[0] not in sections:
            continue
        out.setdefault(parts[0], {})[parts[1]] = val
    return out


def merge_config(*, env: dict, user_file: dict, project_file: dict, cli: dict) -> Settings:
    merged: dict = {}
    for layer in (_env_to_nested(env), user_file, project_file, cli):
        merged = _deep_merge(merged, layer)
    return Settings.model_validate(merged)


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def load_settings(project_dir: Path, cli_overrides: dict | None = None) -> Settings:
    user_file = _read_toml(Path.home() / ".pycode" / "config.toml")
    project_file = _read_toml(project_dir / ".pycode" / "config.toml")
    return merge_config(
        env=dict(os.environ),
        user_file=user_file,
        project_file=project_file,
        cli=cli_overrides or {},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/config tests/unit/test_config.py
git commit -m "feat: layered config system"
```

---

### Task 4: Provider 抽象 + 异常 + FakeLLMProvider

**Files:**
- Create: `src/pycode_agent/model/__init__.py`
- Create: `src/pycode_agent/model/errors.py`
- Create: `src/pycode_agent/model/base.py`
- Create: `src/pycode_agent/model/fake.py`
- Test: `tests/unit/test_fake_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fake_provider.py
from pycode_agent.core.messages import Message, ToolCall
from pycode_agent.model.fake import FakeLLMProvider
from pycode_agent.model.base import LLMResponse

def test_fake_returns_scripted_text():
    p = FakeLLMProvider(script=[LLMResponse(text="hello")])
    r = p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert r.text == "hello"
    assert r.tool_calls == []

def test_fake_returns_scripted_tool_calls_then_text():
    p = FakeLLMProvider(script=[
        LLMResponse(tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "a.py"})]),
        LLMResponse(text="done"),
    ])
    msgs = [Message(role="user", content="read a.py")]
    r1 = p.chat(messages=msgs, tools=[])
    assert r1.tool_calls[0].name == "read_file"
    r2 = p.chat(messages=msgs, tools=[])
    assert r2.text == "done"

def test_fake_exhausted_raises():
    import pytest
    p = FakeLLMProvider(script=[LLMResponse(text="only")])
    p.chat(messages=[], tools=[])
    with pytest.raises(IndexError):
        p.chat(messages=[], tools=[])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fake_provider.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/model/__init__.py
```

```python
# src/pycode_agent/model/errors.py
class ProviderError(Exception): ...
class AuthError(ProviderError): ...
class RateLimitError(ProviderError): ...
class TimeoutError(ProviderError): ...
class ContextOverflowError(ProviderError): ...
class NetworkError(ProviderError): ...
class ToolFormatError(ProviderError): ...
```

```python
# src/pycode_agent/model/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from pycode_agent.core.messages import Message, ToolCall


class LLMResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, *, messages: list[Message], tools: list[dict]) -> LLMResponse:
        """Single turn. tools is a list of JSON-schema tool specs."""
        ...
```

```python
# src/pycode_agent/model/fake.py
from __future__ import annotations
from pycode_agent.core.messages import Message
from .base import LLMProvider, LLMResponse


class FakeLLMProvider(LLMProvider):
    """Deterministic provider driven by a scripted list of responses."""

    def __init__(self, script: list[LLMResponse]):
        self._script = list(script)
        self._i = 0
        self.calls: list[list[Message]] = []

    def chat(self, *, messages: list[Message], tools: list[dict]) -> LLMResponse:
        self.calls.append(list(messages))
        resp = self._script[self._i]  # raises IndexError when exhausted
        self._i += 1
        return resp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fake_provider.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/model tests/unit/test_fake_provider.py
git commit -m "feat: LLMProvider abstraction, errors, FakeLLMProvider"
```

---

### Task 5: 敏感文件判定 security/paths.py

**Files:**
- Create: `src/pycode_agent/security/__init__.py`
- Create: `src/pycode_agent/security/paths.py`
- Test: `tests/unit/test_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_paths.py
from pycode_agent.security.paths import is_sensitive

def test_env_file_sensitive():
    assert is_sensitive(".env")
    assert is_sensitive("config/.env.local")

def test_key_and_cert_sensitive():
    assert is_sensitive("id_rsa.pem")
    assert is_sensitive("server.key")
    assert is_sensitive("secrets/api_token.txt")

def test_normal_source_not_sensitive():
    assert not is_sensitive("src/app/main.py")
    assert not is_sensitive("README.md")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_paths.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/security/__init__.py
```

```python
# src/pycode_agent/security/paths.py
from __future__ import annotations
import re
from pathlib import PurePosixPath

_SENSITIVE_PATTERNS = [
    r"(^|/)\.env(\.|$)",
    r"\.pem$",
    r"\.key$",
    r"\.p12$",
    r"\.pfx$",
    r"(^|/)id_rsa($|\.)",
    r"token",
    r"secret",
    r"credential",
    r"\.aws/credentials$",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SENSITIVE_PATTERNS]


def is_sensitive(path: str) -> bool:
    norm = str(PurePosixPath(path.replace("\\", "/")))
    return any(rx.search(norm) for rx in _COMPILED)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_paths.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/security/__init__.py src/pycode_agent/security/paths.py tests/unit/test_paths.py
git commit -m "feat: sensitive file detection"
```

---

### Task 6: 权限策略 security/policy.py

**Files:**
- Create: `src/pycode_agent/security/policy.py`
- Test: `tests/unit/test_policy.py`

依赖:`Risk` 枚举将在 Task 8 的 `tools/base.py` 定义。为避免循环依赖,`Risk` 定义放在本任务先行创建的 `tools/base.py` 中;若 Task 8 尚未执行,本任务需先建最小 `tools/base.py`(仅 `Risk`)。**执行顺序:本任务先创建 `tools/base.py` 的 `Risk` 部分,Task 8 再补全 `Tool`/`ToolContext`。**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_policy.py
from pycode_agent.tools.base import Risk
from pycode_agent.security.policy import Policy, Decision

def test_readonly_blocks_high_risk():
    p = Policy(mode="readonly")
    assert p.evaluate(Risk.LOW) == Decision.ALLOW
    assert p.evaluate(Risk.HIGH) == Decision.DENY

def test_confirm_requires_confirm_for_high():
    p = Policy(mode="confirm")
    assert p.evaluate(Risk.LOW) == Decision.ALLOW
    assert p.evaluate(Risk.HIGH) == Decision.CONFIRM

def test_workspace_allows_medium_confirms_high():
    p = Policy(mode="workspace")
    assert p.evaluate(Risk.MEDIUM) == Decision.ALLOW
    assert p.evaluate(Risk.HIGH) == Decision.CONFIRM

def test_dangerous_allows_all():
    p = Policy(mode="dangerous")
    assert p.evaluate(Risk.HIGH) == Decision.ALLOW
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_policy.py -v`
Expected: FAIL (ModuleNotFoundError: pycode_agent.tools.base)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/tools/__init__.py
```

```python
# src/pycode_agent/tools/base.py  (本任务仅创建 Risk;Task 8 补全其余)
from __future__ import annotations
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
```

```python
# src/pycode_agent/security/policy.py
from __future__ import annotations
from enum import Enum
from pycode_agent.tools.base import Risk


class Decision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class Policy:
    def __init__(self, mode: str = "confirm"):
        self.mode = mode

    def evaluate(self, risk: Risk) -> Decision:
        if self.mode == "dangerous":
            return Decision.ALLOW
        if self.mode == "readonly":
            return Decision.ALLOW if risk == Risk.LOW else Decision.DENY
        if self.mode == "workspace":
            if risk <= Risk.MEDIUM:
                return Decision.ALLOW
            return Decision.CONFIRM
        # confirm (default)
        return Decision.ALLOW if risk == Risk.LOW else Decision.CONFIRM
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_policy.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/tools/__init__.py src/pycode_agent/tools/base.py src/pycode_agent/security/policy.py tests/unit/test_policy.py
git commit -m "feat: permission policy with four modes"
```

---

### Task 7: PatchManager utils/diff.py

**Files:**
- Create: `src/pycode_agent/utils/__init__.py`
- Create: `src/pycode_agent/utils/diff.py`
- Test: `tests/unit/test_diff.py`

PatchManager 采用"整文件替换 + 生成 diff 预览 + 回滚"模型(切片简化:`edit_file` 接收新内容而非 unified diff 补丁,降低解析脆弱性;diff 仅用于**展示**)。冲突检测:写入前比对调用方提供的 `expected_old`(若提供)与磁盘实际内容,不一致则拒绝。

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_diff.py
from pathlib import Path
from pycode_agent.utils.diff import PatchManager, ConflictError
import pytest

def test_preview_unified_diff(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("line1\nline2\n", encoding="utf-8")
    pm = PatchManager()
    diff = pm.preview(f, "line1\nCHANGED\n")
    assert "-line2" in diff
    assert "+CHANGED" in diff

def test_apply_and_rollback(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("old\n", encoding="utf-8")
    pm = PatchManager()
    token = pm.apply(f, "new\n")
    assert f.read_text(encoding="utf-8") == "new\n"
    pm.rollback(token)
    assert f.read_text(encoding="utf-8") == "old\n"

def test_apply_new_file_then_rollback(tmp_path):
    f = tmp_path / "created.txt"
    pm = PatchManager()
    token = pm.apply(f, "hello\n")
    assert f.read_text(encoding="utf-8") == "hello\n"
    pm.rollback(token)
    assert not f.exists()

def test_conflict_when_expected_mismatch(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("actual\n", encoding="utf-8")
    pm = PatchManager()
    with pytest.raises(ConflictError):
        pm.apply(f, "new\n", expected_old="something else\n")
    assert f.read_text(encoding="utf-8") == "actual\n"  # 文件未被破坏
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_diff.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/utils/__init__.py
```

```python
# src/pycode_agent/utils/diff.py
from __future__ import annotations
import difflib
from dataclasses import dataclass
from pathlib import Path


class ConflictError(Exception):
    ...


@dataclass
class RollbackToken:
    path: Path
    existed_before: bool
    old_content: str | None


class PatchManager:
    """整文件替换模型:预览 unified diff、应用、回滚最近一次变更。"""

    def __init__(self) -> None:
        self._last: RollbackToken | None = None

    def preview(self, path: Path, new_content: str) -> str:
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
        return "".join(diff)

    def apply(self, path: Path, new_content: str, expected_old: str | None = None) -> RollbackToken:
        existed = path.is_file()
        old = path.read_text(encoding="utf-8") if existed else None
        if expected_old is not None and (old or "") != expected_old:
            raise ConflictError(f"expected_old does not match current content of {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        token = RollbackToken(path=path, existed_before=existed, old_content=old)
        self._last = token
        return token

    def rollback(self, token: RollbackToken) -> None:
        if token.existed_before:
            token.path.write_text(token.old_content or "", encoding="utf-8")
        else:
            if token.path.exists():
                token.path.unlink()

    def rollback_last(self) -> bool:
        if self._last is None:
            return False
        self.rollback(self._last)
        self._last = None
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_diff.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/utils tests/unit/test_diff.py
git commit -m "feat: PatchManager with preview, apply, rollback, conflict detection"
```

---

### Task 8: Tool 基类补全 + ToolRegistry + Approval

**Files:**
- Modify: `src/pycode_agent/tools/base.py`(补全 `Tool` / `ToolContext`)
- Create: `src/pycode_agent/tools/registry.py`
- Create: `src/pycode_agent/security/approval.py`
- Test: `tests/unit/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_registry.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_registry.py -v`
Expected: FAIL (ImportError: cannot import name 'Tool')

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/tools/base.py  (完整替换 Task 6 的最小版本)
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from pydantic import BaseModel
from pycode_agent.core.messages import ToolResult


class Risk(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


@dataclass
class ToolContext:
    project_dir: Path
    settings: object | None = None
    patch_manager: object | None = None
    extra: dict = field(default_factory=dict)


class Tool(ABC):
    name: str
    description: str
    args_model: type[BaseModel]
    risk: Risk

    @abstractmethod
    def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...

    def json_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }
```

```python
# src/pycode_agent/tools/registry.py
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
```

```python
# src/pycode_agent/security/approval.py
from __future__ import annotations
from typing import Callable


class Approval:
    """确认交互。可注入 input/output 以便测试。"""

    def __init__(self, prompt_fn: Callable[[str], str] = input,
                 out_fn: Callable[[str], None] = print, auto_yes: bool = False):
        self._prompt = prompt_fn
        self._out = out_fn
        self._auto_yes = auto_yes

    def ask(self, title: str, detail: str = "") -> bool:
        if self._auto_yes:
            return True
        self._out(f"\n[确认] {title}")
        if detail:
            self._out(detail)
        ans = self._prompt("应用? [y/N] ").strip().lower()
        return ans in ("y", "yes")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_registry.py -v`
Expected: PASS (4 passed). 同时重跑 `pytest tests/unit/test_policy.py` 确认仍 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/tools/base.py src/pycode_agent/tools/registry.py src/pycode_agent/security/approval.py tests/unit/test_registry.py
git commit -m "feat: Tool base, ToolRegistry, Approval"
```

---

### Task 9: 文件工具 file_tools.py

**Files:**
- Create: `src/pycode_agent/tools/file_tools.py`
- Test: `tests/unit/test_file_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_file_tools.py
from pathlib import Path
from pycode_agent.tools.base import ToolContext, Risk
from pycode_agent.tools.file_tools import ReadFile, ListDir, SearchText, WriteFile
from pycode_agent.utils.diff import PatchManager

def _ctx(tmp_path) -> ToolContext:
    return ToolContext(project_dir=tmp_path, patch_manager=PatchManager())

def test_read_file(tmp_path):
    (tmp_path / "a.py").write_text("print('x')\n", encoding="utf-8")
    res = ReadFile().run(ReadFile.args_model(path="a.py"), _ctx(tmp_path))
    assert res.ok and "print('x')" in res.content

def test_read_sensitive_blocked(tmp_path):
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    res = ReadFile().run(ReadFile.args_model(path=".env"), _ctx(tmp_path))
    assert not res.ok and "sensitive" in res.error.lower()

def test_list_dir(tmp_path):
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    res = ListDir().run(ListDir.args_model(path="."), _ctx(tmp_path))
    assert res.ok and "a.py" in res.content and "sub" in res.content

def test_search_text(tmp_path):
    (tmp_path / "a.py").write_text("hello world\nfoo\n", encoding="utf-8")
    res = SearchText().run(SearchText.args_model(query="hello"), _ctx(tmp_path))
    assert res.ok and "a.py" in res.content

def test_write_file_is_high_risk():
    assert WriteFile.risk == Risk.HIGH

def test_write_file_creates(tmp_path):
    res = WriteFile().run(WriteFile.args_model(path="new.txt", content="hi\n"), _ctx(tmp_path))
    assert res.ok
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "hi\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_file_tools.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/tools/file_tools.py
from __future__ import annotations
import subprocess
from pathlib import Path
from pydantic import BaseModel, Field
from pycode_agent.core.messages import ToolResult
from pycode_agent.security.paths import is_sensitive
from .base import Tool, Risk, ToolContext

MAX_READ_BYTES = 200_000


def _resolve(ctx: ToolContext, rel: str) -> Path:
    return (ctx.project_dir / rel).resolve()


class ReadArgs(BaseModel):
    path: str = Field(description="项目内相对路径")


class ReadFile(Tool):
    name = "read_file"
    description = "读取文本文件内容(相对项目根目录)"
    args_model = ReadArgs
    risk = Risk.LOW

    def run(self, args: ReadArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        p = _resolve(ctx, args.path)
        if not p.is_file():
            return ToolResult(ok=False, error=f"not a file: {args.path}")
        data = p.read_text(encoding="utf-8", errors="replace")[:MAX_READ_BYTES]
        return ToolResult(ok=True, content=data)


class ListArgs(BaseModel):
    path: str = "."


class ListDir(Tool):
    name = "list_dir"
    description = "列出目录下的文件与子目录"
    args_model = ListArgs
    risk = Risk.LOW

    def run(self, args: ListArgs, ctx: ToolContext) -> ToolResult:
        p = _resolve(ctx, args.path)
        if not p.is_dir():
            return ToolResult(ok=False, error=f"not a dir: {args.path}")
        entries = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
        return ToolResult(ok=True, content="\n".join(entries))


class SearchArgs(BaseModel):
    query: str
    path: str = "."


class SearchText(Tool):
    name = "search_text"
    description = "在项目中搜索文本(优先 ripgrep,回退 Python)"
    args_model = SearchArgs
    risk = Risk.LOW

    def run(self, args: SearchArgs, ctx: ToolContext) -> ToolResult:
        base = _resolve(ctx, args.path)
        try:
            out = subprocess.run(
                ["rg", "-n", "--no-heading", args.query, str(base)],
                capture_output=True, text=True, timeout=30,
            )
            if out.returncode in (0, 1):
                return ToolResult(ok=True, content=out.stdout[:MAX_READ_BYTES] or "(no matches)")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Python fallback
        hits: list[str] = []
        for f in base.rglob("*"):
            if not f.is_file() or is_sensitive(str(f)):
                continue
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if args.query in line:
                        hits.append(f"{f.relative_to(ctx.project_dir)}:{i}:{line}")
            except OSError:
                continue
        return ToolResult(ok=True, content="\n".join(hits[:500]) or "(no matches)")


class WriteArgs(BaseModel):
    path: str
    content: str


class WriteFile(Tool):
    name = "write_file"
    description = "写入或覆盖文件(高风险,需确认)"
    args_model = WriteArgs
    risk = Risk.HIGH

    def run(self, args: WriteArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        p = _resolve(ctx, args.path)
        pm = ctx.patch_manager
        pm.apply(p, args.content)
        return ToolResult(ok=True, content=f"wrote {args.path}")


class EditArgs(BaseModel):
    path: str
    content: str = Field(description="文件的完整新内容")
    expected_old: str | None = Field(default=None, description="期望的旧内容,用于冲突检测")


class EditFile(Tool):
    name = "edit_file"
    description = "用新内容替换文件(展示 diff,高风险,需确认)"
    args_model = EditArgs
    risk = Risk.HIGH

    def run(self, args: EditArgs, ctx: ToolContext) -> ToolResult:
        if is_sensitive(args.path):
            return ToolResult(ok=False, error="refused: sensitive file")
        from pycode_agent.utils.diff import ConflictError
        p = _resolve(ctx, args.path)
        pm = ctx.patch_manager
        try:
            pm.apply(p, args.content, expected_old=args.expected_old)
        except ConflictError as e:
            return ToolResult(ok=False, error=str(e))
        return ToolResult(ok=True, content=f"edited {args.path}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_file_tools.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/tools/file_tools.py tests/unit/test_file_tools.py
git commit -m "feat: file tools (read/list/search/write/edit) with sensitive guard"
```

---

### Task 10: Shell 工具 shell_tools.py

**Files:**
- Create: `src/pycode_agent/tools/shell_tools.py`
- Test: `tests/unit/test_shell_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_shell_tools.py
from pycode_agent.tools.base import ToolContext, Risk
from pycode_agent.tools.shell_tools import RunShell, is_blacklisted

def _ctx(tmp_path):
    return ToolContext(project_dir=tmp_path)

def test_blacklist_rm_rf_root():
    assert is_blacklisted("rm -rf /")
    assert is_blacklisted("sudo apt install x")
    assert is_blacklisted(":(){ :|:& };:")

def test_normal_command_not_blacklisted():
    assert not is_blacklisted("pytest -q")
    assert not is_blacklisted("git status")

def test_run_echo(tmp_path):
    res = RunShell().run(RunShell.args_model(command="echo hello"), _ctx(tmp_path))
    assert res.ok and "hello" in res.content
    assert res.meta["exit_code"] == 0

def test_blacklisted_refused(tmp_path):
    res = RunShell().run(RunShell.args_model(command="rm -rf /"), _ctx(tmp_path))
    assert not res.ok and "blacklist" in res.error.lower()

def test_run_shell_is_high_risk():
    assert RunShell.risk == Risk.HIGH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_shell_tools.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/tools/shell_tools.py
from __future__ import annotations
import re
import subprocess
from pydantic import BaseModel, Field
from pycode_agent.core.messages import ToolResult
from .base import Tool, Risk, ToolContext

_BLACKLIST = [
    r"\brm\s+-rf\s+/",
    r"\bsudo\b",
    r"\bmkfs\b",
    r":\(\)\s*\{.*:\|:&.*\}",   # fork bomb
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\bchmod\s+-R\s+777\s+/",
]
_BL = [re.compile(p) for p in _BLACKLIST]

MAX_OUTPUT = 50_000


def is_blacklisted(command: str) -> bool:
    return any(rx.search(command) for rx in _BL)


class ShellArgs(BaseModel):
    command: str
    timeout: int = Field(default=60, le=600)


class RunShell(Tool):
    name = "run_shell"
    description = "执行 shell 命令(高风险,受黑名单与权限约束)"
    args_model = ShellArgs
    risk = Risk.HIGH

    def run(self, args: ShellArgs, ctx: ToolContext) -> ToolResult:
        if is_blacklisted(args.command):
            return ToolResult(ok=False, error="refused: command matches blacklist")
        try:
            proc = subprocess.run(
                args.command, shell=True, cwd=str(ctx.project_dir),
                capture_output=True, text=True, timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error="timed out", meta={"timed_out": True})
        out = (proc.stdout + (("\n[stderr]\n" + proc.stderr) if proc.stderr else ""))[:MAX_OUTPUT]
        return ToolResult(
            ok=proc.returncode == 0,
            content=out,
            error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
            meta={"exit_code": proc.returncode},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_shell_tools.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/tools/shell_tools.py tests/unit/test_shell_tools.py
git commit -m "feat: run_shell tool with blacklist and timeout"
```

---

### Task 11: Git 工具 + 记忆工具

**Files:**
- Create: `src/pycode_agent/tools/git_tools.py`
- Create: `src/pycode_agent/tools/memory_tools.py`
- Test: `tests/unit/test_git_memory_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_git_memory_tools.py
import subprocess
from pycode_agent.tools.base import ToolContext, Risk
from pycode_agent.tools.git_tools import GitStatus, GitDiff
from pycode_agent.tools.memory_tools import MemoryRead, MemoryWrite
from pycode_agent.utils.diff import PatchManager

def _git(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=a",
                    "commit", "--allow-empty", "-qm", "init"], cwd=tmp_path)

def _ctx(tmp_path):
    return ToolContext(project_dir=tmp_path, patch_manager=PatchManager())

def test_git_status(tmp_path):
    _git(tmp_path)
    (tmp_path / "new.py").write_text("x\n", encoding="utf-8")
    res = GitStatus().run(GitStatus.args_model(), _ctx(tmp_path))
    assert res.ok and "new.py" in res.content

def test_git_diff(tmp_path):
    _git(tmp_path)
    f = tmp_path / "a.py"
    f.write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path)
    res = GitDiff().run(GitDiff.args_model(staged=True), _ctx(tmp_path))
    assert res.ok and "a.py" in res.content

def test_memory_read_missing(tmp_path):
    res = MemoryRead().run(MemoryRead.args_model(), _ctx(tmp_path))
    assert res.ok and "no project memory" in res.content.lower()

def test_memory_write_and_read(tmp_path):
    MemoryWrite().run(MemoryWrite.args_model(content="# Mem\n- uses pytest\n"), _ctx(tmp_path))
    res = MemoryRead().run(MemoryRead.args_model(), _ctx(tmp_path))
    assert "uses pytest" in res.content

def test_memory_write_is_high_risk():
    assert MemoryWrite.risk == Risk.HIGH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_git_memory_tools.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/tools/git_tools.py
from __future__ import annotations
import subprocess
from pydantic import BaseModel
from pycode_agent.core.messages import ToolResult
from .base import Tool, Risk, ToolContext


def _git(ctx: ToolContext, *git_args: str) -> ToolResult:
    try:
        proc = subprocess.run(
            ["git", *git_args], cwd=str(ctx.project_dir),
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return ToolResult(ok=False, error="git not found")
    if proc.returncode != 0:
        return ToolResult(ok=False, error=proc.stderr.strip() or "git failed")
    return ToolResult(ok=True, content=proc.stdout or "(empty)")


class NoArgs(BaseModel):
    pass


class GitStatus(Tool):
    name = "git_status"
    description = "查看 git 工作区状态"
    args_model = NoArgs
    risk = Risk.LOW

    def run(self, args: NoArgs, ctx: ToolContext) -> ToolResult:
        return _git(ctx, "status", "--short", "--branch")


class DiffArgs(BaseModel):
    staged: bool = False


class GitDiff(Tool):
    name = "git_diff"
    description = "查看 git diff(可选 staged)"
    args_model = DiffArgs
    risk = Risk.LOW

    def run(self, args: DiffArgs, ctx: ToolContext) -> ToolResult:
        extra = ["--staged"] if args.staged else []
        return _git(ctx, "diff", *extra)
```

```python
# src/pycode_agent/tools/memory_tools.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_git_memory_tools.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/tools/git_tools.py src/pycode_agent/tools/memory_tools.py tests/unit/test_git_memory_tools.py
git commit -m "feat: git and memory tools"
```

---

### Task 12: 项目扫描 context/scanner.py

**Files:**
- Create: `src/pycode_agent/context/__init__.py`
- Create: `src/pycode_agent/context/scanner.py`
- Test: `tests/unit/test_scanner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scanner.py
from pycode_agent.context.scanner import scan_project, IGNORED_DIRS

def test_ignores_common_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("", encoding="utf-8")
    profile = scan_project(tmp_path)
    assert "src/main.py" in profile.tree
    assert "node_modules" not in profile.tree

def test_detects_python(tmp_path):
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    profile = scan_project(tmp_path)
    assert "python" in profile.languages

def test_profile_summary_is_str(tmp_path):
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    profile = scan_project(tmp_path)
    assert isinstance(profile.summary(), str)
    assert profile.summary()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_scanner.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/context/__init__.py
```

```python
# src/pycode_agent/context/scanner.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}
_LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
}
MAX_TREE_ENTRIES = 300


@dataclass
class ProjectProfile:
    root: Path
    tree: list[str] = field(default_factory=list)
    languages: set[str] = field(default_factory=set)
    markers: list[str] = field(default_factory=list)

    def summary(self) -> str:
        langs = ", ".join(sorted(self.languages)) or "unknown"
        markers = ", ".join(self.markers) or "none"
        head = "\n".join(self.tree[:60])
        return (f"Languages: {langs}\nMarkers: {markers}\n"
                f"Files ({len(self.tree)} shown, capped):\n{head}")


def scan_project(root: Path) -> ProjectProfile:
    root = Path(root)
    profile = ProjectProfile(root=root)
    marker_files = {"pyproject.toml", "package.json", "go.mod", "Cargo.toml", "pom.xml"}
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if len(profile.tree) < MAX_TREE_ENTRIES:
                profile.tree.append(rel)
            lang = _LANG_BY_EXT.get(path.suffix)
            if lang:
                profile.languages.add(lang)
            if path.name in marker_files:
                profile.markers.append(path.name)
    return profile
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_scanner.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/context tests/unit/test_scanner.py
git commit -m "feat: project scanner with ignore rules and profile"
```

---

### Task 13: 审计日志 logs/audit.py

**Files:**
- Create: `src/pycode_agent/logs/__init__.py`
- Create: `src/pycode_agent/logs/audit.py`
- Test: `tests/unit/test_audit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_audit.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_audit.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/logs/__init__.py
```

```python
# src/pycode_agent/logs/audit.py
from __future__ import annotations
import json
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, **fields) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fields, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_audit.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/logs tests/unit/test_audit.py
git commit -m "feat: JSONL audit log"
```

---

### Task 14: Agent Loop core/agent.py

**Files:**
- Create: `src/pycode_agent/core/agent.py`
- Test: `tests/integration/__init__.py`
- Test: `tests/integration/test_agent_loop.py`

Agent Loop 把前面所有部件接起来:Provider 产出 tool_calls → Policy 判定 → (CONFIRM 时)Approval → 执行 → 审计 → 回填。关键不变量见 spec §4。

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/__init__.py
```

```python
# tests/integration/test_agent_loop.py
from pathlib import Path
from pydantic import BaseModel
from pycode_agent.core.agent import Agent
from pycode_agent.core.messages import ToolCall, ToolResult
from pycode_agent.model.fake import FakeLLMProvider
from pycode_agent.model.base import LLMResponse
from pycode_agent.tools.base import Tool, Risk, ToolContext
from pycode_agent.tools.registry import ToolRegistry
from pycode_agent.security.policy import Policy
from pycode_agent.security.approval import Approval
from pycode_agent.utils.diff import PatchManager
from pycode_agent.logs.audit import AuditLog


class EchoArgs(BaseModel):
    text: str

class EchoTool(Tool):
    name = "echo"; description = "echo"; args_model = EchoArgs; risk = Risk.LOW
    def run(self, args, ctx): return ToolResult(ok=True, content=args.text.upper())

class DangerArgs(BaseModel):
    pass

class DangerTool(Tool):
    name = "danger"; description = "high risk"; args_model = DangerArgs; risk = Risk.HIGH
    def __init__(self): self.ran = False
    def run(self, args, ctx):
        self.ran = True
        return ToolResult(ok=True, content="did danger")


def _agent(tmp_path, script, *, tools, mode="confirm", auto_yes=True):
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    ctx = ToolContext(project_dir=tmp_path, patch_manager=PatchManager())
    return Agent(
        provider=FakeLLMProvider(script=script),
        registry=reg,
        policy=Policy(mode=mode),
        approval=Approval(auto_yes=auto_yes),
        audit=AuditLog(tmp_path / "audit.jsonl"),
        ctx=ctx,
        max_turns=8,
    )

def test_loop_runs_low_risk_tool_then_answers(tmp_path):
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "hi"})]),
        LLMResponse(text="final answer"),
    ]
    agent = _agent(tmp_path, script, tools=[EchoTool()])
    result = agent.run("please echo")
    assert result == "final answer"

def test_confirm_yes_runs_high_risk(tmp_path):
    danger = DangerTool()
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="danger", arguments={})]),
        LLMResponse(text="ok done"),
    ]
    agent = _agent(tmp_path, script, tools=[danger], auto_yes=True)
    agent.run("do danger")
    assert danger.ran is True

def test_confirm_no_skips_high_risk(tmp_path):
    danger = DangerTool()
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="danger", arguments={})]),
        LLMResponse(text="understood, skipped"),
    ]
    agent = _agent(tmp_path, script, tools=[danger], auto_yes=False)
    result = agent.run("do danger")
    assert danger.ran is False
    assert result == "understood, skipped"

def test_readonly_denies_high_risk(tmp_path):
    danger = DangerTool()
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="danger", arguments={})]),
        LLMResponse(text="cannot in readonly"),
    ]
    agent = _agent(tmp_path, script, tools=[danger], mode="readonly")
    agent.run("do danger")
    assert danger.ran is False

def test_max_turns_terminates(tmp_path):
    # provider always asks for a tool call -> would loop forever without cap
    script = [LLMResponse(tool_calls=[ToolCall(id=f"c{i}", name="echo", arguments={"text": "x"})]) for i in range(20)]
    agent = _agent(tmp_path, script, tools=[EchoTool()])
    result = agent.run("loop")
    assert "max turns" in result.lower()

def test_audit_written(tmp_path):
    script = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "hi"})]),
        LLMResponse(text="done"),
    ]
    agent = _agent(tmp_path, script, tools=[EchoTool()])
    agent.run("go")
    assert (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_agent_loop.py -v`
Expected: FAIL (ModuleNotFoundError: pycode_agent.core.agent)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/core/agent.py
from __future__ import annotations
from pycode_agent.core.messages import Message
from pycode_agent.model.base import LLMProvider
from pycode_agent.tools.registry import ToolRegistry
from pycode_agent.tools.base import ToolContext
from pycode_agent.security.policy import Policy, Decision
from pycode_agent.security.approval import Approval
from pycode_agent.logs.audit import AuditLog

SYSTEM_PROMPT = (
    "You are PyCodeAgent, a terminal coding assistant. "
    "Use the provided tools to read, search, and modify the project. "
    "High-risk actions require user confirmation. Be concise."
)


class Agent:
    def __init__(self, *, provider: LLMProvider, registry: ToolRegistry,
                 policy: Policy, approval: Approval, audit: AuditLog,
                 ctx: ToolContext, max_turns: int = 12, max_tool_calls: int = 40,
                 system_prefix: str = ""):
        self.provider = provider
        self.registry = registry
        self.policy = policy
        self.approval = approval
        self.audit = audit
        self.ctx = ctx
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.system_prefix = system_prefix
        self.messages: list[Message] = [
            Message(role="system", content=SYSTEM_PROMPT + ("\n\n" + system_prefix if system_prefix else ""))
        ]

    def run(self, user_input: str) -> str:
        self.messages.append(Message(role="user", content=user_input))
        tool_call_count = 0
        for _ in range(self.max_turns):
            resp = self.provider.chat(messages=self.messages, tools=self.registry.schemas())
            if not resp.tool_calls:
                text = resp.text or ""
                self.messages.append(Message(role="assistant", content=text))
                return text
            self.messages.append(Message(role="assistant", tool_calls=resp.tool_calls))
            for call in resp.tool_calls:
                tool_call_count += 1
                result = self._handle_call(call)
                self.messages.append(
                    Message(role="tool", tool_call_id=call.id, content=self._render(result))
                )
                if tool_call_count >= self.max_tool_calls:
                    return "Stopped: reached max tool calls."
        return "Stopped: reached max turns without a final answer."

    def _handle_call(self, call):
        tool = self.registry.get(call.name)
        if tool is None:
            from pycode_agent.core.messages import ToolResult
            res = ToolResult(ok=False, error=f"unknown tool: {call.name}")
            self.audit.record(event="tool_call", tool=call.name, arguments=call.arguments,
                              decision="deny", ok=False, error=res.error)
            return res
        decision = self.policy.evaluate(tool.risk)
        if decision == Decision.DENY:
            from pycode_agent.core.messages import ToolResult
            res = ToolResult(ok=False, error="denied by permission policy")
        elif decision == Decision.CONFIRM:
            approved = self.approval.ask(f"运行工具 {call.name}", str(call.arguments))
            if not approved:
                from pycode_agent.core.messages import ToolResult
                res = ToolResult(ok=False, error="user rejected")
            else:
                res = self.registry.dispatch(call.name, call.arguments, self.ctx)
        else:
            res = self.registry.dispatch(call.name, call.arguments, self.ctx)
        self.audit.record(event="tool_call", tool=call.name, arguments=call.arguments,
                          decision=decision.value, ok=res.ok, error=res.error)
        return res

    @staticmethod
    def _render(result) -> str:
        if result.ok:
            return result.content
        return f"ERROR: {result.error}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_agent_loop.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/core/agent.py tests/integration
git commit -m "feat: Agent Loop with policy, approval, audit, turn caps"
```

---

### Task 15: OpenAI 兼容 Provider

**Files:**
- Create: `src/pycode_agent/model/openai_compatible.py`
- Test: `tests/unit/test_openai_provider.py`

用 `httpx.MockTransport` 注入假响应,避免真实网络。

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_openai_provider.py
import json
import httpx
from pycode_agent.core.messages import Message
from pycode_agent.model.openai_compatible import OpenAICompatibleProvider
from pycode_agent.model.errors import AuthError, RateLimitError

def _provider(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.test/v1")
    return OpenAICompatibleProvider(model="m", api_key="k", client=client)

def test_parses_text_response():
    def handler(req):
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hello"}}]
        })
    p = _provider(handler)
    r = p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert r.text == "hello" and r.tool_calls == []

def test_parses_tool_calls():
    def handler(req):
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "read_file", "arguments": json.dumps({"path": "a.py"})}}
            ]}}]
        })
    p = _provider(handler)
    r = p.chat(messages=[Message(role="user", content="hi")], tools=[])
    assert r.tool_calls[0].name == "read_file"
    assert r.tool_calls[0].arguments == {"path": "a.py"}

def test_auth_error_mapped():
    def handler(req):
        return httpx.Response(401, json={"error": "bad key"})
    p = _provider(handler)
    try:
        p.chat(messages=[Message(role="user", content="hi")], tools=[])
        assert False, "should have raised"
    except AuthError:
        pass

def test_rate_limit_mapped():
    def handler(req):
        return httpx.Response(429, json={"error": "slow down"})
    p = _provider(handler)
    try:
        p.chat(messages=[Message(role="user", content="hi")], tools=[])
        assert False
    except RateLimitError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_openai_provider.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/model/openai_compatible.py
from __future__ import annotations
import json
import httpx
from pycode_agent.core.messages import Message, ToolCall
from .base import LLMProvider, LLMResponse
from .errors import AuthError, RateLimitError, TimeoutError, NetworkError, ProviderError


def _message_to_dict(m: Message) -> dict:
    d: dict = {"role": m.role}
    d["content"] = m.content
    if m.tool_calls:
        d["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
            for tc in m.tool_calls
        ]
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, *, model: str, api_key: str | None, base_url: str = "",
                 timeout: int = 120, client: httpx.Client | None = None):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)

    def chat(self, *, messages: list[Message], tools: list[dict]) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [_message_to_dict(m) for m in messages],
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            resp = self._client.post("/chat/completions", json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise TimeoutError(str(e)) from e
        except httpx.HTTPError as e:
            raise NetworkError(str(e)) from e

        if resp.status_code == 401:
            raise AuthError("authentication failed")
        if resp.status_code == 429:
            raise RateLimitError("rate limited")
        if resp.status_code >= 400:
            raise ProviderError(f"http {resp.status_code}: {resp.text[:200]}")

        msg = resp.json()["choices"][0]["message"]
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc["function"]
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn["name"], arguments=arguments))
        return LLMResponse(text=msg.get("content"), tool_calls=tool_calls)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_openai_provider.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/model/openai_compatible.py tests/unit/test_openai_provider.py
git commit -m "feat: OpenAI-compatible provider with error mapping"
```

---

### Task 16: CLI 入口 + 非交互模式 + REPL

**Files:**
- Create: `src/pycode_agent/cli/__init__.py`
- Create: `src/pycode_agent/cli/builder.py`(组装 Agent 的工厂)
- Create: `src/pycode_agent/cli/main.py`
- Create: `src/pycode_agent/cli/repl.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_cli.py
from typer.testing import CliRunner
from pycode_agent.cli.main import app

runner = CliRunner()

def test_config_list_runs(tmp_path):
    result = runner.invoke(app, ["config", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "mode" in result.stdout.lower()

def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
```

非交互 `-p` 的端到端(用 Fake provider)放在 builder 测试:

```python
# 追加到 tests/integration/test_cli.py
from pathlib import Path
from pycode_agent.cli.builder import build_agent_with_provider
from pycode_agent.model.fake import FakeLLMProvider
from pycode_agent.model.base import LLMResponse
from pycode_agent.config.settings import Settings

def test_build_agent_runs_with_fake(tmp_path):
    provider = FakeLLMProvider(script=[LLMResponse(text="hi from fake")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings(), auto_yes=True
    )
    assert agent.run("hello") == "hi from fake"

def test_build_agent_registers_core_tools(tmp_path):
    provider = FakeLLMProvider(script=[LLMResponse(text="x")])
    agent = build_agent_with_provider(
        provider=provider, project_dir=tmp_path, settings=Settings(), auto_yes=True
    )
    names = {s["function"]["name"] for s in agent.registry.schemas()}
    assert {"read_file", "list_dir", "search_text", "write_file", "edit_file",
            "run_shell", "git_status", "git_diff", "memory_read", "memory_write"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_cli.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write implementation**

```python
# src/pycode_agent/cli/__init__.py
```

```python
# src/pycode_agent/cli/builder.py
from __future__ import annotations
from pathlib import Path
from pycode_agent.config.settings import Settings
from pycode_agent.core.agent import Agent
from pycode_agent.model.base import LLMProvider
from pycode_agent.tools.base import ToolContext
from pycode_agent.tools.registry import ToolRegistry
from pycode_agent.tools.file_tools import ReadFile, ListDir, SearchText, WriteFile, EditFile
from pycode_agent.tools.shell_tools import RunShell
from pycode_agent.tools.git_tools import GitStatus, GitDiff
from pycode_agent.tools.memory_tools import MemoryRead, MemoryWrite
from pycode_agent.security.policy import Policy
from pycode_agent.security.approval import Approval
from pycode_agent.logs.audit import AuditLog
from pycode_agent.utils.diff import PatchManager
from pycode_agent.context.scanner import scan_project


def _build_registry(settings: Settings) -> ToolRegistry:
    reg = ToolRegistry()
    for tool in (ReadFile(), ListDir(), SearchText(), WriteFile(), EditFile(),
                 GitStatus(), GitDiff(), MemoryRead(), MemoryWrite()):
        reg.register(tool)
    if settings.security.allow_shell:
        reg.register(RunShell())
    return reg


def build_agent_with_provider(*, provider: LLMProvider, project_dir: Path,
                              settings: Settings, auto_yes: bool = False) -> Agent:
    project_dir = Path(project_dir)
    pm = PatchManager()
    ctx = ToolContext(project_dir=project_dir, settings=settings, patch_manager=pm)
    profile = scan_project(project_dir)
    return Agent(
        provider=provider,
        registry=_build_registry(settings),
        policy=Policy(mode=settings.security.mode),
        approval=Approval(auto_yes=auto_yes),
        audit=AuditLog(project_dir / ".pycode" / "audit.jsonl"),
        ctx=ctx,
        max_turns=settings.agent.max_turns,
        max_tool_calls=settings.agent.max_tool_calls,
        system_prefix="Project profile:\n" + profile.summary(),
    )
```

```python
# src/pycode_agent/cli/main.py
from __future__ import annotations
import sys
from pathlib import Path
import typer
from pycode_agent import __version__
from pycode_agent.config.loader import load_settings
from pycode_agent.cli.builder import build_agent_with_provider

app = typer.Typer(add_completion=False, help="PyCodeAgent — terminal coding assistant")
config_app = typer.Typer(help="管理配置")
app.add_typer(config_app, name="config")


def _make_provider(settings):
    from pycode_agent.model.openai_compatible import OpenAICompatibleProvider
    return OpenAICompatibleProvider(
        model=settings.model.name,
        api_key=settings.model.api_key,
        base_url=settings.model.base_url,
        timeout=settings.model.timeout,
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="显示版本"),
    prompt: str = typer.Option(None, "-p", "--prompt", help="非交互模式:执行单条指令"),
    project_dir: Path = typer.Option(Path("."), "--project-dir", help="项目目录"),
    no_tools: bool = typer.Option(False, "--no-tools", help="禁用工具调用"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="自动确认(危险)"),
):
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is not None:
        return

    settings = load_settings(project_dir)
    if prompt is not None:
        stdin_data = "" if sys.stdin.isatty() else sys.stdin.read()
        full = prompt if not stdin_data else f"{prompt}\n\n---\n{stdin_data}"
        provider = _make_provider(settings)
        agent = build_agent_with_provider(
            provider=provider, project_dir=project_dir, settings=settings,
            auto_yes=auto_approve,
        )
        if no_tools:
            agent.registry = type(agent.registry)()  # empty registry
        try:
            out = agent.run(full)
        except Exception as e:  # noqa
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(out)
        raise typer.Exit(code=0)

    # no prompt, no subcommand -> interactive REPL
    from pycode_agent.cli.repl import run_repl
    run_repl(project_dir=project_dir, settings=settings, provider_factory=_make_provider)


@config_app.command("list")
def config_list(project_dir: Path = typer.Option(Path("."), "--project-dir")):
    settings = load_settings(project_dir)
    typer.echo(f"model.name    = {settings.model.name}")
    typer.echo(f"model.base_url= {settings.model.base_url}")
    typer.echo(f"security.mode = {settings.security.mode}")
    typer.echo(f"allow_shell   = {settings.security.allow_shell}")
```

```python
# src/pycode_agent/cli/repl.py
from __future__ import annotations
from pathlib import Path
from rich.console import Console
from pycode_agent.cli.builder import build_agent_with_provider

console = Console()


def run_repl(*, project_dir: Path, settings, provider_factory):
    console.print("[bold green]PyCodeAgent[/] — 输入 /exit 退出")
    provider = provider_factory(settings)
    agent = build_agent_with_provider(
        provider=provider, project_dir=project_dir, settings=settings, auto_yes=False
    )
    while True:
        try:
            user = console.input("[bold cyan]You >[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nbye")
            return
        if user in ("/exit", "/quit"):
            return
        if not user:
            continue
        try:
            answer = agent.run(user)
        except Exception as e:  # noqa
            console.print(f"[red]error:[/] {e}")
            continue
        console.print(f"[bold magenta]Agent >[/] {answer}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_cli.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pycode_agent/cli tests/integration/test_cli.py
git commit -m "feat: CLI entry, non-interactive mode, REPL, agent builder"
```

---

### Task 17: 收尾 — 全量测试 + README + 手动冒烟

**Files:**
- Create: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: 运行全部测试**

Run: `pytest -v`
Expected: 所有测试 PASS(约 40+ 用例)。

- [ ] **Step 2: 写 .gitignore**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.pycode/
.venv/
dist/
build/
```

- [ ] **Step 3: 写 README.md**

```markdown
# PyCodeAgent

洁净室重实现的 Claude Code-like 终端编程助手(垂直切片)。

## 安装
\`\`\`bash
pip install -e ".[dev]"
\`\`\`

## 配置
设置环境变量或 `~/.pycode/config.toml`:
\`\`\`bash
export PYCODE_MODEL_NAME=your-model
export PYCODE_MODEL_BASE_URL=https://api.example.com/v1
export PYCODE_API_KEY=sk-...
\`\`\`

## 使用
\`\`\`bash
pycode                                   # 交互式 REPL
pycode -p "解释这个项目的结构"            # 非交互
cat error.log | pycode -p "分析这个报错"  # 管道输入
pycode config list                       # 查看配置
\`\`\`

## 安全
默认 `confirm` 权限模式:高风险操作(写文件、执行 shell)需确认。
敏感文件(.env、密钥)默认拒读;危险命令黑名单拦截。
所有工具调用写入 `.pycode/audit.jsonl`。

## 测试
\`\`\`bash
pytest -v
\`\`\`
```

- [ ] **Step 4: 手动冒烟测试**

Run:
```bash
pycode --version
pycode config list
PYCODE_MODEL_NAME=x pycode config list
```
Expected: 版本号输出;配置项正确显示。

- [ ] **Step 5: Commit**

```bash
git add README.md .gitignore
git commit -m "docs: README, gitignore; vertical slice complete"
```

---

## Self-Review(计划对照 spec)

**Spec 覆盖检查:**
- §1 范围(CLI/配置/Provider/Agent Loop/工具/安全/审计/上下文/记忆/测试)→ Tasks 1–17 全覆盖 ✓
- §4 Agent Loop 不变量(必过 policy+approval、全审计、拒绝回填、异常不崩溃)→ Task 14 测试覆盖 ✓
- §6 工具集 10 个 + 四权限模式 → Tasks 6,9,10,11 ✓
- §6 敏感文件/Shell 黑名单/PatchManager 回滚 → Tasks 5,7,9,10 ✓
- §7 配置优先级 → Task 3 ✓
- §8 错误处理(Provider 分类异常、限流映射)→ Task 15 ✓(重试退避为增强项,切片用直接映射,留 Beta)
- §9 非交互模式(-p、stdin、--no-tools、退出码)→ Task 16 ✓
- §10 测试策略(Fake 驱动 Loop、关键场景)→ Tasks 4,14 ✓
- §12 验收标准 → Task 17 冒烟 + 全量测试 ✓

**占位符扫描:** 无 TBD/TODO;每个代码步骤含完整代码。

**类型一致性:** `ToolResult`/`ToolCall`/`Message` 字段贯穿一致;`Tool.run(args, ctx)` 签名一致;`Policy.evaluate(risk)→Decision`、`Approval.ask(title, detail)→bool`、`PatchManager.apply/rollback`、`registry.dispatch/schemas/get` 在各任务间一致。

**已知取舍(对齐 spec YAGNI):** 限流指数退避、上下文压缩、unified-diff 补丁解析(切片用整文件替换)、流式输出留待 Beta。
