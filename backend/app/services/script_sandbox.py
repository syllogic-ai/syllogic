"""
Sandboxed execution of AI-generated transformation scripts.

Security measures:
- AST-based validation blocks dangerous imports (network, subprocess, etc.)
- Subprocess execution with CPU time and memory limits via resource module
- Strict timeout enforcement via subprocess.run timeout
- Minimal environment variables passed to child process
"""
import ast
import json
import os
import resource
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)

DISALLOWED_MODULES = {
    "socket", "http", "urllib", "requests", "httpx",
    "subprocess", "shutil", "signal", "ctypes",
    "multiprocessing", "threading", "asyncio",
    "webbrowser", "ftplib", "smtplib", "telnetlib",
    "xmlrpc", "pickle", "shelve", "code", "codeop",
    "compileall", "py_compile",
}

TIMEOUT_SECONDS = 60
MAX_MEMORY_BYTES = 512 * 1024 * 1024  # 512 MB
MAX_CPU_SECONDS = 30


def validate_script(script_source: str) -> Tuple[bool, Optional[str]]:
    """Validate a generated script for safety using AST analysis."""
    try:
        tree = ast.parse(script_source)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_root = alias.name.split(".")[0]
                if module_root in DISALLOWED_MODULES:
                    return False, f"Disallowed import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_root = node.module.split(".")[0]
                if module_root in DISALLOWED_MODULES:
                    return False, f"Disallowed import: from {node.module}"

    return True, None


def _set_limits():
    """Pre-exec function to set resource limits in the child process."""
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
    except (ValueError, resource.error):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS))
    except (ValueError, resource.error):
        pass


def execute_script(
    script_source: str,
    file_path: str,
) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Execute a transformation script in a sandboxed subprocess.

    The script must define a ``transform(file_path)`` function that returns
    a list of dicts with standardised field names.

    Returns (success, result_list_or_none, error_or_none).
    """
    is_valid, error = validate_script(script_source)
    if not is_valid:
        return False, None, f"Script validation failed: {error}"

    wrapper = (
        "import json, sys\n"
        + script_source
        + "\n\n"
        "if __name__ == '__main__':\n"
        "    _fp = sys.argv[1]\n"
        "    try:\n"
        "        _result = transform(_fp)\n"
        "        print(json.dumps(_result, default=str))\n"
        "    except Exception as _e:\n"
        "        import traceback\n"
        "        print(json.dumps({'error': str(_e), 'traceback': traceback.format_exc()}), file=sys.stderr)\n"
        "        sys.exit(1)\n"
    )

    script_fd, script_path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(script_fd, "w") as f:
            f.write(wrapper)

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": tempfile.gettempdir(),
            "PYTHONPATH": "",
            "LANG": "C.UTF-8",
        }

        result = subprocess.run(
            [sys.executable, script_path, file_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            preexec_fn=_set_limits,
            env=env,
        )

        if result.returncode != 0:
            error_output = result.stderr.strip()
            if not error_output:
                error_output = f"Script exited with code {result.returncode}"
            try:
                err_json = json.loads(error_output)
                error_output = err_json.get("error", error_output)
                if err_json.get("traceback"):
                    error_output += "\n" + err_json["traceback"]
            except (json.JSONDecodeError, AttributeError):
                pass
            return False, None, error_output

        stdout = result.stdout.strip()
        if not stdout:
            return False, None, "Script produced no output"

        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            return False, None, f"Script output is not valid JSON (first 500 chars): {stdout[:500]}"

        if not isinstance(output, list):
            return False, None, f"Script must return a list, got {type(output).__name__}"

        return True, output, None

    except subprocess.TimeoutExpired:
        return False, None, f"Script execution timed out after {TIMEOUT_SECONDS}s"
    except Exception as e:
        return False, None, f"Execution error: {e}"
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass
