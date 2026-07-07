from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner.artifacts import write_json
from quality_runner.code_quality_ledger import ACCEPTED_STATUSES
GATE_RUN_SCHEMA = "quality-runner-gate-run-v0.1"
TERMINAL_GATE_RUN_STATUSES = {"completed", "aborted"}

DISPOSITION_STATUSES = set(ACCEPTED_STATUSES)


def find_active_gate_run_id(*, repo_root: Path, run_id: str) -> str | None:
    gate_runs_root = repo_root.expanduser().resolve() / ".quality-runner" / "gate-runs"
    if not gate_runs_root.is_dir():
        return None
    for gate_dir in sorted(gate_runs_root.iterdir(), key=lambda item: item.name):
        if not gate_dir.is_dir() or gate_dir.is_symlink():
            continue
        gate_run_path = gate_dir / "gate-run.json"
        if not gate_run_path.is_file():
            continue
        try:
            payload = json.loads(gate_run_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("schema") != GATE_RUN_SCHEMA:
            continue
        if payload.get("run_id") != run_id:
            continue
        status = payload.get("status")
        if isinstance(status, str) and status not in TERMINAL_GATE_RUN_STATUSES:
            return gate_dir.name
    return None


def enrich_record_disposition_response(
    *,
    repo_root: Path,
    run_id: str,
    response: dict[str, Any],
    disposition: str,
    owner: str,
) -> dict[str, Any]:
    if disposition not in DISPOSITION_STATUSES:
        raise ValueError(f"unsupported disposition status: {disposition}")
    if not owner.strip():
        raise ValueError("record-disposition requires a non-empty owner")
    finding_ids = response.get("finding_ids")
    if not isinstance(finding_ids, list) or not finding_ids:
        raise ValueError("record-disposition requires at least one --finding-id")

    references = resolve_finding_references(repo_root=repo_root, run_id=run_id, finding_ids=finding_ids)
    missing = sorted(set(finding_ids) - {item["finding_id"] for item in references})
    if missing:
        raise ValueError(f"finding ids not present in run audit: {', '.join(missing)}")

    fingerprints = sorted(
        {
            item["fingerprint"]
            for item in references
            if isinstance(item.get("fingerprint"), str) and item["fingerprint"]
        }
    )
    enriched = dict(response)
    enriched["disposition"] = disposition
    enriched["owner"] = owner
    if fingerprints:
        enriched["fingerprints"] = fingerprints
    enriched["finding_references"] = references
    return enriched


def apply_record_disposition(
    *,
    repo_root: Path,
    run_id: str,
    gate_run_id: str,
    response: dict[str, Any],
) -> Path | None:
    disposition = response.get("disposition")
    owner = response.get("owner")
    if not isinstance(disposition, str) or not isinstance(owner, str):
        return None

    finding_ids = response.get("finding_ids")
    if not isinstance(finding_ids, list):
        return None

    records = load_finding_dispositions(repo_root=repo_root, run_id=run_id)
    now = datetime.now(UTC).isoformat()
    for finding_id in finding_ids:
        if not isinstance(finding_id, str) or not finding_id:
            continue
        records.append(
            {
                "finding_id": finding_id,
                "status": disposition,
                "reason": str(response.get("notes") or ""),
                "owner": owner,
                "source": "gate-response",
                "gate_run_id": gate_run_id,
                "at": now,
                "fingerprints": _fingerprints_for_finding(response, finding_id),
            }
        )

    run_dir = repo_root.expanduser().resolve() / ".quality-runner" / "runs" / run_id
    ledger_path = run_dir / "resolution-ledger.json"
    if not ledger_path.is_file():
        return None

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if not isinstance(ledger, dict):
        return None
    ledger["finding_dispositions"] = _merge_finding_dispositions(
        ledger.get("finding_dispositions"),
        records,
    )
    ledger = apply_finding_dispositions_to_entries(ledger)
    write_json(ledger_path, ledger)
    return ledger_path


def merge_gate_finding_dispositions(
    ledger: dict[str, Any],
    *,
    repo_root: Path,
    run_id: str,
) -> dict[str, Any]:
    records = load_finding_dispositions(repo_root=repo_root, run_id=run_id)
    if not records:
        return ledger
    merged = dict(ledger)
    merged["finding_dispositions"] = _merge_finding_dispositions(
        ledger.get("finding_dispositions"),
        records,
    )
    return apply_finding_dispositions_to_entries(merged)


def load_finding_dispositions(*, repo_root: Path, run_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    gate_runs_root = repo_root.expanduser().resolve() / ".quality-runner" / "gate-runs"
    if not gate_runs_root.is_dir():
        return records
    for gate_dir in sorted(gate_runs_root.iterdir(), key=lambda item: item.name):
        if not gate_dir.is_dir() or gate_dir.is_symlink():
            continue
        gate_run_path = gate_dir / "gate-run.json"
        if not gate_run_path.is_file():
            continue
        try:
            gate_run = _load_json(gate_run_path)
        except (OSError, ValueError):
            continue
        if gate_run.get("run_id") != run_id:
            continue
        responses = _load_gate_responses(gate_dir / "gate-responses.jsonl")
        for response in responses:
            if response.get("action") != "record-disposition":
                continue
            disposition = response.get("disposition")
            owner = response.get("owner")
            finding_ids = response.get("finding_ids")
            if (
                not isinstance(disposition, str)
                or not isinstance(owner, str)
                or not isinstance(finding_ids, list)
            ):
                continue
            at = response.get("at")
            for finding_id in finding_ids:
                if not isinstance(finding_id, str) or not finding_id:
                    continue
                records.append(
                    {
                        "finding_id": finding_id,
                        "status": disposition,
                        "reason": str(response.get("notes") or ""),
                        "owner": owner,
                        "source": "gate-response",
                        "gate_run_id": gate_dir.name,
                        "at": at if isinstance(at, str) else None,
                        "fingerprints": _fingerprints_for_finding(response, finding_id),
                    }
                )
    return records


def resolve_finding_references(
    *,
    repo_root: Path,
    run_id: str,
    finding_ids: list[str],
) -> list[dict[str, Any]]:
    audit = _load_run_json(repo_root, run_id, "quality-audit.json")
    scan = _load_run_json(repo_root, run_id, "code-quality-scan.json")
    audit_by_id = _audit_findings_by_id(audit)
    fingerprint_by_id = _scan_fingerprints_by_id(scan)

    references: list[dict[str, Any]] = []
    for finding_id in finding_ids:
        audit_finding = audit_by_id.get(finding_id)
        if audit_finding is None:
            continue
        fingerprint = fingerprint_by_id.get(finding_id)
        if fingerprint is None and isinstance(audit_finding.get("fingerprint"), str):
            fingerprint = audit_finding["fingerprint"]
        references.append(
            {
                "finding_id": finding_id,
                "fingerprint": fingerprint,
                "category": audit_finding.get("category"),
            }
        )
    return references


def apply_finding_dispositions_to_entries(ledger: dict[str, Any]) -> dict[str, Any]:
    records = ledger.get("finding_dispositions")
    if not isinstance(records, list) or not records:
        return ledger

    by_fingerprint: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        fingerprints = record.get("fingerprints")
        if isinstance(fingerprints, list):
            for fingerprint in fingerprints:
                if isinstance(fingerprint, str) and fingerprint:
                    by_fingerprint[fingerprint] = record

    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return ledger

    updated_entries: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            updated_entries.append(entry)
            continue
        fingerprint = entry.get("fingerprint")
        record = by_fingerprint.get(fingerprint) if isinstance(fingerprint, str) else None
        if record is None:
            updated_entries.append(entry)
            continue
        updated_entries.append(
            {
                **entry,
                "status": record["status"],
                "reason": record.get("reason") or entry.get("reason") or "",
                "owner": record.get("owner"),
                "disposition_source": record.get("source"),
                "disposition_gate_run_id": record.get("gate_run_id"),
            }
        )

    return {**ledger, "entries": updated_entries}


def _merge_finding_dispositions(
    existing: object,
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in [*(_list(existing)), *incoming]:
        if not isinstance(record, dict):
            continue
        finding_id = record.get("finding_id")
        if isinstance(finding_id, str) and finding_id:
            merged[finding_id] = record
    return [merged[key] for key in sorted(merged)]


def _audit_findings_by_id(audit: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(audit, dict):
        return {}
    findings = audit.get("findings")
    if not isinstance(findings, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for finding in findings:
        if isinstance(finding, dict) and isinstance(finding.get("id"), str):
            indexed[finding["id"]] = finding
    return indexed


def _scan_fingerprints_by_id(scan: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(scan, dict):
        return {}
    findings = scan.get("findings")
    if not isinstance(findings, list):
        return {}
    indexed: dict[str, str] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = finding.get("id")
        fingerprint = finding.get("fingerprint")
        if isinstance(finding_id, str) and isinstance(fingerprint, str):
            indexed[finding_id] = fingerprint
    return indexed


def _load_run_json(repo_root: Path, run_id: str, name: str) -> dict[str, Any] | None:
    path = repo_root.expanduser().resolve() / ".quality-runner" / "runs" / run_id / name
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _fingerprints_for_finding(response: dict[str, Any], finding_id: str) -> list[str]:
    references = response.get("finding_references")
    if isinstance(references, list):
        for reference in references:
            if not isinstance(reference, dict):
                continue
            if reference.get("finding_id") != finding_id:
                continue
            fingerprint = reference.get("fingerprint")
            if isinstance(fingerprint, str) and fingerprint:
                return [fingerprint]
    fingerprints = response.get("fingerprints")
    if isinstance(fingerprints, list):
        return [item for item in fingerprints if isinstance(item, str) and item]
    return []


def _load_gate_responses(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    responses: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            responses.append(payload)
    return responses


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
