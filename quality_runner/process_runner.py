from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Any


def run_shell_command(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=local_command_env(cwd),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        captured_stdout, captured_stderr = terminate_process_group(process)
        raise subprocess.TimeoutExpired(
            cmd=error.cmd,
            timeout=error.timeout,
            output=captured_stdout or error.stdout,
            stderr=captured_stderr or error.stderr,
        ) from error
    except BaseException:
        terminate_process_group(process)
        raise
    return {
        "stdout": stdout,
        "stderr": stderr,
        "returncode": process.returncode,
    }


def terminate_process_group(process: subprocess.Popen[Any]) -> tuple[str, str]:
    try:
        process_group_id = os.getpgid(process.pid)
    except ProcessLookupError:
        return "", ""
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return "", ""
    wait = getattr(process, "wait", None)
    if not callable(wait):
        return "", ""
    try:
        wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            return _communicate_after_termination(process)
    return _communicate_after_termination(process)


def _communicate_after_termination(process: subprocess.Popen[Any]) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=0.2)
    except (OSError, subprocess.SubprocessError):
        return "", ""
    return _text_value(stdout), _text_value(stderr)


def _text_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def local_command_env(cwd: Path) -> dict[str, str]:
    env = dict(os.environ)
    cache_root = cwd / ".quality-runner" / "cache"
    env["UV_CACHE_DIR"] = str(cache_root / "uv")
    env["XDG_CACHE_HOME"] = str(cache_root / "xdg")
    return env
