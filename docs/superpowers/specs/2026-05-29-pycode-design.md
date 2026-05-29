# PyCodeAgent — 可运行垂直切片设计文档

- **日期**: 2026-05-29
- **范围**: 可运行垂直切片(MVP 的核心主链路,可真实运行 + 带测试)
- **包名**: `pycode_agent` · CLI 命令 `pycode` · Python 3.11+
- **依据**: `项目规划书.md`(洁净室重实现一个 Claude Code-like 智能编程 CLI)

> 合规原则:本项目采用洁净室重实现,不复制、不反编译、不依赖任何非授权源码。
> 所有架构、代码、测试均由本项目独立设计完成,功能目标来自公开可观察行为与通用开发者需求。

---

## 1. 目标与非目标

### 本切片交付(In Scope)
- CLI 入口:`pycode chat`(交互式 REPL)、`pycode -p "..."`(非交互)、`pycode config`。
- 配置系统:命令行参数 > 项目配置 > 用户配置 > 环境变量,基于 `pydantic-settings`。
- 模型接入:`LLMProvider` 抽象 + `OpenAICompatibleProvider`(原生 tool-calling)+ `FakeLLMProvider`(可脚本化,离线测试)。
- Agent Loop:多轮思考→工具调用→观察→继续,带最大轮数/工具调用上限。
- 工具集:`read_file`、`list_dir`、`search_text`、`write_file`、`edit_file`、`run_shell`、`git_status`、`git_diff`、`memory_read`、`memory_write`。
- 安全:四种权限模式(默认 `confirm`)、敏感文件拦截、Shell 黑名单、diff 预览 + 用户确认、最近一次变更可回滚。
- 审计日志:JSONL 记录模型建议、工具调用、文件变更、用户确认结果。
- 项目上下文:扫描目录(遵循 `.gitignore` + 内置忽略)、生成轻量项目画像。
- 项目记忆:`.pycode/memory.md` 读写(写入需确认)。
- 测试:单元 + 集成(Fake Provider 驱动 Loop)+ 关键场景。

### 非目标(Out of Scope,留待 Beta/后续)
- 完整 TUI(Textual)、MCP、LSP、IDE 集成、多 Agent、插件市场、代码索引、向量检索、OAuth 登录、异步架构。

### 有意的取舍(YAGNI)
- **工具调用机制**: 仅原生 function-calling(方案 A1)。`LLMProvider` 接口预留扩展位,日后可加文本协议(ReAct)回退,但本切片不实现。
- **同步核心**: 用同步 `httpx` + 流式 `iter_lines`,不引入 asyncio。异步留待引入 TUI/MCP 时再上。

---

## 2. 整体架构

分层架构:

```
CLI / REPL 层        cli/main.py, cli/repl.py
   │
App / 会话层         core/session.py
   │
Agent Engine         core/agent.py  (Agent Loop)
   ├── Provider 层    model/  (base, openai_compatible, fake)
   ├── ToolRegistry   tools/  (registry + 各工具)
   └── ContextManager context/ (scanner, selector)
        │
   横切关注:security/(policy, approval)  logs/(audit)  utils/(diff, paths)
```

- **CLI/REPL 层**: 用户交互、命令路由、流式输出渲染。
- **会话层**: 维护 messages 历史、项目画像、会话生命周期。
- **Agent Engine**: 任务循环与工具编排(见 §4)。
- **Provider 层**: 屏蔽不同模型服务差异,统一消息/工具格式。
- **ToolRegistry**: 统一注册工具、暴露 JSON Schema、按名分发执行。
- **ContextManager**: 项目扫描与上下文选择。
- **security**: 权限判定与确认交互。
- **logs**: 审计与会话转录。

---

## 3. 目录结构

