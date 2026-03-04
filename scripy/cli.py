from __future__ import annotations

import click
from rich.console import Console

from scripy import __version__
from scripy.config import load_config
from scripy.theme import AMBER, MUTED, WORKING

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
@click.option("-p", "--prompt", required=True, help="What script to generate.")
@click.option("-o", "--output", default=None, help="Output file path.")
@click.option("--lang", default=None, help="Language override (python, bash, etc.).")
@click.option("--model", default=None, help="Model name override.")
@click.option("--input", "input_file", default=None, help="Existing script to modify.")
@click.option("--tui", is_flag=True, default=False, help="Launch Textual TUI.")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip all confirmation gates.")
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
) -> None:
    """scripy — generate scripts with local LLMs."""
    cfg = load_config()

    # Apply CLI overrides
    if model:
        cfg.model = model
    if lang:
        cfg.default_lang = lang

    # Stub — agent call goes here in Phase 2
    console.print(f"  [{AMBER}]{WORKING}[/{AMBER}] scripy v{__version__}")
    console.print(f"  [{MUTED}]prompt:  {prompt}[/{MUTED}]")
    console.print(f"  [{MUTED}]model:   {cfg.model}[/{MUTED}]")
    console.print(f"  [{MUTED}]lang:    {lang or cfg.default_lang}[/{MUTED}]")
    if output:
        console.print(f"  [{MUTED}]output:  {output}[/{MUTED}]")
    if input_file:
        console.print(f"  [{MUTED}]input:   {input_file}[/{MUTED}]")
    if tui:
        console.print(f"  [{MUTED}]mode:    tui[/{MUTED}]")
    if yes:
        console.print(f"  [{MUTED}]gates:   bypassed[/{MUTED}]")
