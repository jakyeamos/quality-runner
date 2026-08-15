from __future__ import annotations

from typing import Any


def public_timeout_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "per_gate_timeout_seconds": contract["per_gate_timeout_seconds"],
        "timeout_policy": contract["timeout_policy"],
        "source": contract["source"],
        "baseline_status": contract["baseline_status"],
        "baseline_reason": contract["baseline_reason"],
        "baseline_id": contract["baseline_id"],
        "baseline_path": contract["baseline_path"],
        "baseline_identity_sha256": contract["baseline_identity_sha256"],
        "baseline_sample_count": contract["baseline_sample_count"],
        "expected_gate_plan_sha256": contract["expected_gate_plan_sha256"],
        "baseline_recording": contract.get("baseline_recording"),
        "inspect_timeout_seconds": contract["inspect_timeout_seconds"],
        "inspect_timeout_source": contract["inspect_timeout_source"],
        "verify_timeout_seconds": contract["verify_timeout_seconds"],
        "verify_timeout_source": contract["verify_timeout_source"],
        "run_timeout_seconds": contract["run_timeout_seconds"],
        "run_timeout_source": contract["run_timeout_source"],
        "total_timeout_seconds": contract["total_timeout_seconds"],
        "total_timeout_source": contract["total_timeout_source"],
        "total_timeout_reason": contract["total_timeout_reason"],
    }
