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
