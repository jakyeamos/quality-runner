from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quality_runner.artifacts import artifact_dir, write_json
from quality_runner.schema_constants import FIX_PROPOSALS_SCHEMA

FIX_PROPOSE_RESULT_SCHEMA = "quality-runner-fix-propose-result-v0.1"

PROPOSABLE_ACTIONABILITIES = {
    "mechanical-fix",
    "dependency-setup",
    "read-only-policy",
    "environment-blocker",
}


def generated_proposal_id(now: datetime | None = None) -> str:
    timestamp = datetime.now(UTC) if now is None else now.astimezone(UTC)
    return f"proposal-{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def propose_fix(
    *,
    repo_root: Path,
    run_id: str,
    finding_group: str,
    proposal_id: str | None = None,
    finding_ids: list[str] | None = None,
    actor: str = "user",
) -> dict[str, Any]:
    resolved_run_id = run_id.strip()
    run_dir = artifact_dir(repo_root, resolved_run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"run does not exist: {resolved_run_id}")

    artifacts = _load_run_artifacts(run_dir)
    slice_item = resolve_finding_group(
        finding_group=finding_group,
        remediation_plan=artifacts["remediation_plan"],
        handoff=artifacts["handoff"],
    )
    selected_findings = _selected_findings(slice_item, finding_ids)
    proposals, skipped = _build_proposals(
        slice_item=slice_item,
        findings=selected_findings,
        audit_by_id=artifacts["audit_by_id"],
        gate_by_id=artifacts["gate_by_id"],
        fingerprint_by_id=artifacts["fingerprint_by_id"],
    )
    if not proposals and skipped:
        raise ValueError("no proposable findings matched the requested finding group")

    resolved_proposal_id = proposal_id or generated_proposal_id()
    now = datetime.now(UTC).isoformat()
    payload = {
        "schema": FIX_PROPOSALS_SCHEMA,
        "run_id": resolved_run_id,
        "proposal_id": resolved_proposal_id,
        "finding_group": finding_group,
        "implementation_allowed": False,
        "applied": False,
        "actor": actor,
        "slice_title": slice_item.get("title"),
        "artifact_paths": _artifact_paths(repo_root=repo_root, run_dir=run_dir),
        "proposals": proposals,
        "skipped_findings": skipped,
        "checksum": _payload_checksum(proposals),
        "created_at": now,
    }
    output_path = write_json(run_dir / "fix-proposals.json", payload)
    return {
        "schema": FIX_PROPOSE_RESULT_SCHEMA,
        "status": "proposed",
        "implementation_allowed": False,
        "proposal_id": resolved_proposal_id,
        "finding_group": finding_group,
        "proposal_count": len(proposals),
        "skipped_count": len(skipped),
        "fix_proposals": payload,
        "fix_proposals_path": str(output_path),
    }


def resolve_finding_group(
    *,
    finding_group: str,
    remediation_plan: dict[str, Any],
    handoff: dict[str, Any],
) -> dict[str, Any]:
    for collection_name in ("slices", "security_review_slices"):
        collection = remediation_plan.get(collection_name)
        if not isinstance(collection, list):
            continue
        for slice_item in collection:
            if isinstance(slice_item, dict) and slice_item.get("id") == finding_group:
                return slice_item

    next_slice = handoff.get("next_slice")
    if isinstance(next_slice, dict) and next_slice.get("id") == finding_group:
        return next_slice

    raise ValueError(f"finding group does not exist for run: {finding_group}")


def _load_run_artifacts(run_dir: Path) -> dict[str, Any]:
    remediation_plan = _load_required_json(run_dir / "remediation-plan.json", "remediation plan")
    handoff = _load_required_json(run_dir / "agent-handoff.json", "agent handoff")
    audit = _load_optional_json(run_dir / "quality-audit.json")
    gate_verification = _load_optional_json(run_dir / "gate-verification.json")
    ledger = _load_optional_json(run_dir / "resolution-ledger.json")
    return {
        "remediation_plan": remediation_plan,
        "handoff": handoff,
        "audit_by_id": _index_audit_findings(audit),
        "gate_by_id": _index_gate_blockers(gate_verification),
        "fingerprint_by_id": _index_ledger_fingerprints(ledger),
    }


