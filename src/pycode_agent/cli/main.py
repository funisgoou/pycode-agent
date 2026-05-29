from __future__ import annotations
import json
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
    json_out: bool = typer.Option(False, "--json", help="以 JSON 输出结果(非交互)"),
    quiet: bool = typer.Option(False, "--quiet", help="仅输出最终结果,抑制额外信息"),
    max_turns: int = typer.Option(None, "--max-turns", help="覆盖最大循环轮数"),
    dry_run: bool = typer.Option(False, "--dry-run", help="高风险操作只预览不执行"),
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
            auto_yes=auto_approve, dry_run=dry_run, max_turns=max_turns,
        )
        if no_tools:
            agent.registry = type(agent.registry)()  # empty registry
        try:
            out = agent.run(full)
        except Exception as e:  # noqa
            if json_out:
                typer.echo(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            else:
                typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=1)
        if json_out:
            typer.echo(json.dumps(
                {"ok": True, "result": out, "rejections": agent.rejections},
                ensure_ascii=False,
            ))
        else:
            typer.echo(out)
        # exit code 2: a tool was rejected and the run could not proceed normally
        raise typer.Exit(code=2 if agent.rejections > 0 else 0)

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


@config_app.command("get")
def config_get(key: str, project_dir: Path = typer.Option(Path("."), "--project-dir")):
    from pycode_agent.config.loader import get_setting_for_dir
    try:
        value, source = get_setting_for_dir(project_dir, key)
    except KeyError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{key} = {value}  (source: {source})")


@config_app.command("set")
def config_set(key: str, value: str,
               project_dir: Path = typer.Option(Path("."), "--project-dir")):
    from pycode_agent.config.loader import set_project_setting
    try:
        coerced = set_project_setting(project_dir, key, value)
    except KeyError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:  # validation failure
        typer.echo(f"error: invalid value for {key}: {e}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"set {key} = {coerced}  (written to project config)")
