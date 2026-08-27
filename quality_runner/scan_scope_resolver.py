from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.scan_exclusions import (
    SCAN_EXCLUSION_MODULES,
    SCAN_EXCLUSION_SCOPE_ALL,
    effective_scan_exclusions_by_module,
)

CONFIG_FILE_NAME = ".quality-runner.toml"
SCAN_SCOPE_RESOLVER = "quality-runner-effective-scan-scope-v1"


def resolve_scan_config(
    repo_root: Path,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the repository config used by scope resolution."""
    if config is not None:
        return config
    from quality_runner.config import load_repo_config

    return load_repo_config(repo_root.expanduser().resolve())


def resolve_effective_scan_scope(
    repo_root: Path,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve exclusions and provenance shared by inspect and refresh artifacts."""
    root = repo_root.expanduser().resolve()
    resolved_config = resolve_scan_config(root, config)
    exclusions_by_module = effective_scan_exclusions_by_module(root, resolved_config)
    config_path = _config_path(resolved_config, root)
    config_file = root / CONFIG_FILE_NAME
    config_sha256 = _file_sha256(config_file)
    config_warnings = _config_warnings(resolved_config)
    config_unavailable = config_path is not None and (
        not config_file.is_file() or config_sha256 is None
    )
    policy = _scope_policy(resolved_config)
    fingerprint_payload = {
        "resolver": SCAN_SCOPE_RESOLVER,
        "config_path": config_path,
        "config_sha256": config_sha256,
        "effective_scan_exclusions_by_module": exclusions_by_module,
        "policy": policy,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    metadata: dict[str, Any] = {
        "status": "unavailable" if config_warnings or config_unavailable else "available",
        "resolver": SCAN_SCOPE_RESOLVER,
        "fingerprint": f"sha256:{fingerprint}",
        "config_path": config_path,
        "config_sha256": config_sha256,
        "effective_scan_exclusions": list(exclusions_by_module[SCAN_EXCLUSION_SCOPE_ALL]),
        "effective_scan_exclusions_by_module": {
            module: list(patterns) for module, patterns in exclusions_by_module.items()
        },
        "included_file_count": {
            module: None for module in (SCAN_EXCLUSION_SCOPE_ALL, *SCAN_EXCLUSION_MODULES)
        },
        "cache": {
            "status": "disabled",
            "reused": False,
            "reason": "analysis cache is not configured for this compatibility workflow",
        },
        "provenance": {
            "quality_runner_version": __version__,
            "config_path": config_path,
            "config_sha256": config_sha256,
        },
    }
    if config_warnings:
        metadata["warnings"] = config_warnings
        metadata["reason"] = "repository configuration emitted warnings"
    elif config_unavailable:
        metadata["reason"] = "repository configuration provenance is unavailable"
    return metadata


def update_scan_scope_counts(
    scan: dict[str, Any],
    counts: dict[str, int],
) -> dict[str, Any]:
    """Attach discovered per-module file counts without changing scope identity."""
    raw_scope = scan.get("scan_scope")
    scope = _mapping(cast(object, raw_scope)) if isinstance(raw_scope, dict) else {}
    current_counts = scope.get("included_file_count")
    included_counts = (
        _mapping(cast(object, current_counts)) if isinstance(current_counts, dict) else {}
    )
    included_counts.update(counts)
    scope["included_file_count"] = included_counts
    scan["scan_scope"] = scope
    scan["included_file_count"] = included_counts
    if isinstance(scope.get("cache"), dict):
        scan["cache"] = scope["cache"]
    return scope


def artifact_scan_scope(
    scan: dict[str, Any],
    *,
    repo_root: Path,
    config: dict[str, Any],
    module: str,
    scan_exclusions: list[str] | tuple[str, ...],
    included_file_count: int,
) -> dict[str, Any]:
    """Validate a module's actual scope and return artifact-safe metadata."""
    raw_scope = scan.get("scan_scope")
    scope = (
        _mapping(cast(object, raw_scope))
        if isinstance(raw_scope, dict)
        else resolve_effective_scan_scope(repo_root, config)
    )
    actual_exclusions = list(scan_exclusions)
    reasons: list[str] = []
    if scope.get("status") != "available":
        reasons.append(str(scope.get("reason") or "effective scan scope is unavailable"))
    effective_by_module = scope.get("effective_scan_exclusions_by_module")
    expected_exclusions = (
        _mapping(cast(object, effective_by_module)).get(module)
        if isinstance(effective_by_module, dict)
        else None
    )
    if not isinstance(expected_exclusions, list):
        reasons.append(f"resolver did not provide {module} exclusions")
    elif expected_exclusions != actual_exclusions:
        reasons.append(f"{module} exclusions differ from the resolved scope")
    if type(included_file_count) is not int or included_file_count < 0:
        reasons.append("included file count is unavailable")
    if not isinstance(scope.get("cache"), dict):
        reasons.append("cache provenance is unavailable")
    if not isinstance(scope.get("provenance"), dict):
        reasons.append("scope provenance is unavailable")

    artifact_scope = dict(scope)
    artifact_scope["module"] = module
    artifact_scope["effective_scan_exclusions"] = actual_exclusions
    artifact_scope["included_file_count"] = included_file_count
    if not isinstance(artifact_scope.get("cache"), dict):
        artifact_scope["cache"] = {
            "status": "unavailable",
            "reused": False,
            "reason": "cache provenance is unavailable",
        }
    if not isinstance(artifact_scope.get("provenance"), dict):
        artifact_scope["provenance"] = {
            "quality_runner_version": __version__,
        }
    if reasons:
        artifact_scope["status"] = "unavailable"
        artifact_scope["reason"] = "; ".join(dict.fromkeys(reasons))
    else:
        artifact_scope["status"] = "available"
        artifact_scope.pop("reason", None)
    return artifact_scope


def _config_path(config: dict[str, Any], root: Path) -> str | None:
    configured_path = config.get("path")
    if isinstance(configured_path, str) and configured_path:
        return configured_path
    return CONFIG_FILE_NAME if (root / CONFIG_FILE_NAME).is_file() else None


def _config_warnings(config: dict[str, Any]) -> list[dict[str, str]]:
    warnings = config.get("warnings")
    if not isinstance(warnings, list):
        return []
    warning_items = cast(list[object], warnings)
    return [_string_mapping(cast(object, item)) for item in warning_items if isinstance(item, dict)]


def _scope_policy(config: dict[str, Any]) -> dict[str, Any]:
    structural = config.get("structural_scan")
    if not isinstance(structural, dict):
        return {}
    structural = cast(dict[str, Any], structural)
    ignored_paths = cast(list[object], structural.get("include_ignored_paths", []))
    return {
        "include_ignored_paths": sorted(item for item in ignored_paths if isinstance(item, str)),
        "max_text_files": structural.get("max_text_files"),
    }


def _file_sha256(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    except OSError:
        return None


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value)


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    raw = cast(dict[object, object], cast(object, value))
    return {
        key: item for key, item in raw.items() if isinstance(key, str) and isinstance(item, str)
    }
