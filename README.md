# PyCodeAgent

洁净室重实现的 Claude Code-like 终端编程助手(垂直切片)。

> 本项目独立设计实现,不复制、不反编译任何非授权源码;功能目标来自公开可观察行为与通用开发者需求。

## 安装

```bash
pip install -e ".[dev]"
```

要求 Python 3.11+。

## 配置

通过环境变量或 `~/.pycode/config.toml`(用户级)/ `.pycode/config.toml`(项目级)配置:

```bash
export PYCODE_MODEL_NAME=your-model
export PYCODE_MODEL_BASE_URL=https://api.example.com/v1
export PYCODE_MODEL_API_KEY=sk-...
```

配置优先级:命令行参数 > 项目配置 > 用户配置 > 环境变量。

`base_url` 可填到 API 根(如 `.../v1`)或完整端点(`.../v1/chat/completions`),两种写法都受支持。

## 使用

```bash
pycode                                   # 交互式 REPL(/help 查看命令: /tools /tokens /memory /diff /undo 等)
pycode -p "解释这个项目的结构"            # 非交互单次执行
cat error.log | pycode -p "分析这个报错"  # 管道输入
pycode -p "写 commit message" --no-tools  # 禁用工具调用
pycode -p "审查当前 diff" --json          # 结构化 JSON 输出
pycode -p "重构这个模块" --dry-run         # 高风险操作只预览不执行
pycode -p "..." --max-turns 3 --quiet     # 限制循环轮数 / 精简输出
pycode config list                       # 查看当前配置
pycode config get security.mode          # 查看单项配置及来源
pycode config set security.mode workspace # 写入项目配置
pycode --continue                        # 恢复最近一次会话
pycode --resume 20260601-094530-a3f1     # 按 id 恢复指定会话
pycode sessions list                     # 列出本项目所有会话
pycode --version
```

非交互退出码:`0` 成功 / `1` 错误 / `2` 工具被拒绝且无法继续。

## 安全模型

四种权限模式(默认 `confirm`):

| 模式 | 行为 |
|---|---|
| `readonly` | 仅只读工具可用,写/shell 一律拒绝 |
| `confirm` | 默认。高风险操作(写文件、执行 shell)逐次确认 |
| `workspace` | 工作区内低风险写免确认,危险命令仍确认 |
| `dangerous` | 显式授权,全放行 |

- 敏感文件(`.env`、密钥、证书、token)默认拒读拒写。
- 危险 Shell 命令(`rm -rf /`、`sudo`、fork 炸弹等)由黑名单强制拦截;`git push` 默认禁用(`security.allow_git_push` 开启)。
- 文件路径限定在项目根目录内,拒绝穿越(`../`)与越界绝对路径。
- 文件修改经 PatchManager:展示 diff → 确认 → 应用,可回滚最近一次变更。
- 所有工具调用(含被拒绝的)写入 `.pycode/audit.jsonl`。

## 工具集

读类(低风险):`read_file` `list_dir` `search_text` `git_status` `git_diff` `memory_read`
写/执行类(高风险,需确认):`write_file` `edit_file` `str_replace` `run_shell` `memory_write`

## 测试

```bash
pytest -v
```

## 架构

```
CLI / REPL  →  Agent Loop  →  { LLMProvider, ToolRegistry, ContextScanner }
                                  + Policy / Approval / AuditLog
```

- `model/`:`LLMProvider` 抽象,含 OpenAI 兼容实现(分类异常 + 限流/网络错误指数退避重试)与可脚本化的 `FakeLLMProvider`(离线测试驱动 Agent Loop)。
- `core/agent.py`:多轮 思考→工具调用→观察 循环,带轮数/调用上限。
- `tools/`:统一 `Tool` 基类 + 注册表 + 文件/Shell/Git/记忆工具。
- `security/`:权限策略与确认交互。

## 已知限制(垂直切片范围)

切片聚焦核心主链路。已支持:LLM 摘要式上下文压缩(超预算自动触发)、str_replace 局部编辑(唯一串替换)、多级 undo、输入历史与 slash 命令补全、流式输出、多会话持久化与恢复(--continue/--resume/sessions list、REPL 内 /sessions /resume)。以下留待后续:unified-diff hunk 解析(当前为整文件替换 / 唯一串替换)、完整 TUI、MCP/LSP。