def _build_proposals(
    *,
    slice_item: dict[str, Any],
    findings: list[dict[str, Any]],
    audit_by_id: dict[str, dict[str, Any]],
    gate_by_id: dict[str, dict[str, Any]],
    fingerprint_by_id: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    proposals: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    verification_gates = _string_list(slice_item.get("verification_gates"))

    for index, finding in enumerate(findings, start=1):
        finding_id = finding.get("id")
        if not isinstance(finding_id, str) or not finding_id:
            continue
        audit_finding = _audit_for_slice_finding(finding, audit_by_id)
        actionability = _string_or_none(finding.get("actionability")) or _string_or_none(
            audit_finding.get("actionability")
        )
        fingerprint = _string_or_none(finding.get("fingerprint")) or fingerprint_by_id.get(
            str(finding.get("rule_id") or "")
        )
        summary = _string_or_none(finding.get("summary")) or _string_or_none(
            audit_finding.get("summary")
        )
        if summary is None:
            skipped.append({"finding_id": finding_id, "reason": "finding has no summary"})
            continue

        if finding_id.startswith("gate-"):
            proposal = _gate_proposal(
                proposal_ref=f"{slice_item.get('id')}-{index}",
                finding_id=finding_id,
                gate=gate_by_id.get(finding_id.removeprefix("gate-"), {}),
                summary=summary,
                verification_gates=verification_gates,
            )
            proposals.append(proposal)
            continue

        recommended_fix = _string_or_none(audit_finding.get("recommended_fix"))
        proposable = actionability in PROPOSABLE_ACTIONABILITIES
        if not proposable:
            skipped.append(
                {
                    "finding_id": finding_id,
                    "reason": (
                        f"actionability {actionability or 'unknown'} requires human review before fix proposals"
                    ),
                }
            )
            continue

        steps = _instruction_steps(
            recommended_fix=recommended_fix,
            slice_actions=_string_list(slice_item.get("actions")),
        )
        proposal_body = {
            "proposal_ref": f"{slice_item.get('id')}-{index}",
            "finding_id": finding_id,
            "fingerprint": fingerprint,
            "actionability": actionability,
            "kind": "instruction",
            "summary": summary,
            "recommended_fix": recommended_fix,
            "steps": steps,
            "command": None,
            "unified_diff": None,
            "verification": _verification_steps(audit_finding, verification_gates),
            "applied": False,
            "proposable": True,
        }
        proposal_body["checksum"] = _proposal_checksum(proposal_body)
        proposals.append(proposal_body)

    return proposals, skipped


def _gate_proposal(
    *,
    proposal_ref: str,
    finding_id: str,
    gate: dict[str, Any],
    summary: str,
    verification_gates: list[str],
) -> dict[str, Any]:
    setup = gate.get("dependency_setup")
    command = None
    steps: list[str] = []
    kind = "instruction"
    if isinstance(setup, dict) and isinstance(setup.get("setup_command"), str):
        command = setup["setup_command"]
        kind = "command"
        steps = [f"Run dependency setup: {command}"]
    else:
        recommended = gate.get("recommended_action")
        if isinstance(recommended, str) and recommended:
            steps = [recommended]
        gate_command = gate.get("command")
        if isinstance(gate_command, str) and gate_command:
            command = gate_command
            kind = "command"
            steps.append(f"Run gate command: {gate_command}")

    proposal_body = {
        "proposal_ref": proposal_ref,
        "finding_id": finding_id,
        "fingerprint": None,
        "actionability": "dependency-setup" if kind == "command" else "read-only-policy",
        "kind": kind,
        "summary": summary,
        "recommended_fix": steps[0] if steps else None,
        "steps": steps or ["Resolve the blocked or failed gate before continuing."],
        "command": command,
        "unified_diff": None,
        "verification": verification_gates
        or ["Rerun quality-runner verify-gates and confirm gate verification passed."],
        "applied": False,
        "proposable": True,
    }
    proposal_body["checksum"] = _proposal_checksum(proposal_body)
    return proposal_body


def _instruction_steps(
    *,
    recommended_fix: str | None,
    slice_actions: list[str],
) -> list[str]:
    steps: list[str] = []
    if recommended_fix:
        steps.append(recommended_fix)
    for action in slice_actions:
        if action not in steps:
            steps.append(action)
    return steps or ["Apply the recommended remediation and rerun quality-runner."]


def _verification_steps(
    audit_finding: dict[str, Any],
    verification_gates: list[str],
) -> list[str]:
    verification = _string_list(audit_finding.get("verification"))
    if verification:
        return verification
    if verification_gates:
        return verification_gates
    return ["Rerun quality-runner and confirm the finding no longer appears."]


def _selected_findings(
    slice_item: dict[str, Any],
    finding_ids: list[str] | None,
) -> list[dict[str, Any]]:
    findings = slice_item.get("findings")
    if not isinstance(findings, list):
        return []
    normalized = [finding for finding in findings if isinstance(finding, dict)]
    if not finding_ids:
        return normalized
    allowed = set(finding_ids)
    return [finding for finding in normalized if finding.get("id") in allowed]


def _index_audit_findings(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = audit.get("findings")
    if not isinstance(findings, list):
        return {}
    return {
        finding["id"]: finding
        for finding in findings
        if isinstance(finding, dict) and isinstance(finding.get("id"), str) and finding["id"]
    }


def _index_gate_blockers(gate_verification: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gates = gate_verification.get("gates")
    if not isinstance(gates, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id:
            continue
        diagnostics = gate.get("diagnostics")
        dependency_setup = None
        if isinstance(diagnostics, dict):
            setup = diagnostics.get("dependency_setup")
            if isinstance(setup, dict):
                dependency_setup = setup
        indexed[gate_id] = {
            **gate,
            "dependency_setup": dependency_setup,
        }
    return indexed


def _audit_for_slice_finding(
    finding: dict[str, Any],
    audit_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    finding_id = finding.get("id")
    if isinstance(finding_id, str) and finding_id in audit_by_id:
        return audit_by_id[finding_id]
    rule_id = finding.get("rule_id")
    category = finding.get("category")
    if isinstance(rule_id, str) and isinstance(category, str):
        normalized_category = category.removeprefix("structural:")
        audit_id = f"structural-{normalized_category}-{rule_id}"
        if audit_id in audit_by_id:
            return audit_by_id[audit_id]
    return {}


def _index_ledger_fingerprints(ledger: dict[str, Any]) -> dict[str, str]:
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return {}
    indexed: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fingerprint = entry.get("fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            indexed[str(entry.get("rule_id") or "")] = fingerprint
    return indexed


def _artifact_paths(*, repo_root: Path, run_dir: Path) -> dict[str, str]:
    repo = repo_root.expanduser().resolve()

    def relative(path: Path) -> str:
        return path.resolve().relative_to(repo).as_posix()

    paths = {
        "fix_proposals_json": relative(run_dir / "fix-proposals.json"),
        "agent_handoff_json": relative(run_dir / "agent-handoff.json"),
        "remediation_plan_json": relative(run_dir / "remediation-plan.json"),
        "quality_audit_json": relative(run_dir / "quality-audit.json"),
    }
    gate_verification = run_dir / "gate-verification.json"
    if gate_verification.exists():
        paths["gate_verification_json"] = relative(gate_verification)
    ledger = run_dir / "resolution-ledger.json"
    if ledger.exists():
        paths["resolution_ledger_json"] = relative(ledger)
    return paths


def _payload_checksum(proposals: list[dict[str, Any]]) -> str:
    canonical = json.dumps(proposals, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _proposal_checksum(proposal: dict[str, Any]) -> str:
    material = {
        key: proposal[key]
        for key in (
            "finding_id",
            "kind",
            "summary",
            "recommended_fix",
            "steps",
            "command",
            "unified_diff",
            "verification",
        )
        if key in proposal
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _load_required_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path.name}")
    return _load_json(path)


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
