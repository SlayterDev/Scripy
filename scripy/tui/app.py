"""Textual TUI for scripy."""
from __future__ import annotations

import difflib
import os
import subprocess
import threading

from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, RichLog, Static

from scripy import __version__
from scripy.agent import Agent, RunResult
from scripy.config import Config
from scripy.gates import GateProvider
from scripy.reporter import Reporter
from scripy.theme import AMBER, CODE_THEME, ERROR_COLOR, FAILED, LANGUAGES, MUTED, PROMPT, SPINNER_FRAMES, SUCCESS, SUCCESS_COLOR, WARNING, WARNING_COLOR, WORKING


def _changed_lines(old_code: str, new_code: str) -> set[int]:
    """Return 1-indexed line numbers in new_code that differ from old_code."""
    old = old_code.splitlines()
    new = new_code.splitlines()
    changed: set[int] = set()
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, old, new).get_opcodes():
        if tag != "equal":
            changed.update(range(j1 + 1, j2 + 1))
    return changed


# ---------------------------------------------------------------------------
# Messages  (worker thread → UI, via call_from_thread)
# ---------------------------------------------------------------------------


class LogMessage(Message):
    def __init__(self, glyph: str, color: str, message: str) -> None:
        super().__init__()
        self.glyph = glyph
        self.color = color
        self.message = message


class ScriptUpdated(Message):
    def __init__(self, code: str, lang: str) -> None:
        super().__init__()
        self.code = code
        self.lang = lang


class DiffReady(Message):
    def __init__(self, old_code: str, new_code: str) -> None:
        super().__init__()
        self.old_code = old_code
        self.new_code = new_code


class GeneratingStarted(Message):
    def __init__(self, iteration: int, max_iter: int) -> None:
        super().__init__()
        self.iteration = iteration
        self.max_iter = max_iter


class GeneratingDone(Message):
    pass


class RunGateRequest(Message):
    def __init__(self, code: str, iteration: int, max_iter: int) -> None:
        super().__init__()
        self.code = code
        self.iteration = iteration
        self.max_iter = max_iter
        self._event = threading.Event()
        self._result: tuple[bool, bool, str] = (False, False, code)

    def resolve(self, proceed: bool, always_run: bool, code: str) -> None:
        self._result = (proceed, always_run, code)
        self._event.set()

    def wait(self) -> tuple[bool, bool, str]:
        self._event.wait()
        return self._result


class WriteGateRequest(Message):
    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self._event = threading.Event()
        self._result: tuple[bool, bool] = (False, False)

    def resolve(self, approved: bool, always_write: bool = False) -> None:
        self._result = (approved, always_write)
        self._event.set()

    def wait(self) -> tuple[bool, bool]:
        self._event.wait()
        return self._result


class AgentComplete(Message):
    def __init__(self, result: RunResult) -> None:
        super().__init__()
        self.result = result


class AgentError(Message):
    def __init__(self, error: str) -> None:
        super().__init__()
        self.error = error


class LangSelected(Message):
    def __init__(self, lang: str | None) -> None:
        super().__init__()
        self.lang = lang  # None = cancelled


# ---------------------------------------------------------------------------
# LangPicker widget
# ---------------------------------------------------------------------------


