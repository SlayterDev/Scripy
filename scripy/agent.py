from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI
from rich.console import Console
from rich.live import Live
from rich.text import Text

from scripy.config import Config
from scripy.executor import run_script as exec_run, validate_syntax
from scripy.gates import run_gate, write_gate
from scripy.prompts import SYSTEM_PROMPT, build_user_prompt
from scripy.theme import (
    AMBER,
    ERROR_COLOR,
    FAILED,
    MUTED,
    SPINNER_FRAMES,
    SUCCESS,
    SUCCESS_COLOR,
    WARNING,
    WORKING,
)
from scripy.tools import TOOL_SCHEMAS


@dataclass
class RunResult:
    code: str
    path: Path | None
    elapsed: float
    iterations: int


class Agent:
    def __init__(
        self,
        cfg: Config,
        prompt: str,
        output: str | None,
        lang: str | None,
        input_file: str | None,
        yes: bool,
        force_tools: bool = False,
    ) -> None:
        self.cfg = cfg
        self.prompt = prompt
        self.output = output
        self.lang = lang or cfg.default_lang
        self.input_file = input_file
        self.yes = yes
        self.force_tools = force_tools
        self.always_run = yes
        self.console = Console()
        self.client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
        self.messages: list[dict] = []
        self.current_code = ""
        self._done = False
        self._final_path: Path | None = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> RunResult:
        start = time.monotonic()

        input_content: str | None = None
        if self.input_file:
            input_content = Path(self.input_file).read_text()

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(self.prompt, self.lang, input_content),
            },
        ]

        for iteration in range(self.cfg.max_iterations):
            response = self._call_model_with_spinner(iteration)
            message = response.choices[0].message

            # Append assistant message to history
            assistant_msg: dict = {"role": "assistant"}
            if message.content:
                assistant_msg["content"] = message.content
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            self.messages.append(assistant_msg)

            if message.tool_calls:
                tool_call = message.tool_calls[0]  # one at a time per spec
                tool_result = self._dispatch_tool(tool_call)

                if self._done:
                    break

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )
            else:
                content = message.content or ""

                # Check for inline tool call first — some models (qwen, deepseek)
                # embed JSON tool invocations in plain text instead of using the
                # structured tool_calls field.
                inline = _parse_inline_tool_call(content)
                if inline:
                    self.console.print(
                        f"  [{WARNING}] [{MUTED}]inline tool call detected — model is not using structured tool calling[/{MUTED}]"
                    )
                    tool_result = self._dispatch_inline(inline)
                    if self._done:
                        break
                    # Feed the result back so the model can continue if needed
                    self.messages.append({"role": "user", "content": tool_result})
                    continue

                # No tool call at all — try to extract plain code
                code = _clean_script_content(_extract_code(content))
                if code:
                    self.current_code = code
                    ok, err = validate_syntax(code, self.lang)
                    if not ok:
                        self.console.print(
                            f"  [{ERROR_COLOR}]{FAILED}[/{ERROR_COLOR}]"
                            f" [{MUTED}]syntax: {err}[/{MUTED}]"
                        )
                        self.messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Syntax error in the script:\n{err}\n"
                                    "Fix it and call write_file to save the corrected version."
                                ),
                            }
                        )
                        continue

                    # Valid code, no tool call — go straight to write gate
                    out_path = self._resolve_output(None)
                    if write_gate(out_path, self.yes):
                        Path(out_path).write_text(code)
                        self._final_path = Path(out_path)
                    else:
                        self.console.print(code)
                    self._done = True
                    break
                else:
                    # Model is talking instead of coding — nudge it
                    self.console.print(
                        f"  [{WARNING}] [{MUTED}]model responded without code — re-prompting[/{MUTED}]"
                    )
                    self.messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Please provide the complete script and call write_file to save it."
                            ),
                        }
                    )
        else:
            self.console.print(
                f"  [{WARNING}] [{MUTED}]reached max iterations without completion[/{MUTED}]"
            )
            if self.current_code:
                self.console.print(self.current_code)

        elapsed = time.monotonic() - start
        return RunResult(
            code=self.current_code,
            path=self._final_path,
            elapsed=elapsed,
            iterations=min(self.cfg.max_iterations, iteration + 1),
        )

    # ------------------------------------------------------------------
    # Model call with spinner
    # ------------------------------------------------------------------

    def _call_model_with_spinner(self, iteration: int):
        iter_label = (
            f"  iteration {iteration + 1}/{self.cfg.max_iterations}" if iteration > 0 else ""
        )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                self.client.chat.completions.create,
                model=self.cfg.model,
                messages=self.messages,
                tools=TOOL_SCHEMAS,
                tool_choice="required" if self.force_tools else "auto",
                temperature=self.cfg.temperature,
                max_tokens=self.cfg.max_tokens,
            )

            frame_idx = 0
            with Live(console=self.console, refresh_per_second=4) as live:
                while not future.done():
                    frame = SPINNER_FRAMES[frame_idx % len(SPINNER_FRAMES)]
                    live.update(
                        Text(f"  {WORKING} generating{frame}{iter_label}", style=f"bold {AMBER}")
                    )
                    frame_idx += 1
                    time.sleep(0.25)
                live.update(Text(""))

        return future.result()  # re-raises any exception

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def _dispatch_tool(self, tool_call) -> str:
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return "error: could not parse tool arguments"

        if name == "write_file":
            return self._handle_write_file(args)
        elif name == "run_script":
            return self._handle_run_script(args)
        elif name == "read_file":
            return self._handle_read_file(args)
        elif name == "list_directory":
            return self._handle_list_directory(args)
        else:
            return f"error: unknown tool '{name}'"

    def _dispatch_inline(self, call: dict) -> str:
        """Dispatch a parsed inline tool call (model didn't use structured tool_calls)."""
        name = call.get("name", "")
        args = call.get("arguments", {})
        if name == "write_file":
            return self._handle_write_file(args)
        elif name == "run_script":
            return self._handle_run_script(args)
        elif name == "read_file":
            return self._handle_read_file(args)
        elif name == "list_directory":
            return self._handle_list_directory(args)
        else:
            return f"error: unknown tool '{name}'"

    def _handle_write_file(self, args: dict) -> str:
        content = _clean_script_content(args.get("content", ""))
        model_path = args.get("path", "")
        self.current_code = content

        out_path = self._resolve_output(model_path)

        ok, err = validate_syntax(content, self.lang)
        if not ok:
            self.console.print(
                f"  [{ERROR_COLOR}]{FAILED}[/{ERROR_COLOR}] [{MUTED}]syntax: {err}[/{MUTED}]"
            )
            return f"Syntax error — fix it before calling write_file again:\n{err}"

        if write_gate(out_path, self.yes):
            Path(out_path).write_text(content)
            self._final_path = Path(out_path)
            size = self._final_path.stat().st_size
            self.console.print(
                f"  [{SUCCESS_COLOR}]{SUCCESS}[/{SUCCESS_COLOR}]"
                f" [bold]{out_path}[/bold]"
                f" [{MUTED}]{size}B[/{MUTED}]"
            )
        else:
            self.console.print(content)
            self._final_path = None

        self._done = True
        return "done"

    def _handle_run_script(self, args: dict) -> str:
        code = _clean_script_content(args.get("code", ""))
        interpreter = args.get("interpreter", "python3")
        self.current_code = code

        lang = _interpreter_to_lang(interpreter)
        ok, err = validate_syntax(code, lang)
        if not ok:
            self.console.print(
                f"  [{ERROR_COLOR}]{FAILED}[/{ERROR_COLOR}] [{MUTED}]syntax error[/{MUTED}]"
            )
            return f"Syntax error:\n{err}"

        proceed, self.always_run, code = run_gate(code, self.yes, self.always_run)
        self.current_code = code  # may have been edited

        if not proceed:
            self.console.print(f"  [{MUTED}]{WARNING} skipped execution[/{MUTED}]")
            return "Execution skipped by user. Continue without sandbox feedback."

        self.console.print(
            f"  [{AMBER}]{WORKING}[/{AMBER}] [{MUTED}]running sandbox...[/{MUTED}]"
        )
        stdout, stderr, returncode = exec_run(code, interpreter, self.cfg.sandbox_timeout)

        if returncode == 0:
            self.console.print(
                f"  [{SUCCESS_COLOR}]{SUCCESS}[/{SUCCESS_COLOR}] [{MUTED}]sandbox ok[/{MUTED}]"
            )
            return f"Exit code: 0\nstdout:\n{stdout}" if stdout else "Exit code: 0 (no output)"
        else:
            self.console.print(
                f"  [{ERROR_COLOR}]{FAILED}[/{ERROR_COLOR}]"
                f" [{MUTED}]exit {returncode}[/{MUTED}]"
            )
            parts = [f"Exit code: {returncode}"]
            if stdout:
                parts.append(f"stdout:\n{stdout}")
            if stderr:
                parts.append(f"stderr:\n{stderr}")
            return "\n".join(parts)

    def _handle_read_file(self, args: dict) -> str:
        path = args.get("path", "")
        try:
            return Path(path).read_text()
        except OSError as e:
            return f"Error reading file: {e}"

    def _handle_list_directory(self, args: dict) -> str:
        path = args.get("path", ".")
        try:
            entries = sorted(Path(path).iterdir(), key=lambda p: (p.is_file(), p.name))
            return "\n".join(e.name for e in entries)
        except OSError as e:
            return f"Error listing directory: {e}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_output(self, model_path: str | None) -> str:
        if self.output:
            return self.output
        if model_path:
            return model_path
        ext = {
            "python": ".py",
            "bash": ".sh",
            "sh": ".sh",
            "ruby": ".rb",
            "javascript": ".js",
        }.get(self.lang, ".py")
        return f"script{ext}"


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _parse_inline_tool_call(content: str) -> dict | None:
    """
    Detect an inline JSON tool call embedded in plain-text model output.

    Some models (qwen2.5-coder, deepseek-coder via Ollama) don't use the
    structured tool_calls field and instead append a bare JSON object like:
        {"name": "write_file", "arguments": {"path": ..., "content": ...}}

    Returns the parsed call dict on success, None otherwise.
    Reuses the same last-line heuristic as _strip_trailing_tool_call_json
    so both functions stay in sync.
    """
    import json

    lines = content.split("\n")
    last_idx = len(lines) - 1
    while last_idx >= 0 and not lines[last_idx].strip():
        last_idx -= 1

    if last_idx < 0:
        return None

    last_line = lines[last_idx].strip()
    if last_line.startswith("{") and '"name"' in last_line:
        try:
            obj = json.loads(last_line)
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    return None


