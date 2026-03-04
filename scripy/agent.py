from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from scripy.config import Config
from scripy.executor import run_script as exec_run, validate_syntax
from scripy.gates import GateProvider, StdinGateProvider
from scripy.prompts import SYSTEM_PROMPT, build_user_prompt
from scripy.reporter import Reporter, RichReporter
from scripy.theme import (
    AMBER,
    ERROR_COLOR,
    FAILED,
    MUTED,
    SUCCESS,
    SUCCESS_COLOR,
    WARNING,
    WARNING_COLOR,
    WORKING,
)
from scripy.tools import TOOL_NAMES, TOOL_SCHEMAS


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
        reporter: Reporter | None = None,
        gate_provider: GateProvider | None = None,
    ) -> None:
        self.cfg = cfg
        self.prompt = prompt
        self.output = output
        self.lang = lang or cfg.default_lang
        self.input_file = input_file
        self.yes = yes
        self.force_tools = force_tools or cfg.force_tools
        self.always_run = yes
        self.reporter: Reporter = reporter or RichReporter()
        self.gate_provider: GateProvider = gate_provider or StdinGateProvider()
        self.client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
        self.messages: list[dict] = []
        self.current_code = ""
        self._prev_code = ""
        self._iteration = 0
        self._done = False
        self._final_path: Path | None = None
        self._start: float = 0.0
        self._elapsed: float = 0.0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> RunResult:
        self._start = time.monotonic()

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
            self._iteration = iteration
            response = self._call_model(iteration)
            message = response.choices[0].message

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
                tool_call = message.tool_calls[0]
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

                inline = _parse_inline_tool_call(content)
                if inline:
                    self.reporter.log(
                        WARNING,
                        WARNING_COLOR,
                        "inline tool call detected — model is not using structured tool calling",
                    )
                    tool_result = self._dispatch_inline(inline)
                    if self._done:
                        break
                    self.messages.append({"role": "user", "content": tool_result})
                    continue

                code = _clean_script_content(_extract_code(content))
                if code:
                    self._update_code(code)
                    ok, err = validate_syntax(code, self.lang)
                    if not ok:
                        self.reporter.log(FAILED, ERROR_COLOR, f"syntax: {err}")
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

                    out_path = self._resolve_output(None)
                    self._elapsed = time.monotonic() - self._start
                    if self.gate_provider.write_gate(out_path, self.yes):
                        Path(out_path).write_text(code)
                        self._final_path = Path(out_path)
                    else:
                        self.reporter.print_code(code, self.lang)
                    self._done = True
                    break
                else:
                    self.reporter.log(
                        WARNING, WARNING_COLOR, "model responded without code — re-prompting"
                    )
                    self.messages.append(
                        {
                            "role": "user",
                            "content": "Please provide the complete script and call write_file to save it.",
                        }
                    )
        else:
            self.reporter.log(WARNING, WARNING_COLOR, "reached max iterations without completion")
            if self.current_code:
                self.reporter.print_code(self.current_code, self.lang)

        return RunResult(
            code=self.current_code,
            path=self._final_path,
            elapsed=self._elapsed,
            iterations=min(self.cfg.max_iterations, self._iteration + 1),
        )

    # ------------------------------------------------------------------
    # Model call
    # ------------------------------------------------------------------

    def _call_model(self, iteration: int):
        self.reporter.on_generating_start(iteration, self.cfg.max_iterations)
        try:
            return self.client.chat.completions.create(
                model=self.cfg.model,
                messages=self.messages,
                tools=TOOL_SCHEMAS,
                tool_choice="required" if self.force_tools else "auto",
                temperature=self.cfg.temperature,
                max_tokens=self.cfg.max_tokens,
            )
        finally:
            self.reporter.on_generating_done()

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
        self._update_code(content)

        out_path = self._resolve_output(model_path)

        ok, err = validate_syntax(content, self.lang)
        if not ok:
            self.reporter.log(FAILED, ERROR_COLOR, f"syntax: {err}")
            return f"Syntax error — fix it before calling write_file again:\n{err}"

        self._elapsed = time.monotonic() - self._start
        if self.gate_provider.write_gate(out_path, self.yes):
            Path(out_path).write_text(content)
            self._final_path = Path(out_path)
            size = self._final_path.stat().st_size
            self.reporter.log(SUCCESS, SUCCESS_COLOR, f"wrote {out_path}  {size}B")
        else:
            self.reporter.print_code(content, self.lang)
            self._final_path = None

        self._done = True
        return "done"

    def _handle_run_script(self, args: dict) -> str:
        code = _clean_script_content(args.get("code", ""))
        interpreter = args.get("interpreter", "python3")
        self._update_code(code)

        lang = _interpreter_to_lang(interpreter)
        ok, err = validate_syntax(code, lang)
        if not ok:
            self.reporter.log(FAILED, ERROR_COLOR, "syntax error")
            return f"Syntax error:\n{err}"

        proceed, self.always_run, code = self.gate_provider.run_gate(
            code,
            self.yes,
            self.always_run,
            iteration=self._iteration,
            max_iter=self.cfg.max_iterations,
        )
        self._update_code(code)

        if not proceed:
            self.reporter.log(WARNING, MUTED, "skipped execution")
            return "Execution skipped by user. Continue without sandbox feedback."

        self.reporter.log(WORKING, AMBER, "running sandbox...")
        stdout, stderr, returncode = exec_run(code, interpreter, self.cfg.sandbox_timeout)

        if returncode == 0:
            self.reporter.log(SUCCESS, SUCCESS_COLOR, "sandbox ok")
            return f"Exit code: 0\nstdout:\n{stdout}" if stdout else "Exit code: 0 (no output)"
        else:
            self.reporter.log(FAILED, ERROR_COLOR, f"exit {returncode}")
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

    def _update_code(self, code: str) -> None:
        """Set current_code, fire diff if changed, notify reporter."""
        if not code:
            return
        if self._prev_code and code != self._prev_code and self._iteration > 0:
            self.reporter.show_diff(self._prev_code, code)
        self._prev_code = code
        self.current_code = code
        self.reporter.update_script(code, self.lang)

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