```text
pycode_agent/
  pyproject.toml
  README.md
  src/pycode_agent/
    __init__.py
    cli/
      __init__.py
      main.py          # Typer 入口: chat / -p / config
      repl.py          # 交互式 REPL(简洁版,非完整 TUI)
    core/
      agent.py         # Agent Loop
      session.py       # 会话状态、messages 历史
      messages.py      # Message / ToolCall / ToolResult 数据模型
    model/
      base.py          # LLMProvider 抽象接口
      openai_compatible.py
      fake.py          # FakeLLMProvider(可脚本化)
      errors.py        # 分类异常
    tools/
      base.py          # Tool 抽象基类 + Risk 枚举
      registry.py      # ToolRegistry
      file_tools.py    # read_file / list_dir / search_text / write_file / edit_file
      shell_tools.py   # run_shell
      git_tools.py     # git_status / git_diff
      memory_tools.py  # memory_read / memory_write
    context/
      scanner.py       # 项目扫描 + .gitignore + 内置忽略
      selector.py      # 上下文选择(显式 + 检索)
    config/
      settings.py      # pydantic-settings 模型
      loader.py        # 多来源合并(CLI > 项目 > 用户 > 环境)
    security/
      policy.py        # 四种权限模式 + 风险判定
      approval.py      # 确认交互(展示 diff/命令/风险)
    logs/
      audit.py         # JSONL 审计日志
    utils/
      diff.py          # PatchManager(unified diff 解析/应用/回滚)
      paths.py         # 路径安全、敏感文件判定
  tests/
    unit/
    integration/
    fixtures/
```

---

## 4. 核心数据流(Agent Loop)

```
用户输入 task
  → Session 组装 messages = [system_prompt, ...history, user_msg]
  → ContextManager 注入项目画像(语言栈 / 入口 / 目录树摘要)
  → 循环(turn = 0; turn < max_turns; turn++):
       resp = Provider.chat(messages, tools=registry.schemas())
       ├─ 返回纯文本           → 输出给用户,break
       └─ 返回 tool_calls      →
            for call in tool_calls:
              decision = Policy.evaluate(call.tool, call.args)
              if decision == DENY:
                  result = ToolResult(ok=False, error="policy denied")
              elif decision == CONFIRM:
                  approved = Approval.ask(展示 diff / 命令 / 风险)
                  if not approved:
                      result = ToolResult(ok=False, error="user rejected")
                  else:
                      result = tool.run(call.args, ctx)
              else:  # ALLOW
                  result = tool.run(call.args, ctx)
              AuditLog.record(call, result, decision, user_choice)
              messages.append(role="tool", tool_call_id=call.id, content=result)
       继续下一轮
  → turn >= max_turns 或 tool_calls 累计 >= max_tool_calls
       → 安全终止 + 向用户说明已达上限
```

### 关键不变量
1. 任何高风险工具执行前**必过** `Policy.evaluate` + 必要时 `Approval.ask`。
2. 每个 tool_call(含被拒绝的)都写入审计日志。
3. 用户拒绝 → **不执行**,把"用户拒绝"作为 tool 结果回填,让模型调整方案而非崩溃。
4. 工具异常 → 转成 `ToolResult(ok=False, error=...)` 回填,**不**中断 Loop。

---

## 5. 数据模型(core/messages.py)

```python
class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None   # assistant 发起
    tool_call_id: str | None = None            # role=tool 时回填

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict          # 已解析的 JSON 参数

class ToolResult(BaseModel):
    ok: bool
    content: str = ""        # 回填给模型的文本
    error: str | None = None
    meta: dict = {}          # 例如 shell 的 exit_code/duration
```

---

## 6. 工具接口与权限模型

### 工具基类(tools/base.py)
```python
class Risk(IntEnum):
    LOW = 0      # 只读,直接执行
    MEDIUM = 1   # 写工作区,按模式判定
    HIGH = 2     # 写文件/执行命令,默认确认

class Tool(ABC):
    name: str
    description: str
    args_model: type[BaseModel]   # Pydantic 参数校验
    risk: Risk
    @abstractmethod
    def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...
    def json_schema(self) -> dict: ...   # 供 Provider 工具列表
```

### 切片工具集
| 工具 | 风险 | 行为 |
|---|---|---|
| `read_file` | LOW | 读文件(敏感文件拦截) |
| `list_dir` | LOW | 列目录(遵循忽略规则) |
| `search_text` | LOW | ripgrep 优先,Python 回退 |
| `write_file` | HIGH | 写/覆盖,diff 预览 + 确认 |
| `edit_file` | HIGH | unified diff,经 PatchManager 应用 + 确认 |
| `run_shell` | 动态 | 按命令分级(见下) |
| `git_status` | LOW | 只读 |
| `git_diff` | LOW | 只读;可生成 commit message |
| `memory_read` | LOW | 读 `.pycode/memory.md` |
| `memory_write` | HIGH | 写记忆,确认 |

### 权限四模式(默认 `confirm`)
| 模式 | 说明 |
|---|---|
| `readonly` | 仅 LOW 工具可用;写/shell 一律拒绝 |
| `confirm` | 默认。HIGH 风险逐次确认 |
| `workspace` | 工作区内低风险写免确认;危险命令仍确认 |
| `dangerous` | 显式授权,全放行(临时自动化) |

