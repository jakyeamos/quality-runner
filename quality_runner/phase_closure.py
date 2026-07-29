from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from quality_runner.artifacts import artifact_dir, write_json, write_text
from quality_runner.phase_contract import (
    BLOCKING_DISPOSITIONS,
    early_refresh_recommendation,
    finding_matches_contract,
    finding_owner,
)


def build_phase_closure(
    *,
    baseline_audit: dict[str, Any],
    current_audit: dict[str, Any],
    current_ledger: dict[str, Any],
    contract: dict[str, Any],
    changed_paths: list[str] | None = None,
) -> dict[str, Any]:
    baseline = _index(_findings(baseline_audit))
    current = _index(_findings(current_audit))
    scoped_current = {
        key: item for key, item in current.items() if finding_matches_contract(item, contract)
    }
    scoped_baseline = {
        key: item for key, item in baseline.items() if finding_matches_contract(item, contract)
    }
    statuses = _statuses(current_ledger, contract)
    new = sorted(set(scoped_current) - set(scoped_baseline))
    persisted = sorted(set(scoped_current) & set(scoped_baseline))
    resolved = sorted(set(scoped_baseline) - set(scoped_current))
    dispositions = {
        fingerprint: status
        for fingerprint in [*new, *persisted]
        if (status := statuses.get(fingerprint)) in {"accepted-false-positive", "accepted-intentional"}
    }
    actionable = [
        fingerprint
        for fingerprint in [*new, *persisted]
        if statuses.get(fingerprint, "unresolved") in BLOCKING_DISPOSITIONS
        or fingerprint not in dispositions
    ]
    ownership = {
        fingerprint: finding_owner(fingerprint, contract)
        for fingerprint in [*new, *persisted]
    }
    unmapped = sorted(
        fingerprint for fingerprint, owner in ownership.items() if not owner["mapped"]
    )
    out_of_scope = sorted(set(current) - set(scoped_current))
    early_refresh = early_refresh_recommendation(contract, changed_paths)
    blockers = []
    if actionable:
        blockers.append("phase scope still contains actionable findings")
    if unmapped:
        blockers.append("phase findings are not mapped to a GSD plan/task")
    if early_refresh["recommended"]:
        blockers.append("early refresh is recommended before phase closure")
    return {
        "schema": "quality-runner-phase-closure-v0.1",
        "status": "passed" if not blockers else "blocked",
        "implementation_allowed": False,
        "phase_id": contract["phase_id"],
        "plan_id": contract.get("plan_id"),
        "scan_tier": contract.get("scan_tier", "phase"),
        "scope": contract.get("scope", {}),
        "findings": {
            "new": [_ref(current[item], ownership[item], statuses.get(item)) for item in new],
            "persisted": [
                _ref(current[item], ownership[item], statuses.get(item)) for item in persisted
            ],
            "resolved": [_ref(baseline[item], finding_owner(item, contract), None) for item in resolved],
            "out_of_scope": [_ref(current[item], finding_owner(item, contract), None) for item in out_of_scope],
        },
        "counts": {
            "new": len(new),
            "persisted": len(persisted),
            "resolved": len(resolved),
            "actionable": len(actionable),
            "dispositioned": len(dispositions),
            "unmapped": len(unmapped),
            "out_of_scope": len(out_of_scope),
        },
        "ownership": ownership,
        "dispositions": dispositions,
        "early_refresh": early_refresh,
        "blockers": blockers,
    }


def phase_closure_payload(
    *,
    repo_root: Path,
    current_run_id: str,
    baseline_run_id: str,
    contract: dict[str, Any],
    changed_paths: list[str] | None = None,
) -> dict[str, Any]:
    current_dir = artifact_dir(repo_root, current_run_id)
    baseline_dir = artifact_dir(repo_root, baseline_run_id)
    current = _load(current_dir / "quality-audit.json")
    baseline = _load(baseline_dir / "quality-audit.json")
    ledger = _load_optional(current_dir / "resolution-ledger.json")
    payload = build_phase_closure(
        baseline_audit=baseline,
        current_audit=current,
        current_ledger=ledger,
        contract=contract,
        changed_paths=changed_paths,
    )
    payload["current_run_id"] = current_run_id
    payload["baseline_run_id"] = baseline_run_id
    payload["artifact_paths"] = {
        "phase_closure_json": str(current_dir / "phase-closure.json"),
        "phase_closure_md": str(current_dir / "phase-closure.md"),
    }
    write_json(current_dir / "phase-closure.json", payload)
    write_text(current_dir / "phase-closure.md", render_phase_closure(payload))
    return payload


def render_phase_closure(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    lines = [
        f"# Phase closure: {payload.get('phase_id')}",
        "",
        f"- Status: **{payload.get('status', 'unknown')}**",
        f"- Current run: `{payload.get('current_run_id')}`",
        f"- Baseline run: `{payload.get('baseline_run_id')}`",
        f"- Scan tier: `{payload.get('scan_tier')}`",
        "",
        "## Counts",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in counts.items())
    lines.extend(["", "## Blockers", ""])
    blockers = payload.get("blockers")
    lines.extend(f"- {item}" for item in blockers if isinstance(item, str)) if blockers else lines.append("- None")
    lines.extend(["", "## Early refresh", ""])
    early = payload.get("early_refresh", {})
    lines.append(f"- Recommended: `{early.get('recommended', False)}`")
    lines.extend(f"- {item}" for item in early.get("reasons", []) if isinstance(item, str))
    lines.append("")
    return "\n".join(lines)


def _findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings = payload.get("findings")
    return [item for item in findings if isinstance(item, dict)] if isinstance(findings, list) else []


def _index(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_fingerprint(item): item for item in findings}


def _fingerprint(finding: dict[str, Any]) -> str:
    value = finding.get("fingerprint")
    if isinstance(value, str) and value:
        return value
    stable = {key: finding.get(key) for key in ("id", "rule_id", "category", "file", "summary", "evidence")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


def _statuses(ledger: dict[str, Any], contract: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for item in ledger.get("entries", []) if isinstance(ledger.get("entries"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("fingerprint"), str):
            status = item.get("status")
            statuses[item["fingerprint"]] = status if isinstance(status, str) else "unresolved"
    for item in contract.get("dispositions", []):
        if isinstance(item, dict) and isinstance(item.get("fingerprint"), str):
            statuses[item["fingerprint"]] = str(item["status"])
    return statuses


def _ref(finding: dict[str, Any], owner: dict[str, Any], status: str | None) -> dict[str, Any]:
    return {
        "fingerprint": _fingerprint(finding),
        "id": finding.get("id"),
        "rule_id": finding.get("rule_id") or finding.get("rule"),
        "file": finding.get("file") or finding.get("path"),
        "category": finding.get("category"),
        "severity": finding.get("severity"),
        "summary": finding.get("summary") or finding.get("message"),
        "status": status or "unresolved",
        "owner": owner,
    }


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required QR artifact does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"QR artifact must contain an object: {path}")
    return payload


def _load_optional(path: Path) -> dict[str, Any]:
    return _load(path) if path.exists() else {}
