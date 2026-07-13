from __future__ import annotations

import re
from typing import Any

from quality_runner.security.redaction import REDACTED_LITERAL

SECRET_PATTERNS = (
    re.compile(
        rf"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]"
        rf"(?!{re.escape(REDACTED_LITERAL)}['\"])[^'\"]{{8,}}"
    ),
    re.compile(r"(?i)-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
)


def validate_handoff_quality(
    handoff: dict[str, Any],
    *,
    remediation_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if handoff.get("implementation_allowed") is not False:
        errors.append("handoff must keep implementation_allowed=false")

    plan = remediation_plan
    if plan is None:
        artifact_paths = handoff.get("artifact_paths")
        if isinstance(artifact_paths, dict):
            plan_path = artifact_paths.get("remediation_plan_json")
            if isinstance(plan_path, str):
                plan = _load_json(plan_path)
    slices = plan.get("slices") if isinstance(plan, dict) else None
    if isinstance(slices, list):
        for slice_item in slices:
            if not isinstance(slice_item, dict):
                continue
            slice_id = str(slice_item.get("id") or "unknown")
            verification = slice_item.get("verification_gates")
            if not _has_machine_checkable_verification(verification):
                errors.append(f"slice {slice_id} lacks machine-checkable verification")
            if not _non_empty_string_list(slice_item.get("stop_conditions")):
                errors.append(f"slice {slice_id} lacks STOP conditions")
            if slice_item.get("planned_at") is None:
                errors.append(f"slice {slice_id} lacks planned_at git state")
            if _is_structural_slice(slice_item) and not _has_structural_anchor(slice_item):
                errors.append(f"slice {slice_id} lacks file/line/fingerprint anchor")

    next_slice = handoff.get("next_slice")
    if isinstance(next_slice, dict):
        errors.extend(_lint_slice_dict(next_slice, label="next_slice"))

    return {"passed": not errors, "errors": errors}


def validate_slice_spec_content(content: str) -> dict[str, Any]:
    errors: list[str] = []
    required_sections = (
        "## Why this matters",
        "## Current state",
        "## In scope",
        "## Out of scope",
        "## Ordered steps",
        "## STOP conditions",
        "## Done criteria",
    )
    for section in required_sections:
        if section not in content:
            errors.append(f"missing section: {section}")
    if "## Per-step verification" not in content and "## Verification" not in content:
        errors.append("missing per-step verification section")
    if _contains_secret_literal(content):
        errors.append("slice spec appears to contain secret-looking literals")
    return {"passed": not errors, "errors": errors}


def lint_slice_item(slice_item: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": not _lint_slice_dict(slice_item, label=str(slice_item.get("id") or "slice")),
        "errors": _lint_slice_dict(slice_item, label=str(slice_item.get("id") or "slice")),
    }


def _lint_slice_dict(slice_item: dict[str, Any], *, label: str) -> list[str]:
    errors: list[str] = []
    if not _has_machine_checkable_verification(slice_item.get("verification_gates")):
        errors.append(f"{label} lacks machine-checkable verification")
    if not _non_empty_string_list(slice_item.get("stop_conditions")):
        errors.append(f"{label} lacks STOP conditions")
    if slice_item.get("planned_at") is None:
        errors.append(f"{label} lacks planned_at git state")
    if _is_structural_slice(slice_item) and not _has_structural_anchor(slice_item):
        errors.append(f"{label} lacks structural anchor")
    scope = slice_item.get("scope")
    if not isinstance(scope, dict) or not _non_empty_string_list(scope.get("in_scope")):
        errors.append(f"{label} lacks in-scope boundaries")
    return errors


def _has_machine_checkable_verification(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, str) or not item:
            continue
        lowered = item.lower()
        if any(
            token in lowered
            for token in ("rerun quality-runner", "pytest", "ruff", "pnpm", "git diff")
        ):
            return True
        if "`" in item or " run " in f" {lowered} ":
            return True
    return False


def _is_structural_slice(slice_item: dict[str, Any]) -> bool:
    findings = slice_item.get("findings")
    if not isinstance(findings, list):
        return str(slice_item.get("id") or "").startswith("remediate-structural-")
    return any(
        isinstance(finding, dict) and str(finding.get("category", "")).startswith("structural:")
        for finding in findings
    )


def _has_structural_anchor(slice_item: dict[str, Any]) -> bool:
    findings = slice_item.get("findings")
    if not isinstance(findings, list):
        return False
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if isinstance(finding.get("fingerprint"), str) and finding["fingerprint"]:
            return True
        if isinstance(finding.get("file"), str) and isinstance(finding.get("line"), int):
            return True
        excerpt = finding.get("evidence_excerpt")
        if isinstance(excerpt, dict) and isinstance(excerpt.get("file"), str):
            return True
    return False


def _contains_secret_literal(content: str) -> bool:
    return any(pattern.search(content) for pattern in SECRET_PATTERNS)


def _non_empty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
    )


def _load_json(path: str) -> dict[str, Any] | None:
    import json
    from pathlib import Path

    target = Path(path)
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None
