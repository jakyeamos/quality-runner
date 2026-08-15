from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import hash_text


def compatible_dependency_source(
    repository: dict[str, Any], *, worktree: Path, default: Path
) -> Path:
    target_signature = _javascript_dependency_signature(worktree)
    if target_signature is None:
        return default
    candidates = [default]
    for checkout in repository.get("checkouts", []):
        if not isinstance(checkout, dict) or checkout.get("exists") is not True:
            continue
        raw_path = checkout.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve()
        if path not in candidates:
            candidates.append(path)
    for candidate in candidates:
        if _javascript_dependency_signature(
            candidate
        ) == target_signature and _has_javascript_dependency_tree(candidate):
            return candidate
    return default


def compatible_local_dependency_source(
    repository: dict[str, Any], *, worktree: Path, default: Path
) -> Path:
    """Resolve target-declared local dependencies from a canonical checkout parent."""
    candidates = [default]
    for checkout in repository.get("checkouts", []):
        if not isinstance(checkout, dict) or checkout.get("exists") is not True:
            continue
        raw_path = checkout.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve()
        if path not in candidates:
            candidates.append(path)
    return next(
        (
            candidate
            for candidate in candidates
            if _declared_local_dependencies_available(worktree=worktree, source=candidate)
        ),
        default,
    )


def _declared_local_dependencies_available(*, worktree: Path, source: Path) -> bool:
    try:
        payload = json.loads((worktree / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    specs = [
        value
        for key in ("dependencies", "devDependencies", "optionalDependencies")
        if isinstance(payload.get(key), dict)
        for value in payload[key].values()
        if isinstance(value, str) and value.startswith(("file:", "link:"))
    ]
    return bool(specs) and all(
        (source / spec.split(":", maxsplit=1)[1]).resolve().exists() for spec in specs
    )


def _javascript_dependency_signature(root: Path) -> dict[str, Any] | None:
    manifests = [root / "package.json", *sorted(root.glob("*/package.json"))]
    signatures: dict[str, Any] = {}
    for manifest in manifests:
        if not manifest.is_file():
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        relative = manifest.relative_to(root).as_posix()
        workspace = manifest.parent
        lockfile = next(
            (
                workspace / name
                for name in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock")
                if (workspace / name).is_file()
            ),
            None,
        )
        try:
            lock_hash = hash_text(lockfile.read_text(encoding="utf-8")) if lockfile else None
        except OSError:
            return None
        signatures[relative] = {
            "package_manager": payload.get("packageManager"),
            "dependencies": payload.get("dependencies", {}),
            "dev_dependencies": payload.get("devDependencies", {}),
            "optional_dependencies": payload.get("optionalDependencies", {}),
            "lockfile": lockfile.name if lockfile else None,
            "lock_hash": lock_hash,
        }
    return signatures or None


def _has_javascript_dependency_tree(root: Path) -> bool:
    if (root / "node_modules").is_dir():
        return True
    return any(
        manifest.parent.joinpath("node_modules").is_dir()
        for manifest in root.glob("*/package.json")
    )
