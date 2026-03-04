"""Tests for scripy/prompts.py — system prompt and user prompt builder."""

from scripy.prompts import SYSTEM_PROMPT, build_user_prompt


class TestBuildUserPromptNoInput:
    def test_contains_lang(self):
        result = build_user_prompt("rename jpegs by date", "bash")
        assert "bash" in result

    def test_contains_prompt(self):
        result = build_user_prompt("rename jpegs by date", "bash")
        assert "rename jpegs by date" in result

    def test_exact_format(self):
        result = build_user_prompt("sort files", "python")
        assert result == "Write a python script that: sort files"


class TestBuildUserPromptWithInput:
    EXISTING = "#!/usr/bin/env bash\necho hi"

    def test_contains_instruction(self):
        result = build_user_prompt("add error handling", "bash", self.EXISTING)
        assert "add error handling" in result

    def test_contains_existing_script(self):
        result = build_user_prompt("add error handling", "bash", self.EXISTING)
        assert self.EXISTING in result

    def test_contains_lang(self):
        result = build_user_prompt("add error handling", "bash", self.EXISTING)
        assert "bash" in result

    def test_instructs_complete_output(self):
        result = build_user_prompt("add error handling", "bash", self.EXISTING)
        assert "COMPLETE" in result

    def test_different_from_no_input_path(self):
        with_input = build_user_prompt("add error handling", "bash", self.EXISTING)
        without_input = build_user_prompt("add error handling", "bash")
        assert with_input != without_input


class TestSystemPrompt:
    def test_has_shebang_rule(self):
        assert "shebang" in SYSTEM_PROMPT

    def test_prohibits_markdown_fences(self):
        assert "markdown" in SYSTEM_PROMPT

    def test_references_write_file(self):
        assert "write_file" in SYSTEM_PROMPT

    def test_prohibits_inline_write_file(self):
        # The rule we added: never include write_file call inside the script body
        assert "script body" in SYSTEM_PROMPT

    def test_single_tool_at_a_time(self):
        assert "ONE tool" in SYSTEM_PROMPT
