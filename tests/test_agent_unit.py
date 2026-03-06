"""Unit tests for Agent — helpers, tool handlers, and agentic loop (mocked OpenAI)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from scripy.agent import Agent, _interpreter_to_lang
from scripy.config import Config


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class NullReporter:
    def log(self, *a, **kw): pass
    def print_code(self, *a, **kw): pass
    def update_script(self, *a, **kw): pass
    def show_diff(self, *a, **kw): pass
    def on_generating_start(self, *a, **kw): pass
    def on_generating_done(self): pass


class YesGateProvider:
    def run_gate(self, code, yes, always_run, *, iteration=0, max_iter=3):
        return True, True, code

    def write_gate(self, path, yes, always_write=False, content=""):
        return True, False


def make_cfg(**overrides):
    defaults = dict(
        base_url="http://localhost:11434/v1",
        model="test-model",
        api_key="test",
        temperature=0.2,
        max_tokens=4096,
        force_tools=False,
        max_iterations=3,
        default_lang="python",
        sandbox_timeout=10,
    )
    defaults.update(overrides)
    return Config(**defaults)


def make_agent(tmp_path, *, lang="python", output_name="out.py", **kwargs):
    return Agent(
        cfg=make_cfg(),
        prompt="test prompt",
        output=str(tmp_path / output_name),
        lang=lang,
        input_file=None,
        yes=True,
        reporter=NullReporter(),
        gate_provider=YesGateProvider(),
        **kwargs,
    )


def tool_response(name: str, args: dict):
    """Mock OpenAI response with a single structured tool call."""
    tc = MagicMock()
    tc.id = "call_1"
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def text_response(content: str):
    """Mock OpenAI response with plain-text content and no tool calls."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


HELLO_PY = '#!/usr/bin/env python3\n\n# hello.py — greet the world\n\nprint("Hello, World!")'


# ---------------------------------------------------------------------------
# _interpreter_to_lang
# ---------------------------------------------------------------------------


class TestInterpreterToLang:
    def test_python3(self):
        assert _interpreter_to_lang("python3") == "python"

    def test_python(self):
        assert _interpreter_to_lang("python") == "python"

    def test_bash(self):
        assert _interpreter_to_lang("bash") == "bash"

    def test_sh(self):
        assert _interpreter_to_lang("sh") == "bash"

    def test_unknown_passthrough(self):
        assert _interpreter_to_lang("ruby") == "ruby"


# ---------------------------------------------------------------------------
# Agent._resolve_output
# ---------------------------------------------------------------------------


class TestResolveOutput:
    def test_cli_output_flag_wins(self, tmp_path):
        agent = make_agent(tmp_path)
        assert agent._resolve_output("model.py") == str(tmp_path / "out.py")

    def test_uses_model_path_when_no_flag(self, tmp_path):
        agent = Agent(
            cfg=make_cfg(), prompt="x", output=None, lang="python",
            input_file=None, yes=True,
            reporter=NullReporter(), gate_provider=YesGateProvider(),
        )
        assert agent._resolve_output("model_suggested.py") == "model_suggested.py"

    def test_defaults_python_extension(self, tmp_path):
        agent = Agent(
            cfg=make_cfg(), prompt="x", output=None, lang="python",
            input_file=None, yes=True,
            reporter=NullReporter(), gate_provider=YesGateProvider(),
        )
        assert agent._resolve_output(None) == "script.py"

    def test_defaults_bash_extension(self, tmp_path):
        agent = Agent(
            cfg=make_cfg(), prompt="x", output=None, lang="bash",
            input_file=None, yes=True,
            reporter=NullReporter(), gate_provider=YesGateProvider(),
        )
        assert agent._resolve_output(None) == "script.sh"


# ---------------------------------------------------------------------------
# Agent._handle_read_file / _handle_list_directory
# ---------------------------------------------------------------------------


class TestHandleReadFile:
    def test_reads_existing_file(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("print('hi')")
        agent = make_agent(tmp_path)
        assert agent._handle_read_file({"path": str(f)}) == "print('hi')"

    def test_missing_file_returns_error(self, tmp_path):
        agent = make_agent(tmp_path)
        result = agent._handle_read_file({"path": str(tmp_path / "nope.py")})
        assert result.lower().startswith("error")


class TestHandleListDirectory:
    def test_lists_files(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.sh").write_text("")
        agent = make_agent(tmp_path)
        result = agent._handle_list_directory({"path": str(tmp_path)})
        assert "a.py" in result
        assert "b.sh" in result

    def test_missing_dir_returns_error(self, tmp_path):
        agent = make_agent(tmp_path)
        result = agent._handle_list_directory({"path": str(tmp_path / "nope")})
        assert result.lower().startswith("error")


# ---------------------------------------------------------------------------
# Agent.run() — full loop with mocked OpenAI client
# ---------------------------------------------------------------------------


class TestAgentRunWriteFileTool:
    def _run(self, tmp_path, responses):
        agent = make_agent(tmp_path)
        agent.client = MagicMock()
        agent.client.chat.completions.create.side_effect = responses
        return agent.run()

    def test_writes_file(self, tmp_path):
        result = self._run(
            tmp_path,
            [tool_response("write_file", {"path": "hello.py", "content": HELLO_PY})],
        )
        assert result.path is not None
        assert result.path.read_text() == HELLO_PY

    def test_result_code(self, tmp_path):
        result = self._run(
            tmp_path,
            [tool_response("write_file", {"path": "hello.py", "content": HELLO_PY})],
        )
        assert result.code == HELLO_PY

    def test_elapsed_is_non_negative(self, tmp_path):
        result = self._run(
            tmp_path,
            [tool_response("write_file", {"path": "hello.py", "content": HELLO_PY})],
        )
        assert result.elapsed >= 0

    def test_single_iteration(self, tmp_path):
        result = self._run(
            tmp_path,
            [tool_response("write_file", {"path": "hello.py", "content": HELLO_PY})],
        )
        assert result.iterations == 1


class TestAgentRunTextFallback:
    """Model returns code as plain text rather than using tool_calls."""

    def _run(self, tmp_path, responses):
        agent = make_agent(tmp_path)
        agent.client = MagicMock()
        agent.client.chat.completions.create.side_effect = responses
        return agent.run()

    def test_extracts_and_writes_code(self, tmp_path):
        result = self._run(tmp_path, [text_response(HELLO_PY)])
        assert result.code == HELLO_PY

    def test_prose_reprompts_then_succeeds(self, tmp_path):
        result = self._run(
            tmp_path,
            [
                text_response("I will write a script for you."),
                text_response(HELLO_PY),
            ],
        )
        assert result.code == HELLO_PY
        assert result.iterations == 2


class TestAgentRunSyntaxError:
    """write_file with bad code → agent re-prompts → second call with good code."""

    def _run(self, tmp_path, responses):
        agent = make_agent(tmp_path)
        agent.client = MagicMock()
        agent.client.chat.completions.create.side_effect = responses
        return agent.run()

    def test_reprompts_on_syntax_error(self, tmp_path):
        bad = "def foo(\n  pass"
        result = self._run(
            tmp_path,
            [
                tool_response("write_file", {"path": "hello.py", "content": bad}),
                tool_response("write_file", {"path": "hello.py", "content": HELLO_PY}),
            ],
        )
        assert result.code == HELLO_PY

    def test_correct_iteration_count(self, tmp_path):
        bad = "def foo(\n  pass"
        result = self._run(
            tmp_path,
            [
                tool_response("write_file", {"path": "hello.py", "content": bad}),
                tool_response("write_file", {"path": "hello.py", "content": HELLO_PY}),
            ],
        )
        assert result.iterations == 2