def _strip_trailing_tool_call_json(content: str) -> str:
    """
    Remove a tool-call JSON blob appended at the end of the content.

    Only examines the last non-empty line, so {"name": ...} dicts that appear
    legitimately in the middle of a script are never touched.
    A line is considered a tool-call blob only if it parses as JSON and has
    both 'name' and 'arguments' keys — the OpenAI function-call schema.
    """
    import json

    lines = content.split("\n")

    # Find the last non-empty line
    last_idx = len(lines) - 1
    while last_idx >= 0 and not lines[last_idx].strip():
        last_idx -= 1

    if last_idx < 0:
        return content

    last_line = lines[last_idx].strip()
    if last_line.startswith("{") and '"name"' in last_line:
        try:
            obj = json.loads(last_line)
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                return "\n".join(lines[:last_idx]).rstrip()
        except json.JSONDecodeError:
            pass

    return content


def _clean_script_content(content: str) -> str:
    """
    Strip model artifacts from script content before writing or running.

    Handles common patterns from open-source models (qwen, deepseek, etc.):
    - Markdown code fences
    - <tool_call>...</tool_call> XML markers
    - Trailing JSON function-call blobs
    """
    import re

    # Unwrap markdown fences if the whole thing is fenced
    fence = re.search(r"```(?:\w+)?\n(.*?)```", content, re.DOTALL)
    if fence:
        return fence.group(1).strip()

    # Strip <tool_call>...</tool_call> blocks (qwen / hermes style)
    content = re.sub(r"<tool_call>.*", "", content, flags=re.DOTALL)

    # Strip <|tool_call|>...<|/tool_call|> tokens
    content = re.sub(r"<\|tool_call\|>.*", "", content, flags=re.DOTALL)

    # Strip trailing JSON tool-call blob (plain JSON, no XML wrapper).
    # Only inspects the last non-empty line to avoid false-positives in code
    # that legitimately contains {"name": ...} dict literals mid-script.
    content = _strip_trailing_tool_call_json(content)

    return content.strip()


def _extract_code(text: str) -> str:
    """Extract code from a plain-text response, stripping markdown fences if present."""
    import re

    fence = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()

    text = text.strip()
    # Looks like actual code if it has a shebang or starts with common code tokens
    code_starts = ("#!/", "import ", "from ", "def ", "class ", "if __name__")
    if any(text.startswith(s) for s in code_starts):
        return text

    return ""


def _interpreter_to_lang(interpreter: str) -> str:
    return {"python3": "python", "python": "python", "bash": "bash", "sh": "bash"}.get(
        interpreter, interpreter
    )
