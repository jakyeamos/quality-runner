from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.artifacts import (
    artifact_file,
    artifact_text_file,
    existing_artifact_dir,
    safe_child_file,
    validate_run_id,
    write_json,
    write_text,
)
from quality_runner.schema_constants import REVIEW_DELTA_SCHEMA

_GIT_OBJECT_ID_PATTERN = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")


def build_review_delta(
    *,
    repo_root: Path,
    run_id: str,
    cycle_id: str,
    iteration: int,
    intent: dict[str, Any],
    baseline_run_id: str | None = None,
    changed_paths: list[str] | None = None,
) -> dict[str, Any]:
    _validate_review_identity(repo_root, cycle_id, iteration)
    current_run_dir = existing_artifact_dir(repo_root, run_id)
    current_findings = _findings(safe_child_file(current_run_dir, "quality-audit.json"))
    baseline_findings = (
        _findings(
            safe_child_file(existing_artifact_dir(repo_root, baseline_run_id), "quality-audit.json")
        )
        if baseline_run_id is not None
        else []
    )
    scope_paths = sorted(set(changed_paths or git_changed_paths(repo_root, baseline_run_id)))
    current_by_fingerprint = _index_findings(current_findings)
    baseline_by_fingerprint = _index_findings(baseline_findings)
    in_scope_current, out_of_scope_current = _partition_findings(current_findings, scope_paths)
    in_scope_baseline, _ = _partition_findings(baseline_findings, scope_paths)
    current_scope = {item["fingerprint"] for item in in_scope_current}
    baseline_scope = {item["fingerprint"] for item in in_scope_baseline}
    verification = _verification_state(current_run_dir)
    blocked = verification["blocked"]
    unresolved = sorted(current_scope)
    clean = bool(scope_paths) and not unresolved and not blocked
    payload: dict[str, Any] = {
        "schema": REVIEW_DELTA_SCHEMA,
        "cycle_id": cycle_id,
        "iteration": iteration,
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "task": {
            "intent_hash": _hash_payload(intent),
            "goal": intent.get("goal"),
        },
        "scope": {
            "changed_paths": scope_paths,
            "scope_available": bool(scope_paths),
            "scope_basis": "baseline-and-working-tree-diff",
        },
        "findings": {
            "new": [
                _finding_ref(current_by_fingerprint[key])
                for key in sorted(current_scope - baseline_scope)
            ],
            "persisted": [
                _finding_ref(current_by_fingerprint[key])
                for key in sorted(current_scope & baseline_scope)
            ],
            "resolved": [
                _finding_ref(baseline_by_fingerprint[key])
                for key in sorted(baseline_scope - current_scope)
            ],
            "out_of_scope": [
                _finding_ref(item)
                for item in sorted(out_of_scope_current, key=lambda value: value["fingerprint"])
            ],
        },
        "verification": verification,
        "evidence_limitations": _evidence_limitations(scope_paths, current_findings),
        "clean": clean,
        "continue": not clean,
        "stop_reason": _stop_reason(clean=clean, blocked=blocked, scope_paths=scope_paths),
        "source_artifacts": {
            "quality_audit_json": str(safe_child_file(current_run_dir, "quality-audit.json")),
            "remediation_plan_json": str(safe_child_file(current_run_dir, "remediation-plan.json")),
            "agent_handoff_json": str(safe_child_file(current_run_dir, "agent-handoff.json")),
            "resolution_ledger_json": str(
                safe_child_file(current_run_dir, "resolution-ledger.json")
            ),
        },
    }
    return payload


def persist_review_delta(
    *, repo_root: Path, run_id: str, payload: dict[str, Any]
) -> dict[str, str]:
    json_path = write_json(artifact_file(repo_root, run_id, "review-delta.json"), payload)
    markdown_path = write_text(
        artifact_file(repo_root, run_id, "review-delta.md"),
        render_review_delta_markdown(payload),
    )
    return {"review_delta_json": str(json_path), "review_delta_md": str(markdown_path)}


def render_review_delta_markdown(payload: dict[str, Any]) -> str:
    findings = payload.get("findings", {})
    if not isinstance(findings, dict):
        findings = {}
    lines = [
        "# Quality Runner Review Delta",
        "",
        f"- Cycle: `{payload.get('cycle_id')}`",
        f"- Iteration: `{payload.get('iteration')}`",
        f"- Run: `{payload.get('run_id')}`",
        f"- Baseline: `{payload.get('baseline_run_id') or 'none'}`",
        f"- Recommendation: **{'stop' if payload.get('clean') else 'continue'}**",
        "",
        f"## Stop reason\n\n{payload.get('stop_reason', 'unknown')}",
        "",
        "## Task-scoped findings",
        "",
    ]
    for key, title in (("new", "New"), ("persisted", "Persisted"), ("resolved", "Resolved")):
        items = findings.get(key, [])
        lines.append(f"### {title} ({len(items) if isinstance(items, list) else 0})")
        lines.append("")
        if isinstance(items, list) and items:
            lines.extend(
                f"- `{item.get('fingerprint')}`: {item.get('summary', 'No summary')}"
                for item in items
                if isinstance(item, dict)
            )
        else:
            lines.append("- None")
        lines.append("")
    out_of_scope = findings.get("out_of_scope", [])
    lines.extend(
        [
            "## Out of scope",
            "",
            f"{len(out_of_scope) if isinstance(out_of_scope, list) else 0} finding(s) retained for visibility; they do not block this task.",
            "",
        ]
    )
    verification = payload.get("verification", {})
    lines.extend(
        [
            "## Verification",
            "",
            f"- Status: `{verification.get('status', 'unknown') if isinstance(verification, dict) else 'unknown'}`",
            f"- Blocked: `{verification.get('blocked', True) if isinstance(verification, dict) else True}`",
            "",
        ]
    )
    return "\n".join(lines)


