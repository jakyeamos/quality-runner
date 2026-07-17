from __future__ import annotations

from typing import Any


def passed_gate(gate_id: str, reason: str) -> dict[str, Any]:
    return {"id": gate_id, "status": "passed", "capability_kind": "evidence", "reason": reason}


def blocked_gate(gate_id: str, reason: str, blocker_class: str) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    if blocker_class in {"evidence", "review-required"}:
        diagnostics = {
            "classification": "not-enough-evidence",
            "human_confirmation_required": blocker_class == "review-required",
            "actionability": "needs-author-decision"
            if blocker_class == "review-required"
            else "needs-maintainer-policy",
        }
    actions = {
        "evidence_provenance": "Provide current-HEAD, ref, workflow, and capture-time CI provenance.",
        "release_manifest_coherence": "Align package metadata, reported release version, source HEAD, artifact version, and digest.",
        "package_consumer_smoke": "Build or obtain the local artifact, install it in an isolated consumer, and run the declared smoke command.",
        "migration_safety": "Provide forward, rollback, failure-injection, and reconciliation evidence or a passing migration safety command.",
        "release_acceptance_evidence": "Record owner acceptance and any required external staging or cutover evidence in release-evidence.json.",
        "publication_visibility_review": "Complete authorization, sanitization, publication-versioning, and public/private media-access review evidence.",
        "aggregate_coverage": "Expand aggregate commands and prove coverage for every required leaf gate.",
        "read_only_integrity": "Rerun mutating or unknown-risk gates in a disposable worktree and inspect mutation diagnostics.",
    }
    return {
        "id": gate_id,
        "status": "blocked",
        "capability_kind": "evidence",
        "reason": reason,
        "blocker_class": blocker_class,
        "recommended_action": actions.get(
            gate_id, f"Resolve the {gate_id} readiness requirement and rerun the release profile."
        ),
        **({"diagnostics": diagnostics} if diagnostics else {}),
    }


def dedupe_gates(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for gate in gates:
        gate_id = gate.get("id")
        if isinstance(gate_id, str) and gate_id not in seen:
            seen.add(gate_id)
            result.append(gate)
    return result
