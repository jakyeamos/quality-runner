from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.code_quality_findings import _counts
from quality_runner.security.taxonomy import SECURITY_RESOLUTION_STATUSES

SECURITY_ACCEPTED_STATUSES = {
    "false-positive",
    "accepted-risk",
    "accepted-intentional",
    "accepted-false-positive",
    "blocked",
    "blocked-with-prerequisite",
}


def merge_security_ledger_entries(
    ledger: dict[str, Any],
    *,
    security_scan: dict[str, Any],
    config: dict[str, Any],
    repo_root: Path,
    run_id: str,
) -> dict[str, Any]:
    if security_scan.get("settings", {}).get("enabled") is False:
        return ledger

    candidates = security_scan.get("candidates")
    if not isinstance(candidates, list):
        return ledger

    previous = _latest_security_entries(repo_root, run_id)
    accepted_by_config = _security_accepted_dispositions(config)
    accepted_by_previous = {
        entry["fingerprint"]: entry
        for entry in previous
        if entry.get("fingerprint") and entry.get("status") in SECURITY_ACCEPTED_STATUSES
    }

    entries = list(ledger.get("entries", []))
    current_fingerprints = {
        entry.get("fingerprint") for entry in entries if entry.get("fingerprint")
    }

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        fingerprint = candidate.get("fingerprint")
        if not isinstance(fingerprint, str) or fingerprint in current_fingerprints:
            continue
        configured = accepted_by_config.get(fingerprint)
        previous_entry = accepted_by_previous.get(fingerprint)
        status = "review-required" if candidate.get("requires_agent_review") else "unreviewed"
        reason = ""
        owner = None
        expires = None
        if configured is not None:
            status = configured["status"]
            reason = configured["reason"]
            owner = configured["owner"]
            expires = configured.get("expires")
        elif previous_entry is not None:
            status = str(previous_entry.get("status") or status)
            reason = str(previous_entry.get("reason") or "")
            owner = previous_entry.get("owner")
            expires = previous_entry.get("expires")

        entries.append(
            {
                "fingerprint": fingerprint,
                "status": status,
                "category": f"security:{candidate.get('category')}",
                "severity": candidate.get("severity_hint") or "medium",
                "rule_id": str(candidate.get("category") or "security-candidate"),
                "file": candidate.get("file") or "unknown",
                "line": candidate.get("line") or 1,
                "score": _severity_score(str(candidate.get("severity_hint") or "medium")),
                "confidence": candidate.get("confidence") or "medium",
                "verification": candidate.get("verification_guidance") or "",
                "reason": reason,
                "owner": owner,
                "expires": expires,
                "security_candidate_id": candidate.get("id"),
                "ledger_kind": "security",
            }
        )
        current_fingerprints.add(fingerprint)

    for previous_entry in previous:
        fingerprint = previous_entry.get("fingerprint")
        if not isinstance(fingerprint, str) or fingerprint in current_fingerprints:
            continue
        if previous_entry.get("status") == "fixed":
            continue
        entries.append(
            {
                **previous_entry,
                "status": "stale",
                "reason": "Security candidate absent from current scan.",
            }
        )

    entries.sort(
        key=lambda item: (str(item.get("status")), str(item.get("file")), str(item.get("line")))
    )
    summary = ledger.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    by_status = _counts(entries, "status", sorted(SECURITY_RESOLUTION_STATUSES))
    return {
        **ledger,
        "summary": {
            **summary,
            "total_entries": len(entries),
            "by_status": by_status,
            "security_entries": sum(
                1 for entry in entries if entry.get("ledger_kind") == "security"
            ),
        },
        "entries": entries,
    }


def _severity_score(severity: str) -> int:
    return {
        "critical": 1000,
        "high": 800,
        "medium": 500,
        "low": 200,
        "info": 50,
    }.get(severity, 300)


def _latest_security_entries(repo_root: Path, run_id: str) -> list[dict[str, Any]]:
    runs_dir = repo_root.expanduser().resolve() / ".quality-runner" / "runs"
    if not runs_dir.is_dir():
        return []
    for path in sorted(runs_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_dir() or path.name == run_id or path.is_symlink():
            continue
        candidate = path / "resolution-ledger.json"
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            import json

            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = payload.get("entries")
        if not isinstance(entries, list):
            continue
        return [
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("ledger_kind") == "security"
        ]
    return []


def _security_accepted_dispositions(config: dict[str, Any]) -> dict[str, dict[str, str]]:
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
            and fingerprint.startswith("sec-")
            and isinstance(status, str)
            and status
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