def git_changed_paths(repo_root: Path, baseline_run_id: str | None = None) -> list[str]:
    root = repo_root.expanduser().resolve()
    if not (root / ".git").exists():
        return []
    paths: set[str] = set()
    baseline_sha = _baseline_head_sha(root, baseline_run_id)
    if baseline_sha:
        paths.update(_git_names(root, "diff", "--name-only", baseline_sha, "HEAD", "--"))
    paths.update(_git_names(root, "diff", "--name-only", "HEAD", "--"))
    paths.update(_git_names(root, "ls-files", "--others", "--exclude-standard"))
    return sorted(path for path in paths if path and not path.startswith(".quality-runner/"))


def _validate_review_identity(repo_root: Path, cycle_id: str, iteration: int) -> None:
    validate_run_id(cycle_id)
    if iteration < 1:
        raise ValueError("review iteration must be at least 1")


def _findings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    findings = payload.get("findings", []) if isinstance(payload, dict) else []
    return [_normalize_finding(item) for item in findings if isinstance(item, dict)]


def _normalize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    stable = {
        key: finding.get(key)
        for key in ("id", "rule_id", "category", "file", "path", "summary", "evidence")
        if finding.get(key) is not None
    }
    normalized = dict(finding)
    normalized["fingerprint"] = str(finding.get("fingerprint") or _hash_payload(stable))
    return normalized


def _index_findings(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["fingerprint"]): item for item in findings}


def _partition_findings(
    findings: list[dict[str, Any]], scope_paths: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not scope_paths:
        return [], list(findings)
    scoped: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    for finding in findings:
        path = _finding_path(finding)
        if path and any(
            path == candidate or path.startswith(f"{candidate}/") for candidate in scope_paths
        ):
            scoped.append(finding)
        else:
            outside.append(finding)
    return scoped, outside


def _finding_path(finding: dict[str, Any]) -> str | None:
    for key in ("file", "path", "location"):
        value = finding.get(key)
        if isinstance(value, str) and value and not value.startswith("/"):
            return value.split(":", 1)[0]
    return None


def _finding_ref(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": finding["fingerprint"],
        "id": finding.get("id"),
        "rule_id": finding.get("rule_id"),
        "file": _finding_path(finding),
        "severity": finding.get("severity"),
        "category": finding.get("category"),
        "summary": finding.get("summary") or finding.get("message") or "Quality Runner finding",
    }


def _verification_state(run_dir: Path) -> dict[str, Any]:
    path = safe_child_file(run_dir, "gate-verification.json")
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    status = payload.get("status", "unavailable") if isinstance(payload, dict) else "unavailable"
    blockers = payload.get("blockers", []) if isinstance(payload, dict) else []
    failure_type = payload.get("failure_type") if isinstance(payload, dict) else None
    blocked = status not in {"passed", "clean"} or bool(blockers) or bool(failure_type)
    return {
        "status": status,
        "blocked": blocked,
        "failure_type": failure_type,
        "blockers": blockers if isinstance(blockers, list) else [],
    }


def _evidence_limitations(scope_paths: list[str], findings: list[dict[str, Any]]) -> list[str]:
    limitations: list[str] = []
    if not scope_paths:
        limitations.append(
            "No changed paths were available; findings were not treated as task-scoped."
        )
    if not findings:
        limitations.append("No quality-audit findings were available for this run.")
    return limitations


def _stop_reason(*, clean: bool, blocked: bool, scope_paths: list[str]) -> str:
    if blocked:
        return "verification-blocked"
    if not scope_paths:
        return "no-task-scope-evidence"
    if clean:
        return "no-task-scoped-findings"
    return "task-scoped-findings-remain"


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _baseline_head_sha(repo_root: Path, baseline_run_id: str | None) -> str | None:
    if baseline_run_id is None:
        return None
    try:
        path = artifact_text_file(repo_root, baseline_run_id, "run-manifest.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    git = payload.get("git", {}) if isinstance(payload, dict) else {}
    head_sha = git.get("head_sha") if isinstance(git, dict) else None
    if not isinstance(head_sha, str) or not _GIT_OBJECT_ID_PATTERN.fullmatch(head_sha):
        return None
    return head_sha


def _git_names(repo_root: Path, *args: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
