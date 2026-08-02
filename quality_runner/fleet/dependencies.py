from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import hash_text, redact_text

CommandRunner = Callable[..., dict[str, Any]]


def prepare_dynamic_dependencies(
    *,
    worktree: Path,
    source: Path | None = None,
    timeout_seconds: int,
    run_command: CommandRunner,
) -> dict[str, Any]:
    """Prepare only locked, local dependencies in a runtime-owned worktree."""
    package_json = worktree / "package.json"
    result: dict[str, Any]
    documented_setup: dict[str, Any]
    documented_paths: list[Path]
    if source is not None:
        documented_setup, documented_paths = _copy_documented_sibling_roots(
            source=source, worktree=worktree
        )
    else:
        documented_setup, documented_paths = {"status": "passed"}, []
    if documented_setup["status"] != "passed":
        documented_setup["_cleanup_paths"] = [str(path) for path in documented_paths]
        return documented_setup
    if not package_json.is_file():
        result = {
            "status": "not_required",
            "reason": "dependency tree is not required or is present",
        }
        if documented_paths:
            result["documented_sibling_runtime"] = "copied"
        result["_cleanup_paths"] = [str(path) for path in documented_paths]
        return result
    if not _has_declared_dependencies(package_json):
        result = {
            "status": "not_required",
            "reason": "package has no declared dependencies",
        }
        if documented_paths:
            result["documented_sibling_runtime"] = "copied"
        result["_cleanup_paths"] = [str(path) for path in documented_paths]
        return result

    local_setup: dict[str, Any]
    local_paths: list[Path]
    if source is not None:
        local_setup, local_paths = _copy_local_file_dependencies(source=source, worktree=worktree)
    else:
        local_setup, local_paths = {"status": "passed"}, []
    local_paths = [*documented_paths, *local_paths]
    if local_setup["status"] != "passed":
        local_setup["_cleanup_paths"] = [str(path) for path in local_paths]
        return local_setup

    source_dependencies = (source / "node_modules") if source is not None else None
    if source_dependencies is not None and source_dependencies.is_dir():
        if _copy_source_dependencies(source_dependencies, worktree / "node_modules"):
            result = {
                "status": "passed",
                "method": "copied_from_protected_checkout",
                "source_dependency_tree": "present",
            }
            result["_cleanup_paths"] = [str(path) for path in local_paths]
            return result
        return {
            "status": "unavailable",
            "reason": "protected checkout dependency tree could not be copied safely",
            "_cleanup_paths": [str(path) for path in local_paths],
        }

    package_manager = _package_manager_declaration(worktree)
    if package_manager is None:
        result = {
            "status": "unavailable",
            "reason": "JavaScript dependency setup requires a pinned package manager",
        }
        result["_cleanup_paths"] = [str(path) for path in local_paths]
        return result
    manager, lockfile, command = package_manager
    if not (worktree / lockfile).is_file():
        result = {
            "status": "unavailable",
            "package_manager": manager,
            "reason": f"offline dependency setup requires {lockfile}",
        }
        result["_cleanup_paths"] = [str(path) for path in local_paths]
        return result

    setup_timeout = min(max(timeout_seconds, 60), 120)
    try:
        result = run_command(command, cwd=worktree, timeout=setup_timeout)
    except subprocess.TimeoutExpired as error:
        result = {
            "status": "timeout",
            "package_manager": manager,
            "command_hash": hash_text(command),
            "timeout_seconds": setup_timeout,
            "stdout_length": len(str(error.output or "")),
            "stderr_length": len(str(error.stderr or "")),
            "reason": "offline dependency setup exceeded its bounded timeout",
        }
        result["_cleanup_paths"] = [str(path) for path in local_paths]
        return result
    except OSError as error:
        result = {
            "status": "unavailable",
            "package_manager": manager,
            "command_hash": hash_text(command),
            "reason": redact_text(str(error), root=worktree)[:500],
        }
        result["_cleanup_paths"] = [str(path) for path in local_paths]
        return result

    stdout = str(result.get("stdout", ""))
    stderr = str(result.get("stderr", ""))
    if result.get("returncode") != 0:
        result = {
            "status": "unavailable",
            "package_manager": manager,
            "command_hash": hash_text(command),
            "stdout_hash": hash_text(stdout),
            "stderr_hash": hash_text(stderr),
            "stdout_length": len(stdout),
            "stderr_length": len(stderr),
            "reason": "offline dependency setup could not reproduce the locked dependency tree",
        }
        result["_cleanup_paths"] = [str(path) for path in local_paths]
        return result
    result = {
        "status": "passed",
        "package_manager": manager,
        "command_hash": hash_text(command),
        "stdout_hash": hash_text(stdout),
        "stderr_hash": hash_text(stderr),
        "stdout_length": len(stdout),
        "stderr_length": len(stderr),
        "timeout_seconds": setup_timeout,
    }
    result["_cleanup_paths"] = [str(path) for path in local_paths]
    return result


def _has_declared_dependencies(package_json: Path) -> bool:
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    return any(
        isinstance(payload.get(key), dict) and bool(payload[key])
        for key in ("dependencies", "devDependencies", "optionalDependencies")
    )


