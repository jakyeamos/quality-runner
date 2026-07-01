from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.config import load_repo_config
from quality_runner.schema_constants import STANDARDS_PACKET_SCHEMA

SUPPORTED_PROFILES = {"jakyeamos"}


# fmt: off
def compile_standards(repo_root: Path, scan: dict[str, Any], profile: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
# fmt: on
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"unsupported standards profile: {profile}")

    resolved_config = load_repo_config(repo_root) if config is None else config
    warnings = [*_warnings(scan), *_warnings(resolved_config)]
    package_manager = _package_manager(scan, warnings)

    allowed_package_managers = _allowed_package_managers(resolved_config)

    return {
        "schema": STANDARDS_PACKET_SCHEMA,
        "profile": profile,
        "repo_root": str(repo_root.expanduser().resolve()),
        "sources": _sources(scan, profile, resolved_config),
        "config": resolved_config,
        "requirements": _requirements(package_manager, allowed_package_managers),
        "warnings": warnings,
    }


def _sources(scan: dict[str, Any], profile: str, config: dict[str, Any]) -> list[dict[str, str]]:
    sources = [{"type": "profile", "path": f"profile:{profile}"}]

    config_path = config.get("path")
    if isinstance(config_path, str) and config_path:
        sources.append({"type": "config", "path": config_path})

    instruction_files = scan.get("agent_instruction_files")
    if isinstance(instruction_files, list):
        for path in instruction_files:
            if isinstance(path, str) and path:
                sources.append({"type": "agent_instructions", "path": path})

    truth_file = scan.get("truth_file")
    if isinstance(truth_file, str) and truth_file:
        sources.append({"type": "truth_file", "path": truth_file})

    return sources


def _requirements(
    package_manager: str | None,
    allowed_package_managers: set[str],
) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = [
        {
            "id": "use_pnpm",
            "level": "hard",
            "description": "Use pnpm for JavaScript dependency management and scripts.",
        },
        {
            "id": "quality_ladder",
            "level": "hard",
            "description": "Run lint, type checking, tests, and dead-code checks before completion.",
        },
        {
            "id": "truth_file_current",
            "level": "hard",
            "description": "Maintain .tracker/PROJECT_TRUTH.md when the repo has a truth file.",
        },
        {
            "id": "audit_and_plan_only",
            "level": "hard",
            "description": "Report quality findings and remediation plans without applying changes.",
        },
    ]

    if package_manager not in {*allowed_package_managers, None}:
        requirements.append(
            {
                "id": "package_manager_mismatch",
                "level": "warning",
                "description": "Detected package manager does not match the jakyeamos pnpm standard.",
            }
        )

    return requirements


def _allowed_package_managers(config: dict[str, Any]) -> set[str]:
    configured = config.get("allowed_package_managers")
    if isinstance(configured, list) and configured:
        return {item for item in configured if isinstance(item, str) and item}
    return {"pnpm"}


def _warnings(scan: dict[str, Any]) -> list[dict[str, str]]:
    warnings = scan.get("warnings")
    if not isinstance(warnings, list):
        return []

    normalized: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        path = warning.get("path")
        if isinstance(code, str) and isinstance(message, str) and isinstance(path, str):
            normalized.append({"code": code, "message": message, "path": path})
    return normalized


def _package_manager(scan: dict[str, Any], warnings: list[dict[str, str]]) -> str | None:
    package_manager = scan.get("package_manager")
    if package_manager is None:
        return None
    if isinstance(package_manager, str):
        return package_manager

    warnings.append(
        {
            "code": "invalid_package_manager",
            "message": "scan package_manager must be a string or null",
            "path": "package_manager",
        }
    )
    return "unknown"
