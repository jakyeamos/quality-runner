from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUN_SUMMARY_SCHEMA = "quality-runner-run-summary-v0.1"


def build_run_summary(
    *,
    repo_root: Path,
    run_id: str,
    baseline_run_id: str | None = None,
) -> dict[str, Any]:
    summary = _run_summary(repo_root=repo_root, run_id=run_id)
    payload = {
        "schema": RUN_SUMMARY_SCHEMA,
        **summary,
        "delta": None,
    }
    if baseline_run_id is not None:
        baseline = _run_summary(repo_root=repo_root, run_id=baseline_run_id)
        payload["delta"] = _summary_delta(baseline=baseline, final=summary)
    return payload


def _run_summary(*, repo_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"run does not exist: {run_id}")
    audit = _load_optional_json(run_dir / "quality-audit.json")
    capability_map = _load_optional_json(run_dir / "capability-matrix.json")
    gate_verification = _load_optional_json(run_dir / "gate-verification.json")
    gate_results = _gate_results(gate_verification)
    missing_capabilities = _missing_capabilities(capability_map)
    finding_counts = _finding_counts(audit)
    status = _summary_status(gate_verification, audit)
    return {
        "run_id": run_id,
        "path": str(run_dir),
        "status": status,
        "recommended_classification": _recommended_classification(
            status=status,
            gate_results=gate_results,
            missing_capabilities=missing_capabilities,
            finding_counts=finding_counts,
        ),
        "gate_results": gate_results,
        "missing_capabilities": missing_capabilities,
        "finding_counts": finding_counts,
        "audit_status": _string_or_none(audit.get("status")),
        "gate_verification_status": _string_or_none(gate_verification.get("status")),
    }


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _gate_results(gate_verification: dict[str, Any]) -> list[dict[str, Any]]:
    gates = gate_verification.get("gates")
    if not isinstance(gates, list):
        return []
    results: list[dict[str, Any]] = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        result = {
            "id": gate.get("id"),
            "status": gate.get("status"),
            "failure_type": gate.get("failure_type"),
            "duration_seconds": gate.get("duration_seconds"),
        }
        results.append({key: value for key, value in result.items() if value is not None})
    return results


def _missing_capabilities(capability_map: dict[str, Any]) -> list[str]:
    missing = capability_map.get("missing")
    if not isinstance(missing, list):
        return []
    return [
        item["id"]
        for item in missing
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _finding_counts(audit: dict[str, Any]) -> dict[str, Any]:
    findings = audit.get("findings")
    if not isinstance(findings, list):
        return {"total": 0, "by_category": {}, "by_confidence": {}}
    by_category: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        category = finding.get("category")
        confidence = finding.get("confidence")
        if isinstance(category, str):
            by_category[category] = by_category.get(category, 0) + 1
        if isinstance(confidence, str):
            by_confidence[confidence] = by_confidence.get(confidence, 0) + 1
    return {"total": len(findings), "by_category": by_category, "by_confidence": by_confidence}


def _summary_status(gate_verification: dict[str, Any], audit: dict[str, Any]) -> str:
    gate_status = gate_verification.get("status")
    audit_status = audit.get("status")
    if gate_status == "passed" and audit_status == "findings":
        return "passed-with-findings"
    if isinstance(gate_status, str) and gate_status:
        return gate_status
    if audit_status == "clean":
        return "clean"
    if audit_status == "findings":
        return "findings"
    return "unknown"


def _recommended_classification(
    *,
    status: str,
    gate_results: list[dict[str, Any]],
    missing_capabilities: list[str],
    finding_counts: dict[str, Any],
) -> str:
    if any(gate.get("failure_type") == "environment-restricted" for gate in gate_results):
        return "environment-or-runner-blocker"
    if status == "failed":
        return "failing-executable-gates"
    if missing_capabilities:
        return "missing-capabilities"
    if int(finding_counts.get("total") or 0) > 0:
        return "broad-repo-debt"
    if status in {"passed", "clean"}:
        return "clean"
    return "needs-triage"


def _summary_delta(*, baseline: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    baseline_missing = set(baseline.get("missing_capabilities", []))
    final_missing = set(final.get("missing_capabilities", []))
    baseline_findings = _int_value(_nested_value(baseline, "finding_counts", "total"))
    final_findings = _int_value(_nested_value(final, "finding_counts", "total"))
    return {
        "baseline_run_id": baseline["run_id"],
        "final_run_id": final["run_id"],
        "missing_capabilities": {
            "removed": sorted(baseline_missing - final_missing),
            "added": sorted(final_missing - baseline_missing),
            "baseline_total": len(baseline_missing),
            "final_total": len(final_missing),
        },
        "findings_total": {
            "baseline": baseline_findings,
            "final": final_findings,
            "delta": final_findings - baseline_findings,
        },
    }


def _nested_value(payload: dict[str, Any], key: str, nested_key: str) -> object:
    value = payload.get(key)
    return value.get(nested_key) if isinstance(value, dict) else None


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
