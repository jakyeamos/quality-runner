from __future__ import annotations

from typing import Any, cast

from quality_runner.fleet.contracts import FLEET_FINDING_SCHEMA, digest


def apply_dynamic_quality_evidence(result: dict[str, Any]) -> None:
    dynamic_value = result.get("dynamic")
    if not isinstance(dynamic_value, dict):
        return
    dynamic = cast(dict[str, Any], dynamic_value)
    status = str(dynamic.get("status", "unknown"))
    findings_value = result.get("findings", [])
    if not isinstance(findings_value, list):
        return
    findings = cast(list[dict[str, Any]], findings_value)
    if status not in {"passed", "reused"}:
        _append_dynamic_finding(result, findings, dynamic, status)
        return
    for finding_value in cast(list[object], findings_value):
        if not isinstance(finding_value, dict):
            continue
        finding = cast(dict[str, Any], finding_value)
        if finding.get("dimension") == "quality_commands":
            finding["score"] = 4
            finding["status"] = "validated"
            finding["message"] = (
                "Discovered local quality commands passed in a protected disposable worktree."
            )
            cast(list[dict[str, Any]], finding["evidence"]).append(
                {"path": "dynamic disposable worktree", "detail": "all selected commands passed"}
            )
            break


def _append_dynamic_finding(
    result: dict[str, Any],
    findings: list[dict[str, Any]],
    dynamic: dict[str, Any],
    status: str,
) -> None:
    if status in {"not_selected", "not_applicable"}:
        return
    finding_status = "blocked" if status in {"blocked", "failed", "timeout"} else "unknown"
    reason = str(dynamic.get("reason", "dynamic verification did not produce passing evidence"))
    target_state_value = dynamic.get("target_state")
    evidence: list[dict[str, Any]] = [
        {
            "path": "dynamic disposable worktree",
            "detail": reason,
            "dynamic_status": status,
        }
    ]
    if isinstance(target_state_value, dict):
        target_state = cast(dict[str, Any], target_state_value)
        evidence.append(
            {
                "path": "target branch provenance",
                "detail": str(target_state.get("reason", reason)),
                **{
                    key: target_state.get(key)
                    for key in (
                        "local_head",
                        "upstream",
                        "upstream_head",
                        "ahead",
                        "behind",
                        "safe_action",
                    )
                },
            }
        )
    payload = {
        "schema": FLEET_FINDING_SCHEMA,
        "repo_id": result.get("repo_id"),
        "audit_id": result.get("audit_id"),
        "as_of": result.get("as_of"),
        "dimension": "dynamic_verification",
        "status": finding_status,
        "score": 0,
        "applicable": True,
        "severity": "high" if finding_status == "blocked" else "observation",
        "priority": "P0" if finding_status == "blocked" else "P1",
        "confidence": "high" if finding_status == "blocked" else "medium",
        "message": f"Dynamic quality verification is {status}: {reason}",
        "evidence": evidence,
        "validation_commands": ["qr fleet audit run --all --dynamic --json"],
    }
    payload["finding_id"] = digest(
        [payload["repo_id"], payload["audit_id"], payload["dimension"], status, reason]
    )[:16]
    payload["provenance_hash"] = digest(payload)
    findings.append(payload)
