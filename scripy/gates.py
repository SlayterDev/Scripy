from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console

from scripy.theme import AMBER, MUTED, PROMPT

console = Console()


def _getch() -> str:
    """Read one character from stdin without requiring Enter."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def run_gate(
    code: str,
    yes: bool,
    always_run: bool,
) -> tuple[bool, bool, str]:
    """
    Ask whether to sandbox-run the script.

    Returns (proceed, always_run_updated, code_to_run).
    `code_to_run` may differ from input if user chose `e` (editor).
    """
    if yes or always_run:
        return True, always_run, code

    current_code = code

    while True:
        console.print(
            f"  [{AMBER}]{PROMPT}[/{AMBER}]"
            f" [{MUTED}]run script to validate?[/{MUTED}]"
            f" [{MUTED}][[bold]y[/bold]/n/e/v/a] ›[/{MUTED}] ",
            end="",
        )
        key = _getch().lower()
        console.print(key)

        if key == "y":
            return True, False, current_code
        elif key == "n":
            return False, False, current_code
        elif key == "a":
            return True, True, current_code
        elif key == "v":
            console.print(current_code)
        elif key == "e":
            current_code = _open_in_editor(current_code)
        elif key in ("\x03", "q"):
            raise KeyboardInterrupt


def write_gate(path: str, yes: bool) -> bool:
    """Ask whether to write the file. Returns True if approved."""
    if yes:
        return True

    console.print(
        f"  [{AMBER}]{PROMPT}[/{AMBER}]"
        f" [{MUTED}]write to disk as[/{MUTED}]"
        f" [bold]{path}[/bold]"
        f"[{MUTED}]?[/{MUTED}]"
        f" [{MUTED}][[bold]y[/bold]/n] ›[/{MUTED}] ",
        end="",
    )
    key = _getch().lower()
    console.print(key)
    return key == "y"


def _open_in_editor(code: str) -> str:
    """Open code in $EDITOR and return the (possibly modified) content."""
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        subprocess.run([editor, tmp], check=False)
        return Path(tmp).read_text()
    finally:
        Path(tmp).unlink(missing_ok=True)