def _copy_source_dependencies(source: Path, destination: Path) -> bool:
    try:
        shutil.copytree(source, destination, symlinks=True)
    except OSError:
        shutil.rmtree(destination, ignore_errors=True)
        return False
    for path in destination.rglob("*"):
        if not path.is_symlink():
            continue
        try:
            path.resolve().relative_to(destination.resolve())
        except ValueError:
            shutil.rmtree(destination, ignore_errors=True)
            return False
    return True


def _copy_documented_sibling_roots(
    *, source: Path, worktree: Path
) -> tuple[dict[str, Any], list[Path]]:
    wrapper = source / "bin" / "agent-config.mjs"
    try:
        content = wrapper.read_text(encoding="utf-8")
    except OSError:
        return {"status": "passed"}, []
    names = sorted(
        set(
            re.findall(
                r'path\.resolve\(companionRoot,\s*["\']\.\.["\'],\s*["\']([A-Za-z0-9_.-]+)["\']\)',
                content,
            )
        )
    )
    created: list[Path] = []
    for name in names:
        source_path = (source.parent / name).resolve()
        destination_path = (worktree.parent / name).resolve()
        if not source_path.is_dir() or destination_path.exists():
            continue
        try:
            destination_path.relative_to(worktree.parent.resolve())
            shutil.copytree(
                source_path,
                destination_path,
                symlinks=True,
                ignore=shutil.ignore_patterns(
                    ".git",
                    "node_modules",
                    ".quality-runner",
                    "artifacts",
                    "dist",
                    "build",
                    "coverage",
                    ".cache",
                ),
            )
        except OSError:
            _remove_runtime_path(destination_path)
            return {
                "status": "unavailable",
                "reason": "documented sibling runtime could not be copied safely",
            }, created
        created.append(destination_path)
        if not _contained_symlinks(destination_path):
            _remove_runtime_path(destination_path)
            created.pop()
            return {
                "status": "unavailable",
                "reason": "documented sibling runtime contains an escaping symlink",
            }, created
    return {"status": "passed"}, created


def _copy_local_file_dependencies(
    *, source: Path, worktree: Path
) -> tuple[dict[str, Any], list[Path]]:
    try:
        payload = json.loads((worktree / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unavailable", "reason": "package manifest could not be read"}, []
    if not isinstance(payload, dict):
        return {"status": "unavailable", "reason": "package manifest is not an object"}, []
    specs = [
        value
        for key in ("dependencies", "devDependencies", "optionalDependencies")
        if isinstance(payload.get(key), dict)
        for value in payload[key].values()
        if isinstance(value, str) and value.startswith(("file:", "link:"))
    ]
    created: list[Path] = []
    for spec in specs:
        relative = spec.split(":", maxsplit=1)[1]
        source_path = (source / relative).resolve()
        destination_path = (worktree / relative).resolve()
        if destination_path == worktree:
            continue
        try:
            destination_path.relative_to(worktree.parent.resolve())
        except ValueError:
            return {
                "status": "unavailable",
                "reason": "local dependency path escapes the runtime-owned worktree scope",
            }, created
        if not source_path.exists() or destination_path.exists():
            return {
                "status": "unavailable",
                "reason": "declared local dependency is unavailable or destination already exists",
            }, created
        try:
            if source_path.is_dir():
                shutil.copytree(source_path, destination_path, symlinks=True)
            else:
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination_path)
        except OSError:
            return {
                "status": "unavailable",
                "reason": "declared local dependency could not be copied safely",
            }, created
        created.append(destination_path)
        if destination_path.is_dir() and not _contained_symlinks(destination_path):
            _remove_runtime_path(destination_path)
            created.pop()
            return {
                "status": "unavailable",
                "reason": "declared local dependency contains an escaping symlink",
            }, created
    return {"status": "passed"}, created


def _contained_symlinks(root: Path) -> bool:
    for path in root.rglob("*"):
        if not path.is_symlink():
            continue
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            return False
    return True


def _remove_runtime_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        with suppress(FileNotFoundError):
            path.unlink()


def _package_manager_declaration(worktree: Path) -> tuple[str, str, str] | None:
    try:
        payload = json.loads((worktree / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    declaration = payload.get("packageManager")
    if not isinstance(declaration, str) or "@" not in declaration:
        return None
    manager, version = declaration.split("@", maxsplit=1)
    if manager not in {"bun", "npm", "pnpm", "yarn"} or not version:
        return None
    if "/" in version or "\\" in version:
        return None
    lockfiles = {
        "bun": "bun.lock",
        "npm": "package-lock.json",
        "pnpm": "pnpm-lock.yaml",
        "yarn": "yarn.lock",
    }
    commands = {
        "bun": "bun install --offline --no-save --no-scripts",
        "npm": "npm ci --offline --ignore-scripts --no-audit --no-fund",
        "pnpm": "pnpm install --offline --frozen-lockfile --ignore-scripts --reporter=append-only",
        "yarn": "yarn install --offline --immutable --mode=skip-builds",
    }
    return manager, lockfiles[manager], commands[manager]


remove_runtime_path = _remove_runtime_path
