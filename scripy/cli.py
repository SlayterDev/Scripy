from __future__ import annotations

import click
from rich.console import Console

from scripy import __version__
from scripy.config import load_config
from scripy.theme import AMBER, MUTED, SUCCESS_COLOR, SUCCESS, WORKING

console = Console()


def version_callback(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    cfg = load_config()
    host = cfg.base_url.removeprefix("http://").removeprefix("https://")
    console.print(f"scripy [bold]{__version__}[/bold]")
    console.print(f"model  [{MUTED}]{cfg.model} @ {host}[/{MUTED}]")
    ctx.exit()


@click.command()
@click.option("-p", "--prompt", default=None, help="What script to generate.")
@click.option("-o", "--output", default=None, help="Output file path.")
@click.option("-l", "--lang", default=None, help="Language override (python, bash, etc.).")
@click.option("--model", default=None, help="Model name override.")
@click.option("--input", "input_file", default=None, help="Existing script to modify.")
@click.option("--tui", is_flag=True, default=False, help="Launch Textual TUI.")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip all confirmation gates.")
@click.option(
    "--force-tools",
    is_flag=True,
    default=False,
    help="Set tool_choice=required. Use with models that support structured tool calling (e.g. llama3.1:8b).",
)
@click.option(
    "--version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=version_callback,
    help="Show version and exit.",
)
def main(
    prompt: str,
    output: str | None,
    lang: str | None,
    model: str | None,
    input_file: str | None,
    tui: bool,
    yes: bool,
    force_tools: bool,
) -> None:
    """scripy — generate scripts with local LLMs."""
    cfg = load_config()

    if not tui and not prompt:
        raise click.UsageError("Missing option '-p' / '--prompt'.")

    # Apply CLI overrides
    if model:
        cfg.model = model
    if lang:
        cfg.default_lang = lang

    if tui:
        from scripy.tui.app import ScripyApp

        app = ScripyApp(cfg, prompt, output, lang, input_file, yes, force_tools)
        app.run()
        return

    console.print(f"  [{AMBER}]{WORKING}[/{AMBER}] scripy v{__version__} - {cfg.model}")

    from scripy.agent import Agent

    try:
        result = Agent(cfg, prompt, output, lang, input_file, yes, force_tools).run()
    except KeyboardInterrupt:
        console.print(f"\n  [{MUTED}]~ aborted[/{MUTED}]")
        return

    if result.path:
        size = result.path.stat().st_size
        elapsed = f"{result.elapsed:.1f}s"
        console.print(
            f"  [{SUCCESS_COLOR}]{SUCCESS}[/{SUCCESS_COLOR}]"
            f" wrote [bold]{result.path}[/bold]"
            f"  [{MUTED}]{size}B  {elapsed}[/{MUTED}]"
        )
