from __future__ import annotations

from typing import Any

from quality_runner.code_quality_findings import CATEGORY_ORDER
from quality_runner.findings import AUDIT_REPORT_SCHEMA


def build_audit_report(
    *,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    capability_map: dict[str, Any],
    code_quality_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    findings = [
        *_missing_capability_findings(capability_map, standards_packet),
        *_standards_requirement_findings(standards_packet, scan),
        *_code_quality_findings(code_quality_scan),
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


def _missing_capability_findings(
    capability_map: dict[str, Any],
    standards_packet: dict[str, Any],
) -> list[dict[str, Any]]:
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
        required_owner = capability.get("owner")
        if not isinstance(capability_id, str) or not capability_id:
            continue
        reason_text = reason if isinstance(reason, str) and reason else "capability is absent"
        type_text = (
            capability_type if isinstance(capability_type, str) and capability_type else "unknown"
        )
        language_text = language if isinstance(language, str) and language else "unknown"
        finding_id = f"missing-{capability_id.replace('_', '-')}"
        owner = required_owner if isinstance(required_owner, str) and required_owner else None
        findings.append(
            {
                "id": finding_id,
                "severity": _effective_severity(
                    capability_id=capability_id,
                    finding_id=finding_id,
                    standards_packet=standards_packet,
                ),
                "owner": owner,
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


def _code_quality_findings(code_quality_scan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(code_quality_scan, dict):
        return []
    findings = code_quality_scan.get("findings")
    if not isinstance(findings, list):
        return []

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        category = finding.get("category")
        rule_id = finding.get("rule_id")
        if isinstance(category, str) and category and isinstance(rule_id, str) and rule_id:
            groups.setdefault((category, rule_id), []).append(finding)

    audit_findings: list[dict[str, Any]] = []
    for (category, rule_id), group in sorted(groups.items(), key=_structural_group_sort_key):
        representative = group[0]
        expected = _string_or_default(representative.get("expected_improvement"), "Review finding.")
        count = len(group)
        score = _structural_score(group)
        audit_findings.append(
            {
                "id": f"structural-{category}-{rule_id}",
                "severity": _structural_severity(group),
                "category": f"structural:{category}",
                "summary": (
                    f"{count} {rule_id} structural finding{'s' if count != 1 else ''} "
                    f"in {_string_or_default(representative.get('remediation_bucket'), 'structural quality')}."
                ),
                "evidence": _structural_evidence(group),
                "recommended_fix": f"{count} findings, aggregate score {score}: {expected}",
                "verification": sorted(
                    {
                        item
                        for finding in group
                        if isinstance((item := finding.get("verification")), str) and item
                    }
                )
                or ["Rerun quality-runner and confirm the structural finding clears."],
                "owner": None,
                "score": score,
            }
        )
    return audit_findings


def _structural_group_sort_key(
    item: tuple[tuple[str, str], list[dict[str, Any]]],
) -> tuple[int, int, str]:
    (category, rule_id), group = item
    category_rank = (
        CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)
    )
    return -_structural_score(group), category_rank, rule_id


def _structural_score(group: list[dict[str, Any]]) -> int:
    score = 0
    for item in group:
        value = item.get("score")
        if isinstance(value, int):
            score += value
    return score


def _structural_severity(group: list[dict[str, Any]]) -> str:
    return "warning" if any(item.get("severity") == "warning" for item in group) else "observation"


def _structural_evidence(group: list[dict[str, Any]]) -> list[str]:
    evidence = []
    for finding in group[:5]:
        file = _string_or_default(finding.get("file"), "unknown")
        line = finding.get("line")
        line_text = str(line) if isinstance(line, int) else "?"
        rule = _string_or_default(finding.get("rule_id"), "structural")
        evidence.append(f"{file}:{line_text}: {rule}")
    if len(group) > 5:
        evidence.append(f"{len(group) - 5} additional findings omitted from summary.")
    return evidence


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


def _effective_severity(
    *,
    capability_id: str,
    finding_id: str,
    standards_packet: dict[str, Any],
) -> str:
    config = standards_packet.get("config")
    if isinstance(config, dict):
        overrides = config.get("severity_overrides")
        if isinstance(overrides, dict):
            for key in (finding_id, capability_id):
                value = overrides.get(key)
                if isinstance(value, str) and value:
                    return value
    return _severity_for_capability(capability_id)


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
