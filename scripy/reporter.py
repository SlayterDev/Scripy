from __future__ import annotations

import difflib
import threading
from typing import Protocol

from rich.console import Console
from rich.live import Live
from rich.syntax import Syntax
from rich.text import Text

from scripy.theme import AMBER, MUTED, SPINNER_FRAMES, WORKING, get_code_theme


class Reporter(Protocol):
    def log(self, glyph: str, color: str, message: str) -> None: ...
    def print_code(self, code: str, lang: str) -> None: ...
    def update_script(self, code: str, lang: str) -> None: ...
    def show_diff(self, old_code: str, new_code: str) -> None: ...
    def on_generating_start(self, iteration: int, max_iter: int) -> None: ...
    def on_generating_done(self) -> None: ...


class RichReporter:
    """Headless reporter — outputs to the terminal via Rich."""

    def __init__(self, theme: str | None = None) -> None:
        self.console = Console()
        self.theme = theme or "dracula"
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def log(self, glyph: str, color: str, message: str) -> None:
        self.console.print(f"  [{color}]{glyph}[/{color}] [{MUTED}]{message}[/{MUTED}]")

    def print_code(self, code: str, lang: str) -> None:
        self.console.print(Syntax(code, lang, theme=self.theme))

    def update_script(self, code: str, lang: str) -> None:
        pass  # no-op in headless

    def show_diff(self, old_code: str, new_code: str) -> None:
        lines = list(
            difflib.unified_diff(
                old_code.splitlines(keepends=True),
                new_code.splitlines(keepends=True),
                fromfile="previous",
                tofile="revised",
            )
        )
        if lines:
            self.console.print(Syntax("".join(lines), "diff", theme=self.theme))

    def on_generating_start(self, iteration: int, max_iter: int) -> None:
        iter_label = f" (iteration {iteration + 1}/{max_iter})" if iteration > 0 else ""
        self._stop = threading.Event()
        stop = self._stop

        def _spin() -> None:
            idx = 0
            with Live(console=self.console, refresh_per_second=4) as live:
                while not stop.is_set():
                    frame = SPINNER_FRAMES[idx % len(SPINNER_FRAMES)]
                    live.update(
                        Text(
                            f"  {WORKING} generating{iter_label} {frame}",
                            style=f"bold {AMBER}",
                        )
                    )
                    idx += 1
                    stop.wait(0.25)
                live.update(Text(""))

        self._thread = threading.Thread(target=_spin, daemon=True)
        self._thread.start()

    def on_generating_done(self) -> None:
        if self._stop:
            self._stop.set()
        if self._thread:
            self._thread.join()