### 安全细则
- **敏感文件**(`paths.py`): 默认拒读 `.env`、`*.pem`、`*.key`、证书、`*token*`、云凭据。
- **Shell 黑名单**(强制拒绝): `rm -rf /`、`sudo`、`mkfs`、fork 炸弹、写系统目录、上传密钥等。
- **`git push`**: 默认禁用,需显式开启。
- **PatchManager**: 解析 unified diff → 校验上下文 → 展示 diff → 确认 → 应用 + 生成回滚补丁。冲突时**绝不破坏原文件**,返回冲突错误。支持撤销最近一次变更。

---

## 7. 配置系统

优先级:**命令行参数 > 项目配置(`.pycode/config.toml`)> 用户配置(`~/.pycode/config.toml`)> 环境变量默认值**。

```toml
[model]
provider = "openai_compatible"
name = "default-coding-model"
base_url = "https://api.example.com/v1"
timeout = 120
stream = true

[security]
mode = "confirm"            # readonly | confirm | workspace | dangerous
allow_shell = true
allow_git_push = false

[context]
max_files = 200
max_tokens = 120000
enable_project_memory = true
```

API Key 来源:环境变量 `PYCODE_API_KEY`(或配置文件),不复用任何其他工具的本地凭据。
命令:`pycode config get/set/list`,显示配置来源。

---

## 8. 错误处理

- **Provider 层**(`model/errors.py`)分类异常:`AuthError`、`RateLimitError`、`TimeoutError`、`ContextOverflowError`、`NetworkError`、`ToolFormatError`。
- 限流 / 网络错误带**指数退避重试**(上限可配)。
- 工具异常不崩溃 Loop → `ToolResult(ok=False, error=...)` 回填。
- Shell 超时 → 杀进程,返回 `timed_out=True`。
- Patch 冲突 → 不写文件,返回冲突错误。
- 上下文超长 → 报 `ContextOverflowError`,切片阶段提示用户(压缩留待 Beta)。

---

## 9. 非交互模式

```bash
pycode -p "解释这个报错" < error.log
pycode -p "根据 git diff 写 commit message" --no-tools
pycode -p "审查当前 diff" --json
```

参数:`--json`、`--quiet`、`--verbose`、`--max-turns N`、`--no-tools`、`--dry-run`。
退出码:`0` 成功 / `1` 错误 / `2` 用户拒绝且无法继续。

---

## 10. 测试策略

- **单元**: 配置优先级合并、工具参数校验、PatchManager(应用/冲突/回滚)、Policy 判定、敏感文件拦截、消息格式转换、Shell 黑名单。
- **集成**: `FakeLLMProvider`(预置 tool_call 脚本)驱动完整 Agent Loop;非交互退出码;Git diff 分析。
- **关键场景**: 用户拒绝→不执行;Shell 超时→终止进程;patch 冲突→原文件不坏;敏感文件→默认不可读;`-p` 退出码正确;超过 max_turns→安全终止。
- **E2E**: 临时项目里 读取 → 编辑 → 回滚。

`FakeLLMProvider` 是测试 Agent Loop 的关键:接收一个"响应脚本"(纯文本 / tool_calls 序列),无需真实 API。

---

## 11. 技术选型

| 模块 | 技术 |
|---|---|
| CLI | Typer |
| 配置 | pydantic-settings |
| HTTP | httpx(同步 + 流式) |
| 数据模型 | Pydantic v2 |
| 搜索 | ripgrep subprocess,Python 回退 |
| Diff | 自研 PatchManager(基于 unified diff) |
| 终端渲染 | rich(REPL 输出 / diff 高亮) |
| 测试 | pytest |

---

## 12. 验收标准(本切片)

1. `pip install -e .` 后 `pycode` 可启动。
2. 可配置 API Key 与 base_url。
3. 进入项目目录后,`pycode chat` 能回答项目结构问题、读文件、搜索代码。
4. 模型提出文件修改 → 展示 diff → 确认后才写入;可撤销最近一次变更。
5. `pycode -p "..."` 完成非交互问答,退出码正确。
6. `run_shell` 受权限与黑名单约束;危险命令被拒。
7. 敏感文件默认不可读。
8. 所有工具调用写入审计日志。
9. `pytest` 全绿,Fake Provider 能确定性驱动 Loop。
