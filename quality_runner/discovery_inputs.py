from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from quality_runner.scan_exclusions import is_scan_path_allowed, iter_allowed_paths

MAX_DISCOVERY_TEXT_BYTES = 1_000_000
MAX_WORKSPACES = 200


def _read_package_json(
    root: Path, path: str = "package.json"
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    package_json_path = root / path
    if not package_json_path.exists():
        return {}, []
    try:
        payload = json.loads(package_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, [
            {
                "code": "invalid_package_json",
                "message": f"{path} could not be parsed as JSON",
                "path": path,
            }
        ]
    if not isinstance(payload, dict):
        return {}, [
            {
                "code": "invalid_package_json_shape",
                "message": f"{path} must contain a JSON object",
                "path": path,
            }
        ]
    return payload, []


def _read_pyproject(
    root: Path, path: str = "pyproject.toml"
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    pyproject_path = root / path
    if not pyproject_path.exists():
        return {}, []
    try:
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}, [
            {
                "code": "invalid_pyproject_toml",
                "message": f"{path} could not be parsed as TOML",
                "path": path,
            }
        ]
    if not isinstance(payload, dict):
        return {}, [
            {
                "code": "invalid_pyproject_toml_shape",
                "message": f"{path} must contain a TOML table",
                "path": path,
            }
        ]
    return payload, []


def _package_scripts(package_json: dict[str, Any]) -> dict[str, str]:
    scripts = package_json.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {
        str(name): command
        for name, command in scripts.items()
        if isinstance(name, str) and isinstance(command, str) and command
    }


def _workspace_manifests(
    root: Path,
    scan_exclusions: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    manifests: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    for manifest_name, kind in (
        ("pyproject.toml", "python"),
        ("package.json", "javascript"),
        ("Cargo.toml", "rust"),
        ("go.mod", "go"),
    ):
        for manifest in iter_allowed_paths(root, scan_exclusions):
            if (
                manifest.name != manifest_name
                or manifest.parent == root
                or not manifest.is_file()
                or not is_scan_path_allowed(root, manifest, scan_exclusions)
            ):
                continue
            relative_manifest = manifest.relative_to(root).as_posix()
            if relative_manifest in seen_paths:
                continue
            seen_paths.add(relative_manifest)
            workspace_path = manifest.parent.relative_to(root).as_posix()
            manifests.append(
                {
                    "path": workspace_path,
                    "kind": kind,
                    "manifest": relative_manifest,
                }
            )

            if manifest_name == "pyproject.toml":
                _, manifest_warnings = _read_pyproject(root, relative_manifest)
                warnings.extend(manifest_warnings)
            elif manifest_name == "package.json":
                _, manifest_warnings = _read_package_json(root, relative_manifest)
                warnings.extend(manifest_warnings)

    manifests.sort(key=lambda workspace: (workspace["path"], workspace["manifest"]))
    if len(manifests) > MAX_WORKSPACES:
        manifests = manifests[:MAX_WORKSPACES]
        warnings.append(
            {
                "code": "workspace_scan_limit_reached",
                "message": f"workspace discovery reached the {MAX_WORKSPACES} workspace limit",
                "path": "workspaces",
            }
        )
    return manifests, warnings


def _read_text(path: Path) -> str:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_DISCOVERY_TEXT_BYTES:
            return ""
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
