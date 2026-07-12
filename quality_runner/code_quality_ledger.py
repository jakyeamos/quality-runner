from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.code_quality_findings import _counts
from quality_runner.code_quality_paths import _string_or_none
from quality_runner.review_state import finalize_cycle_state
from quality_runner.schema_constants import RESOLUTION_LEDGER_SCHEMA

ACCEPTED_STATUSES = {"accepted-intentional", "accepted-false-positive", "blocked-with-prerequisite"}
RESOLUTION_STATUSES = {
    "unresolved",
    "fixed",
    "superseded-by-current-scan",
    *ACCEPTED_STATUSES,
}


def build_resolution_ledger(
    *,
    repo_root: Path,
    run_id: str,
    code_quality_scan: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    current_findings = _current_findings(code_quality_scan)
    current_fingerprints = set(current_findings)
    previous_entries = _latest_previous_resolution_entries(repo_root, run_id)
    accepted_by_config = _accepted_dispositions(config)
    accepted_by_previous = {
        entry["fingerprint"]: entry
        for entry in previous_entries
        if entry.get("status") in ACCEPTED_STATUSES and isinstance(entry.get("fingerprint"), str)
    }
    entries: list[dict[str, Any]] = []

    for fingerprint, finding in sorted(current_findings.items()):
        configured = accepted_by_config.get(fingerprint)
        previous = accepted_by_previous.get(fingerprint)
        status = "unresolved"
        reason = ""
        owner = None
        expires = None
        if configured is not None:
            status = configured["status"]
            reason = configured["reason"]
            owner = configured["owner"]
            expires = configured.get("expires")
        elif previous is not None:
            status = str(previous["status"])
            reason = str(previous.get("reason") or previous.get("disposition") or "")
            owner = _string_or_none(previous.get("owner"))
            expires = _string_or_none(previous.get("expires"))

        entries.append(
            _ledger_entry(
                finding=finding,
                status=status,
                reason=reason,
                owner=owner,
                expires=expires,
            )
        )

    for previous in previous_entries:
        fingerprint = previous.get("fingerprint")
        if not isinstance(fingerprint, str) or fingerprint in current_fingerprints:
            continue
        if previous.get("status") == "fixed":
            continue
        entries.append(
            {
                **previous,
                "status": "superseded-by-current-scan",
                "reason": "Finding absent from current scan; QR did not execute remediation.",
            }
        )

    entries.sort(key=lambda item: (str(item["status"]), str(item["rule_id"]), str(item["file"])))
    return {
        "schema": RESOLUTION_LEDGER_SCHEMA,
        "run_id": run_id,
        "summary": {
            "total_entries": len(entries),
            "by_status": _counts(entries, "status", sorted(RESOLUTION_STATUSES)),
        },
        "entries": entries,
    }


def render_resolution_ledger_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Quality Runner Resolution Ledger",
        "",
        f"- Schema: {ledger.get('schema')}",
        f"- Run ID: {ledger.get('run_id')}",
        "",
        "## Status Counts",
        "",
    ]
    summary = ledger.get("summary")
    by_status = summary.get("by_status") if isinstance(summary, dict) else None
    if isinstance(by_status, dict):
        for status, count in sorted(by_status.items()):
            lines.append(f"- {status}: {count}")
    lines.extend(["", "## Entries", ""])

    entries = ledger.get("entries")
    if isinstance(entries, list) and entries:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            lines.append(
                f"- {entry.get('status')}: {entry.get('rule_id')} "
                f"({entry.get('file')}:{entry.get('line')})"
            )
    else:
        lines.append("No resolution entries.")
    return "\n".join(lines).rstrip() + "\n"


def build_review_cycle_ledger(
    *,
    cycle_id: str,
    findings: list[dict[str, Any]],
    prior_findings: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    """Build review-only resolution state without changing audit ledger semantics."""
    return finalize_cycle_state(
        cycle_id=cycle_id,
        findings=findings,
        prior_findings=prior_findings or [],
    )


def _current_findings(code_quality_scan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = code_quality_scan.get("findings")
    if not isinstance(findings, list):
        return {}
    return {
        finding["fingerprint"]: finding
        for finding in findings
        if isinstance(finding, dict) and isinstance(finding.get("fingerprint"), str)
    }


def _ledger_entry(
    *,
    finding: dict[str, Any],
    status: str,
    reason: str,
    owner: str | None,
    expires: str | None,
) -> dict[str, Any]:
    return {
        "fingerprint": finding["fingerprint"],
        "status": status,
        "category": finding["category"],
        "severity": finding["severity"],
        "rule_id": finding["rule_id"],
        "file": finding["file"],
        "line": finding["line"],
        "score": finding["score"],
        "confidence": finding["confidence"],
        "verification": finding["verification"],
        "reason": reason,
        "owner": owner,
        "expires": expires,
    }


def _latest_previous_resolution_entries(repo_root: Path, run_id: str) -> list[dict[str, Any]]:
    runs_dir = repo_root.expanduser().resolve() / ".quality-runner" / "runs"
    if not runs_dir.is_dir():
        return []
    candidates = [
        path / "resolution-ledger.json"
        for path in sorted(runs_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
        if path.is_dir() and path.name != run_id and not path.is_symlink()
    ]
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            import json

            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = payload.get("entries")
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]
    return []


def _accepted_dispositions(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    dispositions = config.get("accepted_dispositions")
    if not isinstance(dispositions, list):
        return {}
    accepted: dict[str, dict[str, str]] = {}
    for item in dispositions:
        if not isinstance(item, dict):
            continue
        fingerprint = item.get("fingerprint")
        status = item.get("status")
        reason = item.get("reason")
        owner = item.get("owner")
        expires = item.get("expires")
        if (
            isinstance(fingerprint, str)
            and fingerprint
            and isinstance(status, str)
            and status in ACCEPTED_STATUSES
            and isinstance(reason, str)
            and reason
            and isinstance(owner, str)
            and owner
        ):
            accepted[fingerprint] = {
                "fingerprint": fingerprint,
                "status": status,
                "reason": reason,
                "owner": owner,
                **({"expires": expires} if isinstance(expires, str) and expires else {}),
            }
    return accepted
