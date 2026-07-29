from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.cache_modes import CacheMode, cache_directory, resolve_cache_mode
from quality_runner.schema_constants import REPO_SCAN_SCHEMA

SCHEMA = "quality-runner-repository-inventory-cache-v0.1"


def load_or_build_inventory(
    repo_root: Path,
    *,
    config: dict[str, Any] | None,
    ci_checks: list[dict[str, str | None]] | None,
    extra_warnings: list[dict[str, str]] | None,
    build: Any,
    cache_mode: CacheMode | str = "repo",
    cache_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    mode = resolve_cache_mode(cache_mode)
    key = inventory_key(
        root,
        config=config,
        ci_checks=ci_checks,
        extra_warnings=extra_warnings,
    )
    path = cache_directory(
        root,
        mode=mode,
        cache_root=cache_root,
        component="repository-inventory-v1",
    ) / f"{key}.json"
    if mode == "disabled":
        payload = dict(build())
        payload["inventory_cache"] = _evidence(
            status="disabled",
            key=key,
            path=path,
            persisted=False,
            mode=mode,
            disabled_reason="diagnostic-cache-disabled",
        )
        return payload
    cached = _read(path)
    if cached is not None:
        payload = dict(cached)
        payload["inventory_cache"] = _evidence(status="hit", key=key, path=path, mode=mode)
        return payload
    payload = dict(build())
    payload["inventory_cache"] = _evidence(status="miss", key=key, path=path, mode=mode)
    _write(path, payload)
    return payload


def inventory_key(
    root: Path,
    *,
    config: dict[str, Any] | None,
    ci_checks: list[dict[str, str | None]] | None,
    extra_warnings: list[dict[str, str]] | None,
) -> str:
    state = {
        "quality_runner_version": __version__,
        "repo_root": str(root),
        "config": config or {},
        "ci_checks": ci_checks or [],
        "extra_warnings": extra_warnings or [],
        "git_state": _git_state(root),
    }
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _git_state(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"head": None, "dirty_files": []}
    head = _git(root, ["rev-parse", "HEAD"])
    status = _git(root, ["status", "--porcelain=v1", "-z"])
    files: list[dict[str, str | None]] = []
    entries = status.split("\0") if status else []
    for entry in entries:
        if len(entry) < 4:
            continue
        relative = entry[3:] if entry[2] == " " else entry[3:]
        path = root / relative
        digest = _file_digest(path)
        files.append({"path": relative, "sha256": digest})
    return {"head": head, "dirty_files": files}


def _git(root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _file_digest(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _read(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("schema") == REPO_SCAN_SCHEMA else None


def _write(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="inventory-", suffix=".json", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except OSError:
        return


def _evidence(
    *,
    status: str,
    key: str,
    path: Path,
    persisted: bool = True,
    mode: CacheMode = "repo",
    disabled_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": status,
        "key": key,
        "cache_path": str(path),
        "persisted": persisted,
        "cache_mode": mode,
        "disabled_reason": disabled_reason if not persisted else None,
    }
