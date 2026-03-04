"""Tests for executor.py — syntax validation and sandboxed script running."""

import pytest

from scripy.executor import run_script, validate_syntax


# ---------------------------------------------------------------------------
# validate_syntax
# ---------------------------------------------------------------------------

class TestValidateSyntaxPython:
    def test_valid(self):
        ok, err = validate_syntax('print("hello")', "python")
        assert ok is True
        assert err == ""

    def test_valid_multiline(self):
        code = "def greet(name):\n    return f'hello {name}'\n"
        ok, err = validate_syntax(code, "python")
        assert ok is True

    def test_invalid_syntax(self):
        ok, err = validate_syntax("def foo(\n  pass", "python")
        assert ok is False
        assert err != ""

    def test_invalid_indentation(self):
        ok, err = validate_syntax("if True:\npass", "python")
        assert ok is False


class TestValidateSyntaxBash:
    def test_valid(self):
        ok, err = validate_syntax("#!/bin/bash\necho hello", "bash")
        assert ok is True

    def test_invalid(self):
        # `done` with no matching loop is reliably rejected by bash -n
        ok, err = validate_syntax("done", "bash")
        assert ok is False
        assert err != ""


class TestValidateSyntaxOther:
    def test_unknown_lang_passes_through(self):
        # We can't statically validate ruby/node/etc — just let it through
        ok, err = validate_syntax("puts 'hello'", "ruby")
        assert ok is True
        assert err == ""


# ---------------------------------------------------------------------------
# run_script
# ---------------------------------------------------------------------------

class TestRunScript:
    def test_successful_run(self):
        code = '#!/usr/bin/env python3\nprint("scripy")'
        stdout, stderr, rc = run_script(code, "python3", timeout=5)
        assert rc == 0
        assert "scripy" in stdout

    def test_stderr_captured(self):
        code = "#!/usr/bin/env python3\nimport sys\nsys.stderr.write('oops\\n')"
        stdout, stderr, rc = run_script(code, "python3", timeout=5)
        assert "oops" in stderr

    def test_nonzero_exit(self):
        code = "#!/usr/bin/env python3\nraise SystemExit(1)"
        stdout, stderr, rc = run_script(code, "python3", timeout=5)
        assert rc != 0

    def test_timeout(self):
        code = "#!/usr/bin/env python3\nimport time\ntime.sleep(10)"
        stdout, stderr, rc = run_script(code, "python3", timeout=1)
        assert rc != 0
        assert "timed out" in stderr

    def test_missing_interpreter(self):
        stdout, stderr, rc = run_script("echo hi", "no_such_interpreter_xyz", timeout=5)
        assert rc == 1
        assert "not found" in stderr

    def test_bash_script(self):
        code = "#!/bin/bash\necho 'hello from bash'"
        stdout, stderr, rc = run_script(code, "bash", timeout=5)
        assert rc == 0
        assert "hello from bash" in stdout
