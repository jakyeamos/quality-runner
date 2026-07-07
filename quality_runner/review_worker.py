from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.controller_reports import validate_controller_report
from quality_runner.findings import validate_agent_handoff
from quality_runner.handoff_lint import validate_handoff_quality

REVIEW_WORKER_RESULT_SCHEMA = "quality-runner-review-worker-result-v0.1"


def review_worker_payload(
    *,
    repo_root: Path,
    baseline_run_id: str,
    final_run_id: str,
    worker_report_path: Path,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    baseline_dir = root / ".quality-runner" / "runs" / baseline_run_id
    final_dir = root / ".quality-runner" / "runs" / final_run_id
    if not baseline_dir.is_dir():
        raise FileNotFoundError(f"baseline run not found: {baseline_run_id}")
    if not final_dir.is_dir():
        raise FileNotFoundError(f"final run not found: {final_run_id}")
    worker_report = _load_json(worker_report_path, "worker report")

    errors: list[str] = []
    warnings: list[str] = []

    worker_validation = validate_controller_report(worker_report)
    if not worker_validation.get("passed"):
        errors.extend(
            f"worker report: {item}"
            for item in worker_validation.get("errors", [])
            if isinstance(item, str)
        )

    final_handoff = _load_json(final_dir / "agent-handoff.json", "final agent handoff")
    handoff_validation = validate_agent_handoff(final_handoff)
    if not handoff_validation.get("passed"):
        errors.extend(
            f"final handoff: {item}"
            for item in handoff_validation.get("errors", [])
            if isinstance(item, str)
        )
    quality_validation = validate_handoff_quality(
        final_handoff,
        remediation_plan=_load_json(final_dir / "remediation-plan.json", "final remediation plan"),
    )
    if not quality_validation.get("passed"):
        errors.extend(
            f"final handoff quality: {item}"
            for item in quality_validation.get("errors", [])
            if isinstance(item, str)
        )

    baseline_scan = _optional_json(baseline_dir / "code-quality-scan.json")
    final_scan = _optional_json(final_dir / "code-quality-scan.json")
    fingerprint_delta = _fingerprint_delta(baseline_scan, final_scan)
    if fingerprint_delta["unresolved"]:
        warnings.append(
            f"{len(fingerprint_delta['unresolved'])} baseline fingerprints still present in final scan"
        )

    changed_files = worker_report.get("files_changed")
    expected_files = _expected_files_from_worker(worker_report)
    if isinstance(changed_files, list) and expected_files:
        unexpected = sorted(set(changed_files) - set(expected_files))
        if unexpected:
            warnings.append(
                f"worker changed files outside declared scope: {', '.join(unexpected[:5])}"
            )

    final_summary = _optional_json(final_dir / "run-summary.json")
    status = final_handoff.get("status")
    return {
        "schema": REVIEW_WORKER_RESULT_SCHEMA,
        "status": "passed" if not errors else "rejected",
        "implementation_allowed": False,
        "baseline_run_id": baseline_run_id,
        "final_run_id": final_run_id,
        "final_handoff_status": status if isinstance(status, str) else None,
        "final_lifecycle_status": final_handoff.get("lifecycle_status"),
        "fingerprint_delta": fingerprint_delta,
        "gate_verification_status": _nested(final_summary, "gate_verification", "status"),
        "errors": errors,
        "warnings": warnings,
    }


def _fingerprint_delta(
    baseline_scan: dict[str, Any] | None,
    final_scan: dict[str, Any] | None,
) -> dict[str, Any]:
    baseline = _fingerprints(baseline_scan)
    final = _fingerprints(final_scan)
    cleared = sorted(baseline - final)
    unresolved = sorted(baseline & final)
    introduced = sorted(final - baseline)
    return {
        "baseline_count": len(baseline),
        "final_count": len(final),
        "cleared": cleared,
        "unresolved": unresolved,
        "introduced": introduced,
    }


def _fingerprints(scan: dict[str, Any] | None) -> set[str]:
    if not isinstance(scan, dict):
        return set()
    findings = scan.get("findings")
    if not isinstance(findings, list):
        return set()
    return {
        str(finding["fingerprint"])
        for finding in findings
        if isinstance(finding, dict)
        and isinstance(finding.get("fingerprint"), str)
        and finding["fingerprint"]
    }


def _expected_files_from_worker(worker_report: dict[str, Any]) -> list[str]:
    files = worker_report.get("files_changed")
    if isinstance(files, list):
        return [item for item in files if isinstance(item, str)]
    return []


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _nested(payload: dict[str, Any] | None, *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
