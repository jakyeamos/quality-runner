from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

KNOWN_ISSUES_SCHEMA = "quality-runner-known-issues-v0.1"
REVIEW_STATE_SCHEMA = "quality-runner-review-state-v0.1"


class KnownIssue(TypedDict, total=False):
    id: str
    fingerprint: str
    summary: str
    status: str
    reason: str
    owner: str
    updated_at: str


def known_issues_path(repo_root: Path) -> Path:
    return repo_root.expanduser().resolve() / ".quality-runner" / "known-issues.json"


def load_known_issues(repo_root: Path) -> list[KnownIssue]:
    path = known_issues_path(repo_root)
    if not path.is_file() or path.is_symlink():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"known issues file is invalid: {error}") from error
    issues = payload.get("issues") if isinstance(payload, Mapping) else None
    if payload.get("schema") != KNOWN_ISSUES_SCHEMA or not isinstance(issues, list):
        raise ValueError("known issues file does not match its schema")
    return [_validate_issue(item) for item in issues]


def accept_known_issue(repo_root: Path, *, fingerprint: str, summary: str, reason: str, owner: str) -> KnownIssue:
    return _upsert(repo_root, {"fingerprint": fingerprint, "summary": summary, "status": "accepted", "reason": reason, "owner": owner})


def edit_known_issue(repo_root: Path, issue_id: str, **changes: str) -> KnownIssue:
    issues = load_known_issues(repo_root)
    for issue in issues:
        if issue.get("id") == issue_id:
            issue.update({key: value for key, value in changes.items() if key in {"summary", "reason", "owner", "status"}})
            issue["updated_at"] = _now()
            _save(repo_root, issues)
            return issue
    raise KeyError(f"unknown issue not found: {issue_id}")


def remove_known_issue(repo_root: Path, issue_id: str) -> None:
    issues = [issue for issue in load_known_issues(repo_root) if issue.get("id") != issue_id]
    _save(repo_root, issues)


def known_issue_findings(repo_root: Path, findings: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    accepted = {issue.get("fingerprint"): issue for issue in load_known_issues(repo_root) if issue.get("status") == "accepted"}
    result: list[dict[str, object]] = []
    for finding in findings:
        fingerprint = finding.get("fingerprint")
        if isinstance(fingerprint, str) and fingerprint in accepted:
            result.append({**finding, "classification": "known-accepted", "status": "known-accepted"})
    return result


def major_change_requires_reverification(
    *,
    baseline_changed: bool = False,
    default_branch_changed: bool = False,
    changed_files: Sequence[str] = (),
    configured_high_risk_paths: Sequence[str] = (),
    explicit: bool = False,
) -> bool:
    if baseline_changed or default_branch_changed or explicit:
        return True
    return any(_matches_path(path, configured_high_risk_paths) for path in changed_files)


def finalize_cycle_state(
    *,
    cycle_id: str,
    findings: Sequence[Mapping[str, object]],
    prior_findings: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    prior = {item.get("fingerprint"): item for item in prior_findings}
    current = {item.get("fingerprint"): item for item in findings}
    entries: list[dict[str, object]] = []
    for fingerprint, finding in current.items():
        if not isinstance(fingerprint, str):
            continue
        old = prior.get(fingerprint)
        status = "open"
        if isinstance(old, Mapping) and old.get("status") in {"accepted", "known-accepted"}:
            status = "accepted"
        elif isinstance(old, Mapping) and old:
            status = "uncertain"
        entries.append({"fingerprint": fingerprint, "status": status, "finding": dict(finding)})
    for fingerprint, old in prior.items():
        if isinstance(fingerprint, str) and fingerprint not in current:
            entries.append({"fingerprint": fingerprint, "status": "resolved", "finding": dict(old)})
    return {"schema": REVIEW_STATE_SCHEMA, "cycle_id": cycle_id, "active": False, "entries": entries}


def _upsert(repo_root: Path, issue: KnownIssue) -> KnownIssue:
    issues = load_known_issues(repo_root)
    existing = next((item for item in issues if item.get("fingerprint") == issue["fingerprint"]), None)
    if existing is None:
        issue = {"id": f"issue-{len(issues) + 1}", **issue}
        issues.append(issue)
    else:
        existing.update(issue)
        existing["updated_at"] = _now()
        issue = existing
    _save(repo_root, issues)
    return issue


def _save(repo_root: Path, issues: Sequence[KnownIssue]) -> None:
    path = known_issues_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("known issues file must not be a symlink")
    path.write_text(json.dumps({"schema": KNOWN_ISSUES_SCHEMA, "issues": list(issues)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_issue(value: object) -> KnownIssue:
    if not isinstance(value, Mapping) or not all(isinstance(value.get(key), str) and value.get(key) for key in ("id", "fingerprint", "summary", "status")):
        raise ValueError("known issue requires id, fingerprint, summary, and status")
    return dict(value)


def _matches_path(path: str, patterns: Sequence[str]) -> bool:
    return any(path == pattern or path.startswith(pattern.rstrip("/") + "/") for pattern in patterns)


def _now() -> str:
    return datetime.now(UTC).isoformat()