def _normalize_json_newlines(text: str) -> str:
    """Escape bare newlines inside JSON string values so json.loads can parse them."""
    result: list[str] = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and in_string and i + 1 < len(text):
            result.append(ch)
            result.append(text[i + 1])
            i += 2
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
        elif ch == "\n" and in_string:
            result.append("\\n")
            i += 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def _parse_inline_tool_call(content: str) -> dict | None:
    """
    Detect an inline JSON tool call embedded in plain-text model output.

    Some models (qwen2.5-coder, deepseek-coder via Ollama) don't use the
    structured tool_calls field and instead append a bare JSON object like:
        {"name": "write_file", "arguments": {"path": ..., "content": ...}}

    Handles both single-line blobs and multi-line blobs where the content
    field contains raw newlines (technically invalid JSON).
    """
    import json
    import re

    lines = content.split("\n")
    last_idx = len(lines) - 1
    while last_idx >= 0 and not lines[last_idx].strip():
        last_idx -= 1

    if last_idx < 0:
        return None

    # Fast path: single-line blob on the last non-empty line.
    last_line = lines[last_idx].strip()
    if last_line.startswith("{") and '"name"' in last_line:
        try:
            obj = json.loads(last_line)
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # Slow path: multi-line blob (content field contains raw newlines).
    # Scan backward to find the opening {"name": line.
    for i in range(last_idx, max(last_idx - 100, -1), -1):
        if not (lines[i].strip().startswith('{"name"') or lines[i].strip().startswith('{ "name"')):
            continue
        blob = "\n".join(lines[i : last_idx + 1])
        if '"arguments"' not in blob:
            break
        # Try json.loads with newlines normalised.
        try:
            obj = json.loads(_normalize_json_newlines(blob))
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                return obj
        except json.JSONDecodeError:
            pass
        # Regex fallback for blobs with unescaped quotes in string values.
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', blob)
        if name_match:
            args: dict = {}
            for m in re.finditer(r'"(\w+)"\s*:\s*"([^"]*)"', blob):
                key, val = m.group(1), m.group(2)
                if key != "name":
                    args[key] = val
            return {"name": name_match.group(1), "arguments": args}
        break

    return None


_TOOL_NAMES = TOOL_NAMES


def _strip_trailing_function_call(content: str) -> str:
    """
    Strip a trailing scripy tool call written as a function call with a dict argument.

    Handles both single-line:
        write_file({"path": "...", "content": "..."})
    and multi-line:
        write_file({
            "path": "...",
            "content": "..."
        })

    Requires the dict-argument style  write_file({  to avoid stripping legitimate
    Python helpers that happen to share a tool name but take positional string args.
    Scans at most 30 lines from the end to avoid false positives deep in a script.
    """
    import re

    lines = content.split("\n")
    last_idx = len(lines) - 1
    while last_idx >= 0 and not lines[last_idx].strip():
        last_idx -= 1

    if last_idx < 0:
        return content

    last_stripped = lines[last_idx].strip()

    # Single-line: write_file({"path": ...})
    for name in _TOOL_NAMES:
        if re.match(rf"^{name}\s*\(\s*\{{", last_stripped):
            return "\n".join(lines[:last_idx]).rstrip()

    # Multi-line: closing is "})" or "}" + ")" on the same or adjacent line
    if last_stripped in ("})", ")"):
        scan_start = max(last_idx - 1, 0)
        scan_end = max(last_idx - 30, -1)
        for i in range(scan_start, scan_end, -1):
            stripped = lines[i].strip()
            for name in _TOOL_NAMES:
                if re.match(rf"^{name}\s*\(\s*\{{", stripped):
                    return "\n".join(lines[:i]).rstrip()

    return content


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

    # Slow path: multi-line blob where the content field contains raw newlines.
    # Scan backward to find the opening {"name": line.
    for i in range(last_idx, max(last_idx - 100, -1), -1):
        stripped_i = lines[i].strip()
        if stripped_i.startswith('{"name"') or stripped_i.startswith('{ "name"'):
            blob = "\n".join(lines[i : last_idx + 1])
            if '"arguments"' in blob:
                return "\n".join(lines[:i]).rstrip()
            break

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

    # Strip trailing function-call blobs: write_file({...}) — single or multi-line.
    content = _strip_trailing_function_call(content)

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
    code_starts = ("#!/", "import ", "from ", "def ", "class ", "if __name__")
    if any(text.startswith(s) for s in code_starts):
        return text

    return ""


def _interpreter_to_lang(interpreter: str) -> str:
    return {"python3": "python", "python": "python", "bash": "bash", "sh": "bash"}.get(
        interpreter, interpreter
    )