class LangPicker(Widget):
    CAN_FOCUS = True

    DEFAULT_CSS = """
    LangPicker {
        display: none;
        height: auto;
        background: #0f172a;
        padding: 1 2;
        border-top: solid #1e293b;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._cursor = 0
        self._other_text = ""
        self._other_mode = False

    def reset(self, current_lang: str) -> None:
        self._other_text = ""
        self._other_mode = False
        for i, (_, lang_id) in enumerate(LANGUAGES):
            if lang_id == current_lang:
                self._cursor = i
                return
        # Custom lang not in list — pre-fill "other"
        self._cursor = len(LANGUAGES) - 1
        self._other_text = current_lang

    def render(self) -> Text:
        t = Text(no_wrap=True)
        for i, (display, lang_id) in enumerate(LANGUAGES):
            is_selected = i == self._cursor
            is_other = lang_id is None

            if is_selected:
                t.append("  > ", style=f"bold {AMBER}")
                if is_other and self._other_mode:
                    t.append("other: ", style=f"bold {AMBER}")
                    t.append(self._other_text + "▌", style=f"bold {AMBER}")
                else:
                    t.append(display, style=f"bold {AMBER}")
            else:
                t.append("    ", "")
                t.append(display, style=MUTED)

            if i < len(LANGUAGES) - 1:
                t.append("\n")
        return t


# ---------------------------------------------------------------------------
# TuiReporter
# ---------------------------------------------------------------------------


class TuiReporter:
    """Reporter that posts messages to the Textual app instead of printing."""

    def __init__(self, app: ScripyApp) -> None:
        self._app = app

    def log(self, glyph: str, color: str, message: str) -> None:
        self._app.call_from_thread(self._app.post_message, LogMessage(glyph, color, message))

    def print_code(self, code: str, lang: str) -> None:
        self._app.call_from_thread(self._app.post_message, ScriptUpdated(code, lang))

    def update_script(self, code: str, lang: str) -> None:
        self._app.call_from_thread(self._app.post_message, ScriptUpdated(code, lang))

    def show_diff(self, old_code: str, new_code: str) -> None:
        self._app.call_from_thread(self._app.post_message, DiffReady(old_code, new_code))

    def on_generating_start(self, iteration: int, max_iter: int) -> None:
        self._app.call_from_thread(
            self._app.post_message, GeneratingStarted(iteration, max_iter)
        )

    def on_generating_done(self) -> None:
        self._app.call_from_thread(self._app.post_message, GeneratingDone())


# ---------------------------------------------------------------------------
# TuiGateProvider
# ---------------------------------------------------------------------------


class TuiGateProvider:
    """Gate provider that suspends the worker thread until the user responds in the footer."""

    def __init__(self, app: ScripyApp) -> None:
        self._app = app

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
        msg = RunGateRequest(code, iteration, max_iter)
        self._app.call_from_thread(self._app.post_message, msg)
        return msg.wait()

    def write_gate(self, path: str, yes: bool, always_write: bool = False, content: str = "") -> tuple[bool, bool]:
        if yes or always_write or self._app._always_write:
            return True, True
        msg = WriteGateRequest(path)
        self._app.call_from_thread(self._app.post_message, msg)
        return msg.wait()


# ---------------------------------------------------------------------------
# GateBar widget
# ---------------------------------------------------------------------------


class GateBar(Widget):
    """Footer bar that morphs between idle / run-gate / write-gate states."""

    DEFAULT_CSS = """
    GateBar {
        height: 1;
        background: #0f172a;
        padding: 0 2;
    }
    """

    _state: reactive[str] = reactive("idle")
    _iteration: reactive[int] = reactive(0)
    _max_iter: reactive[int] = reactive(3)
    _path: reactive[str] = reactive("")
    _frame: reactive[int] = reactive(0)

    def on_mount(self) -> None:
        self._timer = None

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick_frame(self) -> None:
        self._frame += 1

    def show_generating(self, iteration: int, max_iter: int) -> None:
        self._iteration = iteration
        self._max_iter = max_iter
        self._state = "generating"
        if self._timer is None:
            self._timer = self.set_interval(0.25, self._tick_frame)

    def show_run_gate(self, iteration: int, max_iter: int) -> None:
        self._stop_timer()
        self._iteration = iteration
        self._max_iter = max_iter
        self._state = "run"

    def show_write_gate(self, path: str) -> None:
        self._stop_timer()
        self._path = path
        self._state = "write"

    def clear(self) -> None:
        self._stop_timer()
        self._frame = 0
        self._state = "idle"

    def show_compose(self) -> None:
        self._stop_timer()
        self._state = "compose"

    def show_done(self) -> None:
        self._stop_timer()
        self._frame = 0
        self._state = "done"

    def render(self) -> Text:
        t = Text(overflow="ellipsis", no_wrap=True)

        if self._state == "generating":
            frame = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
            label = (
                f" (iteration {self._iteration + 1}/{self._max_iter})"
                if self._iteration > 0
                else ""
            )
            t.append(f"  generating{label} {frame}", style=MUTED)
        elif self._state == "run":
            t.append(
                f"  iteration {self._iteration + 1}/{self._max_iter}   ",
                style=MUTED,
            )
            for key, label in [("y", "run"), ("n", "skip"), ("e", "edit"), ("v", "view"), ("a", "always")]:
                t.append(f"[{key}]", style=f"bold {AMBER}")
                t.append(f" {label}  ", style=MUTED)

        elif self._state == "write":
            t.append(f"  write {self._path}?   ", style=MUTED)
            for key, label in [("y", "write"), ("n", "print to stdout"), ("a", "always")]:
                t.append(f"[{key}]", style=f"bold {AMBER}")
                t.append(f" {label}  ", style=MUTED)

        elif self._state == "compose":
            t.append("  ", "")
            t.append("?", f"bold {AMBER}")
            t.append("  describe the script you want to build, then press Enter", style=MUTED)
            t.append("   ", "")
            t.append("[^l]", style=f"bold {AMBER}")
            t.append(" set language", style=MUTED)

        elif self._state == "done":
            for key, label in [("r", "refine"), ("e", "edit"), ("q", "quit")]:
                t.append(f"[{key}]", style=f"bold {AMBER}")
                t.append(f" {label}  ", style=MUTED)
            t.append("[^l]", style=f"bold {AMBER}")
            t.append(" set language", style=MUTED)

        return t


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------


class ScripyApp(App):
    CSS = """
    Screen {
        background: #000000;
    }

    #header {
        height: 1;
        background: #000000;
        color: #F59E0B;
        padding: 0 2;
    }

    #main {
        height: 1fr;
    }

    #log-pane {
        width: 1fr;
        background: #000000;
        border-right: solid #1e293b;
        padding: 0 1;
    }

    #script-pane {
        width: 1fr;
        background: #000000;
        padding: 0 1;
        overflow-y: auto;
    }

    #refine-input {
        display: none;
        height: 1;
        background: #0f172a;
        border: none;
        padding: 0 2;
        color: #94a3b8;
    }

    #refine-input:focus {
        border: none;
    }
    """

    def __init__(
        self,
        cfg: Config,
        prompt: str | None,
        output: str | None,
        lang: str | None,
        input_file: str | None,
        yes: bool,
        force_tools: bool,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.prompt = prompt
        self.output = output
        self.lang = lang
        self.input_file = input_file
        self.yes = yes
        self.force_tools = force_tools
        self._active_gate: RunGateRequest | WriteGateRequest | None = None
        self._result: RunResult | None = None
        self._is_refining: bool = False
        self._baseline_code: str = ""
        self._always_write: bool = False
        self._preview_code: str = ""
        self._preview_lang: str = lang or cfg.default_lang
        self._picker_from_input: bool = False

    def _header_markup(self) -> str:
        lang = self.lang or self.cfg.default_lang
        return (
            f"  {WORKING} scripy v{__version__}"
            f"   [{MUTED}]{self.cfg.model}[/{MUTED}]"
            f"   [{AMBER}]{lang}[/{AMBER}]"
        )

    def compose(self) -> ComposeResult:
        yield Static(self._header_markup(), id="header", markup=True)
        with Horizontal(id="main"):
            yield RichLog(id="log-pane", markup=True, highlight=True, wrap=True)
            yield Static("", id="script-pane", expand=True, markup=False)
        yield LangPicker()
        yield GateBar()
        yield Input(placeholder="Describe your refinement…", id="refine-input")

    def on_mount(self) -> None:
        if self.prompt:
            log = self.query_one("#log-pane", RichLog)
            log.write(
                Text.assemble(
                    ("  ", ""),
                    (PROMPT, f"bold {AMBER}"),
                    (" ", ""),
                    (self.prompt, MUTED),
                )
            )
            self.run_worker(self._agent_worker, thread=True)
        else:
            self._start_compose()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _agent_worker(self) -> None:
        reporter = TuiReporter(self)
        gate_provider = TuiGateProvider(self)
        try:
            result = Agent(
                self.cfg,
                self.prompt,
                self.output,
                self.lang,
                self.input_file,
                self.yes,
                self.force_tools,
                reporter=reporter,
                gate_provider=gate_provider,
            ).run()
            self.call_from_thread(self.post_message, AgentComplete(result))
        except Exception as e:
            self.call_from_thread(self.post_message, AgentError(str(e)))

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_log_message(self, msg: LogMessage) -> None:
        log = self.query_one("#log-pane", RichLog)
        log.write(
            Text.assemble(
                ("  ", ""),
                (msg.glyph, f"bold {msg.color}"),
                (" ", ""),
                (msg.message, MUTED),
            )
        )

    def on_script_updated(self, msg: ScriptUpdated) -> None:
        self._preview_code = msg.code
        self._preview_lang = msg.lang
        pane = self.query_one("#script-pane", Static)
        if self._baseline_code:
            changed = _changed_lines(self._baseline_code, msg.code)
            pane.update(
                Syntax(
                    msg.code,
                    msg.lang,
                    theme=CODE_THEME,
                    line_numbers=bool(changed),
                    highlight_lines=changed or None,
                )
            )
        else:
            pane.update(Syntax(msg.code, msg.lang, theme=CODE_THEME, line_numbers=False))

    def on_diff_ready(self, msg: DiffReady) -> None:
        lines = list(
            difflib.unified_diff(
                msg.old_code.splitlines(keepends=True),
                msg.new_code.splitlines(keepends=True),
                fromfile="previous",
                tofile="revised",
            )
        )
        if lines:
            log = self.query_one("#log-pane", RichLog)
            log.write(Syntax("".join(lines), "diff", theme=CODE_THEME))

    def on_generating_started(self, msg: GeneratingStarted) -> None:
        self.query_one(GateBar).show_generating(msg.iteration, msg.max_iter)

    def on_generating_done(self, _msg: GeneratingDone) -> None:
        self.query_one(GateBar).clear()

    def on_run_gate_request(self, msg: RunGateRequest) -> None:
        self._active_gate = msg
        self.query_one(GateBar).show_run_gate(msg.iteration, msg.max_iter)

    def on_write_gate_request(self, msg: WriteGateRequest) -> None:
        self._active_gate = msg
        self.query_one(GateBar).show_write_gate(msg.path)

    def on_agent_complete(self, msg: AgentComplete) -> None:
        self._result = msg.result
        if msg.result.path:
            size = msg.result.path.stat().st_size
            elapsed = f"{msg.result.elapsed:.1f}s"
            log = self.query_one("#log-pane", RichLog)
            log.write(
                Text.assemble(
                    ("  ", ""),
                    (SUCCESS, f"bold {SUCCESS_COLOR}"),
                    (" wrote ", MUTED),
                    (str(msg.result.path), f"bold {SUCCESS_COLOR}"),
                    (f"  {size}B  {elapsed}", MUTED),
                )
            )
        self.query_one(GateBar).show_done()

    def on_agent_error(self, msg: AgentError) -> None:
        log = self.query_one("#log-pane", RichLog)
        log.write(
            Text.assemble(
                ("  ", ""),
                (FAILED, f"bold {ERROR_COLOR}"),
                (f" {msg.error}", MUTED),
            )
        )
        self.set_timer(2, self.exit)

    # ------------------------------------------------------------------
    # Key handling — routes to active gate when one is pending
    # ------------------------------------------------------------------

    async def on_key(self, event: events.Key) -> None:
        key = event.key.lower()

        # Language picker intercepts all keys while open.
        picker = self.query_one(LangPicker)
        if picker.display:
            self._handle_lang_picker_key(key, event)
            event.stop()
            return

        # When the refine input is visible, handle escape/q to cancel, ctrl+l to pick lang.
        inp = self.query_one("#refine-input", Input)
        if inp.display:
            if key == "ctrl+l":
                self._show_lang_picker(from_input=True)
                event.stop()
                return
            if event.key == "escape" or (event.key == "q" and not self.prompt):
                if not self.prompt:
                    # No prompt yet — escape quits entirely
                    self.exit()
                else:
                    inp.display = False
                    self.query_one(GateBar).display = True
                event.stop()
            return

        # Ctrl+L opens the language picker (only when no gate is pending).
        if key == "ctrl+l" and self._active_gate is None:
            self._show_lang_picker()
            event.stop()
            return

        # Handle done state (no active gate).
        gate = self._active_gate
        if gate is None:
            if self.query_one(GateBar)._state == "done":
                if key == "r":
                    self._start_refine()
                    event.stop()
                elif key == "q":
                    self.exit(self._result)
                    event.stop()
                elif key == "e" and self._result and self._result.path:
                    path = self._result.path
                    with self.suspend():
                        subprocess.run([os.environ.get("EDITOR", "vi"), str(path)])
                    new_code = path.read_text()
                    self._result = RunResult(
                        code=new_code,
                        path=path,
                        elapsed=self._result.elapsed,
                        iterations=self._result.iterations,
                    )
                    self.query_one("#script-pane", Static).update(
                        Syntax(new_code, self.lang or "python", theme=CODE_THEME, line_numbers=False)
                    )
                    event.stop()
            return

        if isinstance(gate, RunGateRequest):
            if key == "y":
                self._resolve_run_gate(True, False, gate.code)
            elif key == "n":
                self._resolve_run_gate(False, False, gate.code)
            elif key == "a":
                self._resolve_run_gate(True, True, gate.code)
            elif key == "v":
                # Script pane already shows the code — echo to log for clarity
                log = self.query_one("#log-pane", RichLog)
                log.write(Syntax(gate.code, self.lang or "python", theme=CODE_THEME))
            elif key == "e":
                log = self.query_one("#log-pane", RichLog)
                log.write(
                    Text.assemble(
                        ("  ", ""),
                        (WARNING, f"bold {WARNING_COLOR}"),
                        (" editor not supported in TUI mode", MUTED),
                    )
                )
            event.stop()

        elif isinstance(gate, WriteGateRequest):
            if key == "y":
                self._resolve_write_gate(True)
            elif key == "n":
                self._resolve_write_gate(False)
            elif key == "a":
                self._resolve_write_gate(True, always_write=True)
            event.stop()

    def _handle_lang_picker_key(self, key: str, event: events.Key) -> None:
        picker = self.query_one(LangPicker)
        if picker._other_mode:
            if key == "escape":
                picker._other_mode = False
                picker.refresh()
            elif key == "enter":
                lang = picker._other_text.strip()
                if lang:
                    self.post_message(LangSelected(lang))
            elif key in ("backspace", "delete"):
                picker._other_text = picker._other_text[:-1]
                picker.refresh()
            elif event.character:
                picker._other_text += event.character
                picker.refresh()
            return

        if key == "up":
            picker._cursor = max(0, picker._cursor - 1)
            picker.refresh()
        elif key == "down":
            picker._cursor = min(len(LANGUAGES) - 1, picker._cursor + 1)
            picker.refresh()
        elif key == "enter":
            _, lang_id = LANGUAGES[picker._cursor]
            if lang_id is None:
                picker._other_mode = True
                picker.refresh()
            else:
                self.post_message(LangSelected(lang_id))
        elif key == "escape":
            self.post_message(LangSelected(None))

    def _show_lang_picker(self, from_input: bool = False) -> None:
        self._picker_from_input = from_input
        picker = self.query_one(LangPicker)
        picker.reset(self.lang or self.cfg.default_lang)
        picker.display = True
        if from_input:
            self.query_one("#refine-input", Input).display = False
        else:
            self.query_one(GateBar).display = False

    def on_lang_selected(self, msg: LangSelected) -> None:
        self.query_one(LangPicker).display = False
        if self._picker_from_input:
            inp = self.query_one("#refine-input", Input)
            inp.display = True
            inp.focus()
        else:
            self.query_one(GateBar).display = True
        self._picker_from_input = False
        if msg.lang:
            self._set_lang(msg.lang)

    def _set_lang(self, lang: str) -> None:
        self.lang = lang
        self._preview_lang = lang
        self.query_one("#header", Static).update(self._header_markup())
        log = self.query_one("#log-pane", RichLog)
        log.write(
            Text.assemble(
                ("  ", ""),
                (WARNING, f"bold {WARNING_COLOR}"),
                (f" language → {lang}", MUTED),
            )
        )
        if self._preview_code:
            self.query_one("#script-pane", Static).update(
                Syntax(self._preview_code, lang, theme=CODE_THEME, line_numbers=False)
            )

    def _start_compose(self) -> None:
        gate_bar = self.query_one(GateBar)
        gate_bar.display = True
        gate_bar.show_compose()
        inp = self.query_one("#refine-input", Input)
        inp.placeholder = "What script should I build?"
        inp.clear()
        inp.display = True
        inp.focus()

    def _start_refine(self) -> None:
        self.query_one(GateBar).display = False
        inp = self.query_one("#refine-input", Input)
        inp.placeholder = "Describe your refinement…"
        inp.clear()
        inp.display = True
        inp.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        new_prompt = event.value.strip()
        if not new_prompt:
            return

        event.input.clear()
        event.input.display = False
        gate_bar = self.query_one(GateBar)
        gate_bar.display = True
        gate_bar.clear()

        log = self.query_one("#log-pane", RichLog)
        is_initial = not self._is_refining and not self.prompt
        if not is_initial:
            log.write(Rule(style=MUTED))
        log.write(
            Text.assemble(
                ("  ", ""),
                (PROMPT, f"bold {AMBER}"),
                (" ", ""),
                (new_prompt, MUTED),
            )
        )

        self._baseline_code = self._result.code if self._result else ""
        if not is_initial:
            self._is_refining = True
        if self._result and self._result.path:
            # Lock in the filename from the first run so refinements don't rename it.
            if not self.output:
                self.output = str(self._result.path)
            self.input_file = str(self._result.path)
        self.prompt = new_prompt
        self.run_worker(self._agent_worker, thread=True)

    def _resolve_run_gate(self, proceed: bool, always_run: bool, code: str) -> None:
        gate = self._active_gate
        self._active_gate = None
        self.query_one(GateBar).clear()
        assert isinstance(gate, RunGateRequest)
        gate.resolve(proceed, always_run, code)

    def _resolve_write_gate(self, approved: bool, always_write: bool = False) -> None:
        if always_write:
            self._always_write = True
        gate = self._active_gate
        self._active_gate = None
        self.query_one(GateBar).clear()
        assert isinstance(gate, WriteGateRequest)
        gate.resolve(approved, always_write)
