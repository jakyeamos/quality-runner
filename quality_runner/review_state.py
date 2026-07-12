from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

from quality_runner.core.review_contracts import KnownIssue as NormalizedKnownIssue
from quality_runner.core.review_contracts import KnownIssueDraft

KNOWN_ISSUES_SCHEMA = "quality-runner-known-issues-v0.1"
REVIEW_STATE_SCHEMA = "quality-runner-review-state-v0.1"
_REQUIRED_ISSUE_FIELDS = ("id", "fingerprint", "summary", "status")
_OPTIONAL_ISSUE_FIELDS = ("reason", "owner", "updated_at")


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
    return [_issue_to_v1(issue) for issue in _load_normalized_known_issues(repo_root)]


def _load_normalized_known_issues(repo_root: Path) -> list[NormalizedKnownIssue]:
    path = known_issues_path(repo_root)
    if not path.is_file() or path.is_symlink():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"known issues file is invalid: {error}") from error
    if not isinstance(payload, Mapping) or payload.get("schema") != KNOWN_ISSUES_SCHEMA:
        raise ValueError("known issues file does not match its schema")
    issues = payload.get("issues")
    if not isinstance(issues, list):
        raise ValueError("known issues file does not match its schema")
    return [_validate_issue(item) for item in issues]


def accept_known_issue(
    repo_root: Path, *, fingerprint: str, summary: str, reason: str, owner: str
) -> KnownIssue:
    draft: KnownIssueDraft = {
        "fingerprint": fingerprint,
        "summary": summary,
        "status": "accepted",
        "reason": reason,
        "owner": owner,
    }
    return _issue_to_v1(_upsert(repo_root, draft))


def edit_known_issue(repo_root: Path, issue_id: str, **changes: str) -> KnownIssue:
    issues = _load_normalized_known_issues(repo_root)
    for issue in issues:
        if issue["id"] != issue_id:
            continue
        for field in ("summary", "reason", "owner", "status"):
            value = changes.get(field)
            if value is not None:
                issue[field] = value
        issue["updated_at"] = _now()
        _save(repo_root, issues)
        return _issue_to_v1(issue)
    raise KeyError(f"unknown issue not found: {issue_id}")


def remove_known_issue(repo_root: Path, issue_id: str) -> None:
    issues = [
        issue for issue in _load_normalized_known_issues(repo_root) if issue["id"] != issue_id
    ]
    _save(repo_root, issues)


def known_issue_findings(
    repo_root: Path, findings: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    accepted = {
        issue["fingerprint"]
        for issue in _load_normalized_known_issues(repo_root)
        if issue["status"] == "accepted"
    }
    result: list[dict[str, object]] = []
    for finding in findings:
        fingerprint = finding.get("fingerprint")
        if isinstance(fingerprint, str) and fingerprint in accepted:
            result.append(
                {**finding, "classification": "known-accepted", "status": "known-accepted"}
            )
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
    return {
        "schema": REVIEW_STATE_SCHEMA,
        "cycle_id": cycle_id,
        "active": False,
        "entries": entries,
    }


def _upsert(repo_root: Path, draft: KnownIssueDraft) -> NormalizedKnownIssue:
    issues = _load_normalized_known_issues(repo_root)
    existing = next((item for item in issues if item["fingerprint"] == draft["fingerprint"]), None)
    if existing is None:
        issue: NormalizedKnownIssue = {
            "id": f"issue-{len(issues) + 1}",
            "fingerprint": draft["fingerprint"],
            "summary": draft["summary"],
            "status": draft["status"],
            "reason": draft["reason"],
            "owner": draft["owner"],
            "extensions": {},
        }
        issues.append(issue)
    else:
        existing["summary"] = draft["summary"]
        existing["status"] = draft["status"]
        existing["reason"] = draft["reason"]
        existing["owner"] = draft["owner"]
        existing["updated_at"] = _now()
        issue = existing
    _save(repo_root, issues)
    return issue


def _save(repo_root: Path, issues: Sequence[NormalizedKnownIssue]) -> None:
    path = known_issues_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("known issues file must not be a symlink")
    path.write_text(
        json.dumps(
            {"schema": KNOWN_ISSUES_SCHEMA, "issues": [_issue_to_v1(issue) for issue in issues]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _validate_issue(value: object) -> NormalizedKnownIssue:
    if not isinstance(value, Mapping):
        raise ValueError("known issue requires id, fingerprint, summary, and status")
    issue: NormalizedKnownIssue = {
        "id": _required_issue_text(value, "id"),
        "fingerprint": _required_issue_text(value, "fingerprint"),
        "summary": _required_issue_text(value, "summary"),
        "status": _required_issue_text(value, "status"),
        "extensions": {
            key: item
            for key, item in value.items()
            if key not in {*_REQUIRED_ISSUE_FIELDS, *_OPTIONAL_ISSUE_FIELDS}
        },
    }
    reason = value.get("reason")
    if isinstance(reason, str):
        issue["reason"] = reason
    elif "reason" in value:
        issue["extensions"]["reason"] = reason
    owner = value.get("owner")
    if isinstance(owner, str):
        issue["owner"] = owner
    elif "owner" in value:
        issue["extensions"]["owner"] = owner
    updated_at = value.get("updated_at")
    if isinstance(updated_at, str):
        issue["updated_at"] = updated_at
    elif "updated_at" in value:
        issue["extensions"]["updated_at"] = updated_at
    return issue


def _issue_to_v1(issue: NormalizedKnownIssue) -> KnownIssue:
    payload = dict(issue["extensions"])
    payload.update(
        {
            "id": issue["id"],
            "fingerprint": issue["fingerprint"],
            "summary": issue["summary"],
            "status": issue["status"],
        }
    )
    if "reason" in issue:
        payload["reason"] = issue["reason"]
    if "owner" in issue:
        payload["owner"] = issue["owner"]
    if "updated_at" in issue:
        payload["updated_at"] = issue["updated_at"]
    return cast(KnownIssue, payload)


def _required_issue_text(value: Mapping[str, object], field: str) -> str:
    text = value.get(field)
    if not isinstance(text, str) or not text:
        raise ValueError("known issue requires id, fingerprint, summary, and status")
    return text


def _matches_path(path: str, patterns: Sequence[str]) -> bool:
    return any(
        path == pattern or path.startswith(pattern.rstrip("/") + "/") for pattern in patterns
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
