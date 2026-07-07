from __future__ import annotations

from typing import Any

ACTIONABILITY_VALUES = {
    "mechanical-fix",
    "needs-author-decision",
    "needs-maintainer-policy",
    "dependency-setup",
    "environment-blocker",
    "read-only-policy",
    "informational",
    "accepted-disposition",
    "needs-triage",
}


def enrich_audit_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        actionability, rationale = actionability_for_finding(finding)
        enriched.append(
            {
                **finding,
                "actionability": actionability,
                "actionability_rationale": rationale,
            }
        )
    return enriched


def actionability_for_finding(finding: dict[str, Any]) -> tuple[str, str]:
    category = str(finding.get("category") or "")
    severity = str(finding.get("severity") or "")
    summary = str(finding.get("summary") or "")

    if category == "capability":
        return (
            "needs-maintainer-policy",
            "Missing repo-owned quality gates require maintainer policy or adoption work.",
        )
    if category == "input-warning":
        return (
            "informational",
            "Input warning affects evidence quality but not source code directly.",
        )
    if category == "standard":
        return (
            "needs-maintainer-policy",
            "Standards-profile mismatch is a repository policy decision.",
        )
    if category.startswith("security:agent-review"):
        return (
            "needs-author-decision",
            "Agent-reviewed security findings require explicit author or security-owner judgment.",
        )
    if category.startswith("security:"):
        if severity in {"critical", "blocker"}:
            return (
                "needs-author-decision",
                "High-severity security findings need explicit remediation approval.",
            )
        return ("mechanical-fix", "Deterministic security finding with a concrete recommended fix.")
    if category.startswith("skill:"):
        return (
            "needs-maintainer-policy",
            "Quality-skill findings reflect team-specific standards that need maintainer review.",
        )
    if category.startswith("architecture:"):
        return (
            "needs-maintainer-policy",
            "Architecture-contract violations require maintainer boundary decisions.",
        )
    if category == "integrate" or category.startswith("structural:integrate"):
        return (
            "needs-author-decision",
            "Unwired or partial work requires an explicit wire, finish, descope, or WIP decision.",
        )
    if category.startswith("structural:"):
        if severity == "observation":
            return ("informational", "Structural observation is advisory and non-blocking.")
        if severity == "warning":
            return (
                "mechanical-fix",
                "Structural warning is usually addressable with a focused refactor.",
            )
        return (
            "needs-author-decision",
            "High-signal structural debt may require scoped redesign or accepted disposition.",
        )
    if "dependency" in summary.lower() or "install" in summary.lower():
        return (
            "dependency-setup",
            "Finding points at dependency or environment setup before code edits.",
        )
    if "read-only" in summary.lower():
        return ("read-only-policy", "Finding is blocked by read-only gate policy or mutation risk.")
    if "environment" in summary.lower() or "sandbox" in summary.lower():
        return ("environment-blocker", "Finding is blocked by local environment restrictions.")
    return (
        "needs-triage",
        "Finding needs controller triage when category-specific routing is unavailable.",
    )
