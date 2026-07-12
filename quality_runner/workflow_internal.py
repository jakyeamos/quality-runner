from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quality_runner.capabilities import detect_capabilities
from quality_runner.ci_status import load_ci_status
from quality_runner.config import load_repo_config
from quality_runner.discovery import inspect_repo
from quality_runner.standards import DEFAULT_PROFILE, compile_standards


def generated_run_id(now: datetime | None = None, suffix: str | None = None) -> str:
    timestamp = datetime.now(UTC) if now is None else now.astimezone(UTC)
    run_suffix = uuid4().hex[:8] if suffix is None else suffix
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{run_suffix}"


def inspect_repo_bundle(
    repo_root: Path,
    run_id: str,
    profile: str | None,
    ci_status_json: Path | None,
    branch_warnings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    ci_checks, ci_warnings = load_ci_status(repo_root, ci_status_json)
    config = load_repo_config(repo_root)
    scan = inspect_repo(
        repo_root,
        run_id=run_id,
        ci_checks=ci_checks,
        extra_warnings=[*branch_warnings, *ci_warnings],
        config=config,
    )
    resolved_profile = profile or string_or_default(config.get("default_profile"), DEFAULT_PROFILE)
    standards_packet = compile_standards(
        repo_root=repo_root, scan=scan, profile=resolved_profile, config=config
    )
    capability_map = detect_capabilities(scan=scan, standards_packet=standards_packet)
    return scan, standards_packet, capability_map, config


def string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def verify_payload_status(
    gate_verification: dict[str, Any],
    remediation_plan: dict[str, Any],
) -> str:
    gate_status = gate_verification.get("status")
    if gate_status == "passed" and remediation_plan.get("slices"):
        return "passed-with-findings"
    return gate_status if isinstance(gate_status, str) else "blocked"
