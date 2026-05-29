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
        if user == "/undo":
            pm = agent.ctx.patch_manager
            if pm is not None and pm.rollback_last():
                console.print("[green]已撤销最近一次文件修改[/]")
            else:
                console.print("[yellow]没有可撤销的修改[/]")
            continue
        if not user:
            continue
        try:
            answer = agent.run(user)
        except Exception as e:  # noqa
            console.print(f"[red]error:[/] {e}")
            continue
        console.print(f"[bold magenta]Agent >[/] {answer}")
