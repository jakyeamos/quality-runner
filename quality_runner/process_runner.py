from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.cache_limits import prune_lru_tree
from quality_runner.cache_modes import default_external_cache_root

LOCAL_COMMAND_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
)

SUPPORTED_PACKAGE_MANAGERS = frozenset({"bun", "npm", "pnpm", "yarn"})
_XDG_CACHE_MAX_ENTRIES = 4096
_XDG_CACHE_MAX_BYTES = 64 * 1024 * 1024


def run_shell_command(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
    return _run_command(command, cwd=cwd, timeout=timeout, shell=True)


def run_command(command: Sequence[str], *, cwd: Path, timeout: int) -> dict[str, object]:
    return _run_command(command, cwd=cwd, timeout=timeout, shell=False)


def _run_command(
    command: str | Sequence[str], *, cwd: Path, timeout: int, shell: bool
) -> dict[str, object]:
    command_text = command if isinstance(command, str) else " ".join(command)
    command_env = local_command_env(cwd, command=command_text)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=command_env,
    )
    process_group_id = _process_group_id(process)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        captured_stdout, captured_stderr = terminate_process_group(
            process, process_group_id=process_group_id
        )
        raise subprocess.TimeoutExpired(
            cmd=error.cmd,
            timeout=error.timeout,
            output=captured_stdout or error.stdout,
            stderr=captured_stderr or error.stderr,
        ) from error
    except BaseException:
        terminate_process_group(process, process_group_id=process_group_id)
        raise
    finally:
        _enforce_xdg_bound(command_env)
    return {"stdout": stdout, "stderr": stderr, "returncode": process.returncode}


def _process_group_id(process: subprocess.Popen[Any]) -> int:
    try:
        return os.getpgid(process.pid)
    except ProcessLookupError:
        # start_new_session=True makes the child pid the process-group id. Keep
        # that stable identifier even if the leader exits before pipe cleanup.
        return process.pid


def terminate_process_group(
    process: subprocess.Popen[Any], *, process_group_id: int | None = None
) -> tuple[str, str]:
    resolved_group_id = process_group_id or _process_group_id(process)
    try:
        try:
            os.killpg(resolved_group_id, signal.SIGTERM)
        except ProcessLookupError:
            return _communicate_after_termination(process)
        wait = getattr(process, "wait", None)
        if not callable(wait):
            return "", ""
        grace_started = time.monotonic()
        with suppress(subprocess.TimeoutExpired):
            wait(timeout=0.2)
        grace_remaining = 0.2 - (time.monotonic() - grace_started)
        if grace_remaining > 0:
            time.sleep(grace_remaining)
        # The group leader can exit after SIGTERM while descendants keep inherited
        # pipes open. Escalate the stored group id regardless of the leader's state.
        with suppress(ProcessLookupError):
            os.killpg(resolved_group_id, signal.SIGKILL)
        return _communicate_after_termination(process)
    except BaseException:
        # A coordinator signal or external interruption must not leave the group
        # alive just because it arrived during the bounded cleanup window.
        with suppress(ProcessLookupError):
            os.killpg(resolved_group_id, signal.SIGKILL)
        raise
    finally:
        _close_process_pipes(process)


def _communicate_after_termination(process: subprocess.Popen[Any]) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=0.2)
    except (OSError, subprocess.SubprocessError):
        return "", ""
    finally:
        _close_process_pipes(process)
    return _text_value(stdout), _text_value(stderr)


def _close_process_pipes(process: subprocess.Popen[Any]) -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(process, name, None)
        close = getattr(stream, "close", None)
        if callable(close):
            with suppress(OSError, ValueError):
                close()


def _text_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def local_command_env(cwd: Path, *, command: str | None = None) -> dict[str, str]:
    env = {
        key: value
        for key in LOCAL_COMMAND_ENV_ALLOWLIST
        if (value := os.environ.get(key)) is not None
    }
    cache_root = cwd / ".quality-runner" / "cache"
    env["UV_CACHE_DIR"] = os.environ.get(
        "UV_CACHE_DIR", str(default_external_cache_root() / "shared-tools" / "uv-v1")
    )
    env["XDG_CACHE_HOME"] = str(_xdg_cache_root(cache_root, command))
    package_manager_root = _package_manager_command_root(cwd, command)
    if (
        package_manager_root is not None
        and (package_manager_root / ".quality-runner" / "copied-dependencies").is_file()
    ):
        # pnpm 11 treats the copied workspace-state path as stale and otherwise
        # starts an implicit install. QR already prepared this locked tree.
        env["pnpm_config_verify_deps_before_run"] = "false"
    package_manager_bin = _cached_package_manager_bin(package_manager_root)
    if package_manager_bin and env.get("PATH"):
        env["PATH"] = f"{package_manager_bin}{os.pathsep}{env['PATH']}"
    return env


def _xdg_cache_root(repo_cache_root: Path, command: str | None) -> Path:
    normalized = f" {command or ''} "
    if any(token in normalized for token in (" qr ", " quality-runner ")):
        return default_external_cache_root() / "shared-tools" / f"quality-runner-{__version__}"
    identity = hashlib.sha256((command or "unspecified").encode("utf-8")).hexdigest()[:16]
    return repo_cache_root / "xdg" / "isolated-v1" / identity


def _enforce_xdg_bound(environment: dict[str, str]) -> None:
    configured = environment.get("XDG_CACHE_HOME")
    if not configured:
        return
    prune_lru_tree(
        owned_root=Path(configured),
        max_entries=_XDG_CACHE_MAX_ENTRIES,
        max_bytes=_XDG_CACHE_MAX_BYTES,
    )


def _cached_package_manager_bin(cwd: Path) -> str | None:
    package_manager = _declared_package_manager(cwd)
    if package_manager is None:
        manager = _lockfile_package_manager(cwd)
        version = None
    else:
        manager, version = package_manager
    if manager is None:
        return None
    cache_roots = (
        Path.home() / ".cache" / "node" / "corepack" / "v1",
        Path.home() / "Library" / "pnpm" / ".tools",
    )
    versions = [version] if version is not None else _cached_versions(cache_roots, manager)
    candidates = [
        root / manager / candidate / "bin" for candidate in versions for root in cache_roots
    ]
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


def _package_manager_command_root(cwd: Path, command: str | None) -> Path:
    if not command:
        return cwd
    match = re.match(r"\s*cd\s+([A-Za-z0-9_./-]+)\s*&&\s*(?:pnpm|yarn|npm|bun)\b", command)
    if not match:
        return cwd
    candidate = (cwd / match.group(1)).resolve()
    try:
        candidate.relative_to(cwd.resolve())
    except ValueError:
        return cwd
    return candidate


def _lockfile_package_manager(cwd: Path) -> str | None:
    for lockfile, manager in (
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
        ("bun.lock", "bun"),
        ("bun.lockb", "bun"),
    ):
        if (cwd / lockfile).is_file():
            return manager
    return None


def _cached_versions(cache_roots: tuple[Path, ...], manager: str) -> list[str]:
    versions = {
        path.name
        for root in cache_roots
        if (manager_root := root / manager).is_dir()
        for path in manager_root.iterdir()
        if path.is_dir()
    }
    return sorted(versions, key=_version_key, reverse=True)


def _version_key(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts) if parts else (0,)


def _declared_package_manager(cwd: Path) -> tuple[str, str] | None:
    manifest = cwd / "package.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    declaration = payload.get("packageManager")
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
