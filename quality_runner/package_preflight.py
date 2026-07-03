from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import PACKAGE_MANAGER_PREFLIGHT_SCHEMA

LOCKFILE_MANAGERS = {
    "pnpm-lock.yaml": "pnpm",
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "bun.lock": "bun",
    "bun.lockb": "bun",
}


def build_package_manager_preflight(repo_root: Path, scan: dict[str, Any]) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    lockfiles = sorted(name for name in LOCKFILE_MANAGERS if (root / name).exists())
    nested_lockfiles = _nested_lockfiles(root=root, scan=scan)
    declared = _declared_package_manager(root)
    detected = _string_or_none(scan.get("package_manager")) or declared
    warnings = _warnings(
        declared=declared,
        detected=detected,
        lockfiles=lockfiles,
        nested_lockfiles=nested_lockfiles,
    )
    return {
        "schema": PACKAGE_MANAGER_PREFLIGHT_SCHEMA,
        "status": "warning" if warnings else "ok",
        "package_manager": detected,
        "declared_package_manager": declared,
        "lockfiles": lockfiles,
        "nested_lockfiles": nested_lockfiles,
        "warnings": warnings,
    }


def _declared_package_manager(root: Path) -> str | None:
    package_json = root / "package.json"
    if not package_json.exists():
        return None
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    package_manager = payload.get("packageManager")
    if not isinstance(package_manager, str) or not package_manager:
        return None
    return package_manager.split("@", maxsplit=1)[0]


def _warnings(
    *,
    declared: str | None,
    detected: str | None,
    lockfiles: list[str],
    nested_lockfiles: list[dict[str, str]],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    lockfile_managers = {LOCKFILE_MANAGERS[name] for name in lockfiles}
    if len(lockfile_managers) > 1:
        warnings.append(
            {
                "code": "multiple_lockfiles",
                "message": "Multiple JavaScript package-manager lockfiles are present.",
                "path": ".",
            }
        )
    if declared is not None and detected is not None and declared != detected:
        warnings.append(
            {
                "code": "declared_package_manager_mismatch",
                "message": "Declared packageManager differs from detected package-manager state.",
                "path": "package.json",
            }
        )
    root_managers = {LOCKFILE_MANAGERS[name] for name in lockfiles}
    nested_managers = {item["package_manager"] for item in nested_lockfiles}
    if nested_managers - root_managers:
        warnings.append(
            {
                "code": "nested_package_manager_lockfiles",
                "message": "Nested JavaScript package-manager lockfiles are present.",
                "path": ".",
            }
        )
    return warnings


def _nested_lockfiles(*, root: Path, scan: dict[str, Any]) -> list[dict[str, str]]:
    workspaces = scan.get("workspaces")
    if not isinstance(workspaces, list):
        return []
    found: list[dict[str, str]] = []
    for workspace in workspaces:
        if not isinstance(workspace, dict) or workspace.get("kind") != "javascript":
            continue
        path = workspace.get("path")
        if not isinstance(path, str) or not path or path == ".":
            continue
        workspace_root = root / path
        for lockfile, manager in LOCKFILE_MANAGERS.items():
            lockfile_path = workspace_root / lockfile
            if lockfile_path.exists():
                found.append(
                    {
                        "path": f"{path}/{lockfile}",
                        "package_manager": manager,
                    }
                )
    return sorted(found, key=lambda item: item["path"])


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
