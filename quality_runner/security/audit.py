from __future__ import annotations

from typing import Any

SEVERITY_RANK = {"critical": 0, "high": 1, "blocker": 2, "warning": 3, "observation": 4}


def security_audit_findings(
    security_scan: dict[str, Any] | None,
    security_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(security_scan, dict):
        return []
    if security_scan.get("settings", {}).get("enabled") is False:
        return []

    findings: list[dict[str, Any]] = []
    findings.extend(_candidate_findings(security_scan))
    if _explicit_security_requirements(security_config):
        findings.extend(_missing_capability_findings(security_scan))
    findings.extend(_agent_review_findings(security_scan))
    return findings


def _explicit_security_requirements(security_config: dict[str, Any] | None) -> bool:
    if not isinstance(security_config, dict):
        return False
    required = security_config.get("required_capabilities")
    return isinstance(required, list) and bool(required)


def _candidate_findings(security_scan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = security_scan.get("candidates")
    if not isinstance(candidates, list):
        return []

    findings: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = candidate.get("id")
        category = candidate.get("category")
        if not isinstance(candidate_id, str) or not isinstance(category, str):
            continue
        severity_hint = str(candidate.get("severity_hint") or "medium")
        findings.append(
            {
                "id": f"security-candidate-{candidate_id.lower()}",
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
    for capability in missing:
        if not isinstance(capability, dict):
            continue
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
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gate_id = gate.get("id")
        if not isinstance(gate_id, str):
            continue
        scope = gate.get("scope")
        categories = []
        if isinstance(scope, dict) and isinstance(scope.get("categories"), list):
            categories = [item for item in scope["categories"] if isinstance(item, str)]
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
                "verification": list(gate.get("completion_criteria") or [])
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
