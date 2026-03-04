"""Tests for script content cleaning — the artifact-stripping logic in agent.py."""

import pytest

from scripy.agent import (
    _clean_script_content,
    _extract_code,
    _parse_inline_tool_call,
    _strip_trailing_tool_call_json,
)

# ---------------------------------------------------------------------------
# _parse_inline_tool_call
# ---------------------------------------------------------------------------

class TestParseInlineToolCall:
    def test_detects_write_file(self):
        raw = f'{HELLO}\n\n{TOOL_CALL_JSON}'
        result = _parse_inline_tool_call(raw)
        assert result is not None
        assert result["name"] == "write_file"
        assert "path" in result["arguments"]

    def test_detects_run_script(self):
        raw = f'{HELLO}\n\n{RUN_TOOL_CALL_JSON}'
        result = _parse_inline_tool_call(raw)
        assert result is not None
        assert result["name"] == "run_script"

    def test_returns_none_for_clean_script(self):
        assert _parse_inline_tool_call(HELLO) is None

    def test_returns_none_for_prose(self):
        assert _parse_inline_tool_call("I will write a script for you.") is None

    def test_returns_none_for_mid_script_name_dict(self):
        script = '#!/usr/bin/env python3\ndata = {"name": "x", "arguments": {"y": 1}}\nprint(data)'
        # "arguments" key is present but it's mid-script, NOT the last line
        assert _parse_inline_tool_call(script) is None

    def test_returns_none_for_invalid_json(self):
        raw = f'{HELLO}\n\n{{"name": broken'
        assert _parse_inline_tool_call(raw) is None

    def test_returns_none_when_arguments_key_missing(self):
        raw = f'{HELLO}\n\n{{"name": "write_file", "path": "hello.py"}}'
        assert _parse_inline_tool_call(raw) is None


# ---------------------------------------------------------------------------
# _strip_trailing_tool_call_json
# ---------------------------------------------------------------------------

TOOL_CALL_JSON = '{"name": "write_file", "arguments": {"path": "hello.py", "content": "..."}}'
RUN_TOOL_CALL_JSON = '{"name": "run_script", "arguments": {"code": "...", "interpreter": "python3"}}'

HELLO = '#!/usr/bin/env python3\n\n# hello.py\nprint("Hello, World!")'


class TestStripTrailingToolCallJson:
    def test_strips_write_file_blob(self):
        raw = f"{HELLO}\n\n{TOOL_CALL_JSON}"
        assert _strip_trailing_tool_call_json(raw) == HELLO

    def test_strips_run_script_blob(self):
        raw = f"{HELLO}\n\n{RUN_TOOL_CALL_JSON}"
        assert _strip_trailing_tool_call_json(raw) == HELLO

    def test_strips_with_trailing_blank_lines_after_blob(self):
        raw = f"{HELLO}\n\n{TOOL_CALL_JSON}\n\n\n"
        assert _strip_trailing_tool_call_json(raw) == HELLO

    def test_does_not_strip_mid_script_name_dict(self):
        """A {"name": ...} dict in the middle of code must not be touched."""
        script = (
            '#!/usr/bin/env python3\n'
            'records = [\n'
            '    {"name": "Alice", "age": 30},\n'
            '    {"name": "Bob", "age": 25},\n'
            ']\n'
            'print(records)'
        )
        assert _strip_trailing_tool_call_json(script) == script

    def test_does_not_strip_dict_without_arguments_key(self):
        """A trailing dict that has "name" but not "arguments" is not a tool call."""
        script = '#!/usr/bin/env python3\nresult = {"name": "test", "value": 42}'
        assert _strip_trailing_tool_call_json(script) == script

    def test_does_not_strip_invalid_json(self):
        script = '#!/usr/bin/env python3\nprint("done")\n{"name": broken json'
        assert _strip_trailing_tool_call_json(script) == script

    def test_empty_string(self):
        assert _strip_trailing_tool_call_json("") == ""

    def test_only_whitespace(self):
        assert _strip_trailing_tool_call_json("   \n\n  ") == "   \n\n  "

    def test_clean_script_unchanged(self):
        assert _strip_trailing_tool_call_json(HELLO) == HELLO


# ---------------------------------------------------------------------------
# _clean_script_content
# ---------------------------------------------------------------------------

class TestCleanScriptContent:
    def test_strips_trailing_tool_call_json(self):
        raw = f"{HELLO}\n\n{TOOL_CALL_JSON}"
        assert _clean_script_content(raw) == HELLO

    def test_strips_markdown_fence(self):
        raw = f"```python\n{HELLO}\n```"
        assert _clean_script_content(raw) == HELLO

    def test_strips_markdown_fence_no_lang(self):
        raw = f"```\n{HELLO}\n```"
        assert _clean_script_content(raw) == HELLO

    def test_strips_tool_call_xml_marker(self):
        raw = f"{HELLO}\n<tool_call>{TOOL_CALL_JSON}</tool_call>"
        assert _clean_script_content(raw) == HELLO

    def test_strips_pipe_tool_call_token(self):
        raw = f"{HELLO}\n<|tool_call|>{TOOL_CALL_JSON}<|/tool_call|>"
        assert _clean_script_content(raw) == HELLO

    def test_clean_passthrough(self):
        assert _clean_script_content(HELLO) == HELLO

    def test_mid_script_name_dict_preserved(self):
        script = (
            '#!/usr/bin/env python3\n'
            'data = {"name": "Alice", "arguments": {"x": 1}}\n'
            'print(data)'
        )
        # "arguments" key is present but this is mid-script, not the last line
        assert _clean_script_content(script) == script

    def test_strips_trailing_blank_lines(self):
        raw = f"{HELLO}\n\n\n"
        assert _clean_script_content(raw) == HELLO


# ---------------------------------------------------------------------------
# _extract_code
# ---------------------------------------------------------------------------

class TestExtractCode:
    def test_extracts_from_markdown_fence(self):
        text = f"Here is the script:\n```python\n{HELLO}\n```"
        assert _extract_code(text) == HELLO

    def test_extracts_shebang_plain(self):
        assert _extract_code(HELLO) == HELLO

    def test_extracts_import_plain(self):
        code = "import os\nprint(os.getcwd())"
        assert _extract_code(code) == code

    def test_extracts_def_plain(self):
        code = "def main():\n    pass"
        assert _extract_code(code) == code

    def test_returns_empty_for_prose(self):
        assert _extract_code("I will write a script that does X.") == ""

    def test_returns_empty_for_json(self):
        assert _extract_code('{"name": "write_file", "arguments": {}}') == ""

    def test_returns_empty_for_empty_string(self):
        assert _extract_code("") == ""


# ---------------------------------------------------------------------------
# Integration: the exact failure mode seen in the wild
# Model dumps script + inline JSON call as plain text (no structured tool call)
# ---------------------------------------------------------------------------

class TestRealWorldArtifact:
    """
    qwen2.5-coder:7b (via Ollama) sometimes ignores tool-calling and emits
    the script followed by a plain JSON write_file invocation as message.content.
    The pipeline path is: _extract_code → _clean_script_content → write.
    """

    BLOB = (
        '{"name": "write_file", "arguments": {'
        '"path": "hello_world.py", '
        '"content": "#!/usr/bin/env python3\\n\\nprint(\\"Hello, World!\\")"}}'
    )

    def test_extract_then_clean_strips_blob(self):
        raw = f'#!/usr/bin/env python3\n\n# hello_world.py\n\nprint("Hello, World!")\n\n{self.BLOB}'
        extracted = _extract_code(raw)
        cleaned = _clean_script_content(extracted)
        assert self.BLOB not in cleaned
        assert 'print("Hello, World!")' in cleaned

    def test_parse_inline_detects_write_file(self):
        raw = f'#!/usr/bin/env python3\n\nprint("Hello, World!")\n\n{self.BLOB}'
        result = _parse_inline_tool_call(raw)
        assert result is not None
        assert result["name"] == "write_file"
        assert result["arguments"]["path"] == "hello_world.py"

    def test_parse_inline_returns_none_for_clean_script(self):
        assert _parse_inline_tool_call('#!/usr/bin/env python3\nprint("hi")') is None

    def test_parse_inline_returns_none_for_prose(self):
        assert _parse_inline_tool_call("I will write a script for you.") is None

    def test_clean_does_not_corrupt_script_body(self):
        raw = f'#!/usr/bin/env python3\n\n# hello_world.py\n\nprint("Hello, World!")\n\n{self.BLOB}'
        result = _clean_script_content(_extract_code(raw))
        assert result == '#!/usr/bin/env python3\n\n# hello_world.py\n\nprint("Hello, World!")'
