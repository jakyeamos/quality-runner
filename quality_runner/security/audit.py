from __future__ import annotations

from typing import Any, cast

SEVERITY_RANK = {"critical": 0, "high": 1, "blocker": 2, "warning": 3, "observation": 4}


def security_audit_findings(
    security_scan: dict[str, Any] | None,
    security_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(security_scan, dict):
        return []
    settings = _dict(security_scan.get("settings")) or {}
    if settings.get("enabled") is False:
        return []

    findings: list[dict[str, Any]] = []
    findings.extend(_candidate_findings(security_scan))
    findings.extend(_missing_capability_findings(security_scan))
    findings.extend(_agent_review_findings(security_scan))
    return findings


def _candidate_findings(security_scan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = security_scan.get("candidates")
    if not isinstance(candidates, list):
        return []

    findings: list[dict[str, Any]] = []
    for candidate in _dict_list(cast(object, candidates)):
        candidate_id = candidate.get("id")
        category = candidate.get("category")
        if not isinstance(candidate_id, str) or not isinstance(category, str):
            continue
        severity_hint = str(candidate.get("severity_hint") or "medium")
        findings.append(
            {
                "id": f"security-candidate-{candidate_id.lower()}",
                "detector": "security",
                "rule_id": category,
                "fingerprint": candidate.get("fingerprint"),
                "file": candidate.get("file"),
                "line": candidate.get("line"),
                "confidence": candidate.get("confidence"),
                "coverage_ref": "security",
                "severity": _audit_severity(severity_hint),
                "category": f"security:{category}",
                "summary": (
                    f"Security candidate ({category}) in {candidate.get('file')}: "
                    f"{candidate.get('summary') or 'review required'}."
                ),
                "evidence": [
                    f"{candidate.get('file')}:{candidate.get('line')}: {candidate.get('evidence')}",
                    f"Confidence: {candidate.get('confidence')}.",
                ],
                "recommended_fix": str(
                    candidate.get("recommended_review")
                    or "Review the candidate and disposition in the resolution ledger."
                ),
                "verification": [
                    str(
                        candidate.get("verification_guidance")
                        or "Confirm or reject the candidate with evidence."
                    ),
                    "Update resolution ledger disposition after review.",
                ],
                "owner": None,
                "score": _severity_score(severity_hint),
                "disposition_class": candidate.get("disposition_class"),
                "disposition_group": candidate.get("disposition_group"),
                "disposition_required": candidate.get("disposition_required", False),
                "owner_role": candidate.get("owner_role", "security-maintainer"),
                "disposition_rationale": candidate.get("disposition_rationale"),
            }
        )
    return findings


def _missing_capability_findings(security_scan: dict[str, Any]) -> list[dict[str, Any]]:
    missing = security_scan.get("missing_capabilities")
    if not isinstance(missing, list):
        return []

    findings: list[dict[str, Any]] = []
    for capability in _dict_list(cast(object, missing)):
        capability_id = capability.get("id")
        if not isinstance(capability_id, str):
            continue
        if capability.get("capability_kind") == "agent_review":
            continue
        finding_id = f"missing-{capability_id.replace('_', '-')}"
        findings.append(
            {
                "id": finding_id,
                "severity": _missing_capability_severity(capability),
                "category": "security:capability",
                "summary": f"Missing security capability: {capability_id}.",
                "evidence": [
                    f"Capability map lists {capability_id} as missing.",
                    str(capability.get("reason") or "No matching security gate detected."),
                ],
                "recommended_fix": _recommended_fix(capability),
                "verification": [
                    f"Add {capability_id} gate and rerun quality-runner.",
                    f"Confirm {finding_id} is absent from regenerated audit.",
                ],
                "owner": None,
                "score": 900,
            }
        )
    return findings


def _agent_review_findings(security_scan: dict[str, Any]) -> list[dict[str, Any]]:
    gates = security_scan.get("agent_review_gates")
    if not isinstance(gates, list):
        return []

    findings: list[dict[str, Any]] = []
    for gate in _dict_list(cast(object, gates)):
        gate_id = gate.get("id")
        if not isinstance(gate_id, str):
            continue
        scope = _dict(gate.get("scope"))
        categories = []
        if scope is not None:
            categories = [
                item for item in _any_list(scope.get("categories")) if isinstance(item, str)
            ]
        findings.append(
            {
                "id": f"security-review-{gate_id.replace('_', '-')}",
                "severity": "observation",
                "category": "security:agent-review",
                "summary": f"Agent security review required: {gate_id}.",
                "evidence": [
                    f"QR created agent-review gate {gate_id}.",
                    f"Review categories: {', '.join(categories) if categories else 'security'}.",
                ],
                "recommended_fix": (
                    "Complete the agent-review gate instructions and disposition all related candidates."
                ),
                "verification": list(_any_list(gate.get("completion_criteria")))
                or ["Disposition all related security candidates."],
                "owner": None,
                "score": 700,
            }
        )
    return findings


def _audit_severity(severity_hint: str) -> str:
    if severity_hint in {"critical", "high"}:
        return "blocker"
    if severity_hint == "medium":
        return "warning"
    return "observation"


def _severity_score(severity_hint: str) -> int:
    return {
        "critical": 1200,
        "high": 1000,
        "medium": 600,
        "low": 200,
        "info": 50,
    }.get(severity_hint, 400)


def _recommended_fix(capability: dict[str, Any]) -> str:
    commands = capability.get("recommended_commands")
    if isinstance(commands, list) and commands:
        return f"Add a repo-owned security gate such as: {commands[0]}"
    capability_id = capability.get("id")
    return f"Provide the missing {capability_id} security capability."


def _missing_capability_severity(capability: dict[str, Any]) -> str:
    if capability.get("capability_kind") == "evidence" or capability.get("type") == "evidence":
        return "warning"
    required_by = capability.get("required_by")
    if required_by == "config":
        return "blocker"
    return "warning"


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in cast(list[Any], value) if isinstance(item, dict)]


def _any_list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []
