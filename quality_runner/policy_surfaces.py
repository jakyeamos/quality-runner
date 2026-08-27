"""Classification and validation for repository policy artifacts.

Policy files are part of the Quality Runner scan surface, but source-line
coverage is not an appropriate evidence type for them.  This module keeps the
two concerns explicit: policy artifacts remain inventoried and must pass their
own validator, while the generic Python changed-line coverage gate can record
them as ``validated_by_policy_gate``.
"""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner.config import load_repo_config
from quality_runner.fleet.change_matrix import assess_matrix_path

POLICY_SURFACE_SCHEMA = "policy-surface-validation/v1"
POLICY_FILE_VALIDATORS = {
    ".pre-cr.json": "pre-cr-config",
    ".quality-runner.toml": "quality-runner-config",
    ".gitleaks.toml": "gitleaks-config",
    "change-surface-matrix.json": "change-surface-matrix",
    ".agents/change-surface-matrix.json": "change-surface-matrix",
    ".context/change-surface-matrix.json": "change-surface-matrix",
    "docs/change-surface-matrix.json": "change-surface-matrix",
}


def classify_policy_surface(relative_path: str) -> dict[str, str] | None:
    """Return the scan classification for a known policy artifact."""
    normalized = relative_path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    validator = POLICY_FILE_VALIDATORS.get(normalized)
    if validator is None:
        return None
    return {
        "path": normalized,
        "surface_kind": "policy_config",
        "validator": validator,
        "source_line_coverage": "not_applicable",
        "coverage_disposition": "validated_by_policy_gate",
    }


def validate_policy_surfaces(
    repo_root: Path,
    *,
    paths: list[str] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Validate policy artifacts and return a machine-readable evidence report.

    When ``paths`` is omitted, every known policy artifact present in the
    repository is inventoried.  Callers may pass changed paths to keep the
    check task-scoped while still retaining the explicit surface classification.
    """
    root = repo_root.expanduser().resolve()
    selected = _candidate_paths(root, paths)
    observed_at = as_of or datetime.now(UTC).replace(microsecond=0).isoformat()
    surfaces: list[dict[str, Any]] = []
    for relative in selected:
        classification = classify_policy_surface(relative)
        if classification is None:
            continue
        path = root / relative
        surfaces.append(_validate_one(root, path, classification, observed_at))
    failures = [item for item in surfaces if item["status"] != "passed"]
    return {
        "schema": POLICY_SURFACE_SCHEMA,
        "repository": str(root),
        "as_of": observed_at,
        "scan_inventory": {
            "policy_files_considered": len(surfaces),
            "policy_files_validated": len(surfaces) - len(failures),
            "source_line_coverage_excluded": [item["path"] for item in surfaces],
        },
        "surfaces": surfaces,
        "status": "failed" if failures else "passed",
        "errors": [error for item in failures for error in item["errors"]],
    }


def _candidate_paths(root: Path, paths: list[str] | None) -> list[str]:
    if paths is not None:
        changed = {
            classification["path"]
            for path in paths
            if (classification := classify_policy_surface(path)) is not None
        }
        present = {
            relative
            for relative in POLICY_FILE_VALIDATORS
            if (root / relative).is_file() and not (root / relative).is_symlink()
        }
        return sorted(present | changed)
    return sorted(
        relative
        for relative in POLICY_FILE_VALIDATORS
        if (root / relative).is_file() and not (root / relative).is_symlink()
    )


def _validate_one(
    root: Path,
    path: Path,
    classification: dict[str, str],
    as_of: str,
) -> dict[str, Any]:
    errors: list[str] = []
    validator = classification["validator"]
    if path.is_symlink():
        errors.append("policy artifact is a symlink and was not followed")
    elif not path.is_file():
        errors.append("policy artifact is missing")
    else:
        try:
            if validator == "pre-cr-config":
                _validate_pre_cr(path)
            elif validator == "quality-runner-config":
                _validate_quality_runner_config(root)
            elif validator == "gitleaks-config":
                _validate_toml(path, ".gitleaks.toml")
            elif validator == "change-surface-matrix":
                result = assess_matrix_path(path, root=root, as_of=as_of[:10])
                if result.get("status") not in {"validated", "maintained"}:
                    errors.append(str(result.get("message", "matrix validation failed")))
        except (OSError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
            errors.append(str(error))
    return {
        **classification,
        "status": "failed" if errors else "passed",
        "validator_evidence": f"qr policy-surface-check {classification['path']}",
        "errors": errors,
    }


def _validate_pre_cr(path: Path) -> None:
    payload = _load_json(path)
    required = ("version", "testCommand", "coveragePaths", "threshold")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f".pre-cr.json missing required fields: {', '.join(missing)}")
    if not isinstance(payload["coveragePaths"], list) or not payload["coveragePaths"]:
        raise ValueError(".pre-cr.json coveragePaths must be a non-empty list")
    if not isinstance(payload["threshold"], (int, float)):
        raise ValueError(".pre-cr.json threshold must be numeric")


def _validate_quality_runner_config(root: Path) -> None:
    config = load_repo_config(root)
    warnings = config.get("warnings", [])
    if warnings:
        warning_values = cast(list[object], warnings) if isinstance(warnings, list) else []
        messages: list[str] = []
        for item in warning_values:
            if isinstance(item, dict):
                messages.append(str(cast(dict[str, Any], item).get("message", item)))
        raise ValueError(".quality-runner.toml warnings: " + "; ".join(messages))


def _validate_toml(path: Path, label: str) -> None:
    try:
        tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{label} is invalid TOML: {error}") from error


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, Any], payload)
