"""Package-manager and workspace evidence for repository hygiene reports."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

EXPECTED_PNPM_VERSION = "11.9.0"

_SKIP_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".next",
        ".pnpm-store",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "DerivedData",
        "build",
        "coverage",
        "dist",
        "node_modules",
    }
)
_FIXTURE_DIRECTORY_NAMES = frozenset(
    {"example", "examples", "fixture", "fixtures", "test", "tests"}
)
_WORKSPACE_DIRECTORY_NAMES = frozenset({"apps", "packages", "components", "modules"})
_LOCKFILE_NAMES = frozenset(
    {"pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb"}
)


def _package_manager_state(
    root: Path,
    tracked_paths: list[str],
    languages: set[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    all_package_paths = _package_json_paths(root)
    workspace_file = root / "pnpm-workspace.yaml"
    managed_package_paths = (
        all_package_paths if (root / "package.json").exists() or workspace_file.exists() else []
    )
    nested_package_roots = [
        _nested_package_root_state(root, path)
        for path in all_package_paths
        if path not in managed_package_paths
    ]
    applicable = bool(managed_package_paths) or bool({"javascript", "typescript"} & languages)
    package_values: list[dict[str, str]] = []
    package_documents: dict[str, dict[str, Any]] = {}
    parse_errors: list[str] = []
    for path in managed_package_paths:
        relative = path.relative_to(root).as_posix()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            parse_errors.append(f"{relative}: {error}")
            continue
        if not isinstance(document, dict):
            parse_errors.append(f"{relative}: package.json must contain an object")
            continue
        package_documents[relative] = document
        package_manager = document.get("packageManager")
        if isinstance(package_manager, str) and package_manager:
            package_values.append({"path": relative, "value": package_manager})

    lockfiles = sorted(
        path for path in tracked_paths if PurePosixPath(path).name in _LOCKFILE_NAMES
    )
    pnpm_lock = "pnpm-lock.yaml" in lockfiles
    manager_name, manager_version = _parse_package_manager(package_values)
    version_exception = config.get("pnpm_version_exception")
    package_manager_exception = config.get("package_manager_exception")
    package_manager_exception = (
        package_manager_exception.strip()
        if isinstance(package_manager_exception, str) and package_manager_exception.strip()
        else None
    )
    violations: list[dict[str, Any]] = []
    violations.extend(
        {
            "code": "package-json-invalid",
            "path": item.split(":", 1)[0],
            "severity": "error",
            "message": item,
        }
        for item in parse_errors
    )
    if not applicable:
        manager_status = "not_applicable"
    elif package_manager_exception is not None:
        manager_status = "exception"
    else:
        if not pnpm_lock:
            violations.append(
                {
                    "code": "pnpm-lockfile-missing",
                    "path": "pnpm-lock.yaml",
                    "severity": "error",
                    "message": "JavaScript/TypeScript repositories require a pnpm lockfile.",
                }
            )
        if any(Path(path).name != "pnpm-lock.yaml" for path in lockfiles):
            violations.append(
                {
                    "code": "package-manager-lock-conflict",
                    "path": "",
                    "severity": "error",
                    "message": "Conflicting npm, Yarn, or Bun lockfiles are present; migrate deliberately.",
                    "lockfiles": lockfiles,
                }
            )
        if manager_name != "pnpm" or manager_version != EXPECTED_PNPM_VERSION:
            if isinstance(version_exception, str) and version_exception.strip():
                manager_status = "exception"
            else:
                manager_status = "noncompliant"
                expected = f"pnpm@{EXPECTED_PNPM_VERSION}"
                actual = (
                    f"{manager_name}@{manager_version}"
                    if manager_name and manager_version
                    else manager_name or "missing"
                )
                violations.append(
                    {
                        "code": "pnpm-version-pin-missing",
                        "path": "package.json",
                        "severity": "error",
                        "message": f"Expected packageManager {expected}; found {actual}.",
                    }
                )
        else:
            manager_status = "compliant"
    workspace = _workspace_state(root, package_documents, managed_package_paths, pnpm_lock)
    return {
        "applicable": applicable,
        "status": manager_status,
        "expected": f"pnpm@{EXPECTED_PNPM_VERSION}" if applicable else None,
        "manager": manager_name,
        "version": manager_version,
        "package_json_paths": sorted(package_documents),
        "nested_package_roots": nested_package_roots,
        "lockfiles": lockfiles,
        "pnpm_lockfile": pnpm_lock,
        "version_exception": version_exception if isinstance(version_exception, str) else None,
        "package_manager_exception": package_manager_exception,
        "violations": violations,
        "workspace": workspace,
    }


def _package_json_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for directory, directory_names, filenames in os.walk(root):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in _SKIP_DIRECTORY_NAMES and not name.startswith(".")
        )
        if "package.json" in filenames:
            paths.append(Path(directory) / "package.json")
    return sorted(paths)


def _nested_package_root_state(root: Path, path: Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    parts = {part.lower() for part in PurePosixPath(relative).parts}
    fixture = bool(parts & _FIXTURE_DIRECTORY_NAMES)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        document = {}
    package_manager = document.get("packageManager") if isinstance(document, dict) else None
    lockfiles = sorted(
        candidate.name
        for candidate in path.parent.iterdir()
        if candidate.is_file() and candidate.name in _LOCKFILE_NAMES
    )
    return {
        "path": relative,
        "scope": "fixture" if fixture else "nested-root",
        "enforcement": "report-only" if fixture else "separate-root-check",
        "package_manager": package_manager if isinstance(package_manager, str) else None,
        "lockfiles": lockfiles,
    }


def _parse_package_manager(values: list[dict[str, str]]) -> tuple[str | None, str | None]:
    if not values:
        return None, None
    value = values[0]["value"]
    name, separator, version = value.partition("@")
    if not separator:
        return value, None
    return name, version


def _workspace_state(
    root: Path,
    documents: dict[str, dict[str, Any]],
    package_paths: list[Path],
    pnpm_lock: bool,
) -> dict[str, Any]:
    relative_paths = sorted(documents)
    workspace_file = root / "pnpm-workspace.yaml"
    root_document = documents.get("package.json", {})
    declared = root_document.get("workspaces") if isinstance(root_document, dict) else None
    product_paths = [
        path
        for path in relative_paths
        if path != "package.json"
        and PurePosixPath(path).parts
        and PurePosixPath(path).parts[0].lower() in _WORKSPACE_DIRECTORY_NAMES
        and not any(part.lower() in _FIXTURE_DIRECTORY_NAMES for part in PurePosixPath(path).parts)
    ]
    clear_product_workspace = len(product_paths) > 0 and len(package_paths) > 1
    return {
        "file": workspace_file.exists(),
        "package_count": len(package_paths),
        "package_paths": relative_paths,
        "root_workspaces_declared": isinstance(declared, (list, dict)),
        "clear_product_workspace": clear_product_workspace,
        "missing_workspace_file": clear_product_workspace
        and not workspace_file.exists()
        and pnpm_lock,
        "catalogs": _workspace_catalog_state(workspace_file),
    }


def _workspace_catalog_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False, "references": []}
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return {"present": True, "references": [], "readable": False}
    references = [line.strip() for line in content.splitlines() if "catalog:" in line]
    return {"present": True, "references": references, "readable": True}
