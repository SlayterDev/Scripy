from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

from rich.console import Console

from scripy.theme import AMBER, MUTED, PROMPT

console = Console()


class GateProvider(Protocol):
    def run_gate(
        self,
        code: str,
        yes: bool,
        always_run: bool,
        *,
        iteration: int = 0,
        max_iter: int = 3,
    ) -> tuple[bool, bool, str]: ...

    def write_gate(self, path: str, yes: bool, always_write: bool = False, content: str = "") -> tuple[bool, bool]: ...


class StdinGateProvider:
    """Headless confirmation gates — reads single keystrokes from stdin."""

    def run_gate(
        self,
        code: str,
        yes: bool,
        always_run: bool,
        *,
        iteration: int = 0,
        max_iter: int = 3,
    ) -> tuple[bool, bool, str]:
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

    def write_gate(self, path: str, yes: bool, always_write: bool = False, content: str = "") -> tuple[bool, bool]:
        if yes or always_write:
            return True, always_write

        while True:
            console.print(
                f"  [{AMBER}]{PROMPT}[/{AMBER}]"
                f" [{MUTED}]write to disk as[/{MUTED}]"
                f" [bold]{path}[/bold]"
                f"[{MUTED}]?[/{MUTED}]"
                f" [{MUTED}][[bold]y[/bold]/n/v/a] ›[/{MUTED}] ",
                end="",
            )
            key = _getch().lower()
            console.print(key)

            if key == "y":
                return True, False
            elif key == "n":
                return False, False
            elif key == "a":
                return True, True
            elif key == "v":
                if content:
                    console.print(content)
            elif key in ("\x03", "q"):
                raise KeyboardInterrupt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _getch() -> str:
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _open_in_editor(code: str) -> str:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        subprocess.run([editor, tmp], check=False)
        return Path(tmp).read_text()
    finally:
        Path(tmp).unlink(missing_ok=True)
