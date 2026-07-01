from __future__ import annotations

from typing import Any

from quality_runner.findings import AUDIT_REPORT_SCHEMA


def build_audit_report(
    *,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    capability_map: dict[str, Any],
) -> dict[str, Any]:
    findings = [
        *_missing_capability_findings(capability_map),
        *_standards_requirement_findings(standards_packet, scan),
        *_warning_findings(capability_map),
    ]

    return {
        "schema": AUDIT_REPORT_SCHEMA,
        "run_id": _string_or_none(scan.get("run_id")),
        "repo_root": _string_or_none(scan.get("repo_root")),
        "profile": _string_or_none(standards_packet.get("profile")),
        "status": "findings" if findings else "clean",
        "implementation_allowed": False,
        "findings": findings,
        "warnings": _warnings(capability_map),
    }


def render_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Quality Runner Audit Report",
        "",
        f"- Schema: {report.get('schema')}",
        f"- Status: {report.get('status')}",
        f"- Implementation allowed: {str(report.get('implementation_allowed')).lower()}",
        "",
        "## Findings",
        "",
    ]

    findings = report.get("findings")
    if isinstance(findings, list) and findings:
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            lines.extend(
                [
                    f"### {finding.get('id')}",
                    "",
                    f"- Severity: {finding.get('severity')}",
                    f"- Category: {finding.get('category')}",
                    f"- Summary: {finding.get('summary')}",
                    f"- Recommended fix: {finding.get('recommended_fix')}",
                    "- Evidence:",
                    *_markdown_items(finding.get("evidence")),
                    "- Verification:",
                    *_markdown_items(finding.get("verification")),
                    "",
                ]
            )
    else:
        lines.extend(["No findings.", ""])

    return "\n".join(lines).rstrip() + "\n"


def _missing_capability_findings(capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    missing = capability_map.get("missing")
    if not isinstance(missing, list):
        return []

    findings: list[dict[str, Any]] = []
    for capability in missing:
        if not isinstance(capability, dict):
            continue
        capability_id = capability.get("id")
        reason = capability.get("reason")
        capability_type = capability.get("type")
        language = capability.get("language")
        if not isinstance(capability_id, str) or not capability_id:
            continue
        reason_text = reason if isinstance(reason, str) and reason else "capability is absent"
        type_text = (
            capability_type if isinstance(capability_type, str) and capability_type else "unknown"
        )
        language_text = language if isinstance(language, str) and language else "unknown"
        finding_id = f"missing-{capability_id.replace('_', '-')}"
        findings.append(
            {
                "id": finding_id,
                "severity": _severity_for_capability(capability_id),
                "category": "capability",
                "summary": f"Required quality capability is missing: {capability_id}.",
                "evidence": [
                    f"Capability map lists {capability_id} as missing.",
                    f"Missing {type_text} capability evidence: {reason_text}.",
                ],
                "recommended_fix": _recommended_fix(capability_id, language_text),
                "verification": [
                    f"Add the {capability_id} capability and rerun quality-runner.",
                    f"Confirm audit finding {finding_id} is absent from the regenerated report.",
                ],
            }
        )
    return findings


def _warning_findings(capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for warning in _warnings(capability_map):
        code = warning["code"]
        finding_id = f"warning-{code.replace('_', '-')}"
        findings.append(
            {
                "id": finding_id,
                "severity": "warning",
                "category": "input-warning",
                "summary": warning["message"],
                "evidence": [f"{warning['path']}: {warning['message']}"],
                "recommended_fix": f"Resolve input warning {code} before relying on audit results.",
                "verification": [
                    "Rerun quality-runner after resolving the warning.",
                    f"Confirm warning {code} is absent from the regenerated artifacts.",
                ],
            }
        )
    return findings


def _standards_requirement_findings(
    standards_packet: dict[str, Any],
    scan: dict[str, Any],
) -> list[dict[str, Any]]:
    requirements = standards_packet.get("requirements")
    if not isinstance(requirements, list):
        return []

    findings: list[dict[str, Any]] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        requirement_id = requirement.get("id")
        if requirement_id == "package_manager_mismatch":
            detected = _string_or_default(scan.get("package_manager"), "unknown")
            findings.append(
                {
                    "id": "standard-package-manager-mismatch",
                    "severity": "warning",
                    "category": "standard",
                    "summary": "Detected package manager does not match the pnpm standard.",
                    "evidence": [
                        "Expected package manager: pnpm.",
                        f"Detected package manager: {detected}.",
                        "Package manager source: package.json packageManager or lockfile discovery.",
                    ],
                    "recommended_fix": (
                        "Align JavaScript dependency management to the pnpm standard."
                    ),
                    "verification": [
                        "Update package metadata and lockfiles to use pnpm.",
                        "Rerun quality-runner and confirm standard-package-manager-mismatch is absent.",
                    ],
                }
            )
    return findings


def _warnings(payload: dict[str, Any]) -> list[dict[str, str]]:
    warnings = payload.get("warnings")
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


def _severity_for_capability(capability_id: str) -> str:
    if capability_id in {"formatter", "lint", "typecheck", "tests", "dead_code", "truth_file"}:
        return "blocker"
    return "warning"


def _recommended_fix(capability_id: str, language: str) -> str:
    python_fixes = {
        "formatter": "Add a Python format gate such as ruff format --check .",
        "lint": "Add a Python lint gate such as ruff check .",
        "typecheck": "Add a Python typecheck gate such as basedpyright.",
        "tests": "Add a Python test gate such as pytest -q.",
        "build": "Add a Python build gate such as uv build.",
        "dead_code": "Add a Python dead-code gate such as vulture . --min-confidence 70.",
        "runtime_smoke": "Add a Python smoke gate that exercises installed console scripts.",
        "pre_pr": "Add a pull_request CI quality gate or document the equivalent pre-PR check.",
        "pre_cr": "Add a Pre-CR changed-line readiness configuration.",
    }
    javascript_fixes = {
        "formatter": "Add a formatter command such as pnpm format.",
        "lint": "Add a lint command such as pnpm lint.",
        "typecheck": "Add a typecheck command such as pnpm typecheck.",
        "tests": "Add a test command such as pnpm test.",
        "build": "Add a build command such as pnpm build.",
        "dead_code": "Add a dead-code scan command such as pnpm audit:dead-code.",
        "runtime_smoke": "Add a smoke-test command for runtime verification.",
        "pre_pr": "Add a pre-PR check command or document the equivalent release gate.",
        "pre_cr": "Add a Pre-CR script or configuration.",
        "truth_file": "Create and maintain .tracker/PROJECT_TRUTH.md.",
    }
    fixes = python_fixes if language == "python" else javascript_fixes
    return fixes.get(capability_id, f"Provide the missing {capability_id} capability.")


def _markdown_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["  - unavailable"]
    items = [item for item in value if isinstance(item, str) and item]
    if not items:
        return ["  - unavailable"]
    return [f"  - {item}" for item in items]


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default
