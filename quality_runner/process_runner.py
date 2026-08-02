from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, cast

LOCAL_COMMAND_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
)

SUPPORTED_PACKAGE_MANAGERS = frozenset({"bun", "npm", "pnpm", "yarn"})


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
    env = {
        key: value
        for key in LOCAL_COMMAND_ENV_ALLOWLIST
        if (value := os.environ.get(key)) is not None
    }
    cache_root = cwd / ".quality-runner" / "cache"
    env["UV_CACHE_DIR"] = str(cache_root / "uv")
    env["XDG_CACHE_HOME"] = str(cache_root / "xdg")
    package_manager_bin = _cached_package_manager_bin(cwd)
    if package_manager_bin and env.get("PATH"):
        env["PATH"] = f"{package_manager_bin}{os.pathsep}{env['PATH']}"
    return env


def _cached_package_manager_bin(cwd: Path) -> str | None:
    package_manager = _declared_package_manager(cwd)
    if package_manager is None:
        return None
    manager, version = package_manager
    cache_roots = (
        Path.home() / ".cache" / "node" / "corepack" / "v1",
        Path.home() / "Library" / "pnpm" / ".tools",
    )
    candidates = [root / manager / version / "bin" for root in cache_roots]
    for candidate in candidates:
        if (candidate / manager).is_file():
            return str(candidate)
    for candidate in candidates:
        entry = _package_manager_script(candidate, manager)
        if entry is None:
            continue
        shim = _create_package_manager_shim(cwd, manager, entry)
        if shim is not None:
            return shim
    return None


def _declared_package_manager(cwd: Path) -> tuple[str, str] | None:
    manifest = cwd / "package.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    declaration = cast(dict[str, Any], payload).get("packageManager")
    if not isinstance(declaration, str):
        return None
    manager, separator, version = declaration.partition("@")
    if not separator or manager not in SUPPORTED_PACKAGE_MANAGERS or not version:
        return None
    if "/" in version or "\\" in version:
        return None
    return manager, version.split("+", 1)[0]


def _package_manager_script(directory: Path, manager: str) -> Path | None:
    for name in (f"{manager}.cjs", f"{manager}.mjs"):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _create_package_manager_shim(cwd: Path, manager: str, script: Path) -> str | None:
    node = shutil.which("node")
    if node is None:
        return None
    shim_directory = cwd / ".quality-runner" / "cache" / "package-managers" / "bin"
    shim = shim_directory / manager
    content = f'#!/bin/sh\nexec {shlex.quote(node)} {shlex.quote(str(script))} "$@"\n'
    try:
        shim_directory.mkdir(parents=True, exist_ok=True)
        if not shim.exists() or shim.read_text(encoding="utf-8") != content:
            shim.write_text(content, encoding="utf-8")
        shim.chmod(0o755)
    except OSError:
        return None
    return str(shim_directory)
