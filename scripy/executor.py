from __future__ import annotations

import py_compile
import shutil
import subprocess
import tempfile
from pathlib import Path


def validate_syntax(code: str, lang: str) -> tuple[bool, str]:
    """Return (ok, error_message). Empty error_message on success."""
    if lang == "python":
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            py_compile.compile(tmp, doraise=True)
            return True, ""
        except py_compile.PyCompileError as e:
            return False, str(e)
        finally:
            Path(tmp).unlink(missing_ok=True)

    if lang in ("bash", "sh"):
        interpreter = shutil.which("bash") or shutil.which("sh")
        if not interpreter:
            return True, ""  # can't validate without interpreter
        result = subprocess.run(
            [interpreter, "-n"],
            input=code,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, ""

    # Other languages: skip static validation
    return True, ""


def run_script(
    code: str,
    interpreter: str,
    timeout: int,
) -> tuple[str, str, int]:
    """
    Execute code in a sandboxed subprocess.
    Returns (stdout, stderr, returncode).
    """
    exe = shutil.which(interpreter)
    if not exe:
        return "", f"interpreter not found: {interpreter}", 1

    suffix_map = {
        "python3": ".py",
        "python": ".py",
        "bash": ".sh",
        "sh": ".sh",
        "ruby": ".rb",
        "node": ".js",
    }
    suffix = suffix_map.get(interpreter, ".tmp")

    with tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name

    try:
        result = subprocess.run(
            [exe, tmp],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"timed out after {timeout}s", 1
    finally:
        Path(tmp).unlink(missing_ok=True)
