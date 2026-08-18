"""Independent, read-only validation of isolated-change-workflow custody.

Quality Runner deliberately does not verify the workflow's local HMAC key. It
checks the receipt shape and binds the receipt to live Git evidence, while
reporting cryptographic identity as unavailable to this producer.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from quality_runner.fleet.behavior_support import iso_timestamp, string_value, string_values
from quality_runner.fleet.wip import records as read_wip_records
from quality_runner.fleet.workspace_policy import (
    default_workspace_policy_path,
    invalid_workspace_policy_projection,
    is_canonical_workspace,
    load_workspace_policy,
    workspace_policy_projection,
)

CUSTODY_VALIDATION_SCHEMA = "quality-runner-custody-validation/v1"
TASK_SCHEMA = "isolated-change-task/v2"
LEGACY_TASK_SCHEMA = "isolated-change-task/v1"
DEFAULT_STALE_SECONDS = 24 * 60 * 60
DEFAULT_ADOPTABLE_SECONDS = 72 * 60 * 60


def _run(root: Path, *args: str, text: bool = True) -> tuple[Any, str | None]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=text,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace") if not text else result.stderr
        return None, stderr.strip() or f"git {args[0]} failed"
    return result.stdout, None


def _git_text(root: Path, *args: str) -> str | None:
    output, _ = _run(root, *args)
    return output.strip() if isinstance(output, str) and output.strip() else None


def _canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _common_git_dir(root: Path) -> Path:
    value = _git_text(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not value:
        raise ValueError("repository common Git directory is unavailable")
    return _canonical(Path(value))


def _receipt_root(root: Path) -> Path:
    return _common_git_dir(root) / "isolated-change-workflow" / "tasks"


def _worktrees(root: Path) -> list[dict[str, Any]]:
    output = _git_text(root, "worktree", "list", "--porcelain") or ""
    records: list[dict[str, Any]] = []
    for block in output.split("\n\n"):
        record: dict[str, Any] = {}
        for line in block.splitlines():
            if line.startswith("worktree "):
                record["path"] = _canonical(Path(line.removeprefix("worktree ")))
            elif line.startswith("branch "):
                record["branch"] = line.removeprefix("branch ").removeprefix("refs/heads/")
            elif line.startswith("HEAD "):
                record["head_sha"] = line.removeprefix("HEAD ")
        if record.get("path"):
            records.append(record)
    if not records:
        records.append(
            {
                "path": _canonical(root),
                "branch": _git_text(root, "branch", "--show-current"),
                "head_sha": _git_text(root, "rev-parse", "HEAD"),
            }
        )
    return records


def _operations(worktree: Path) -> list[str]:
    git_dir = _git_text(worktree, "rev-parse", "--path-format=absolute", "--git-dir")
    if not git_dir:
        return ["git-dir-unavailable"]
    root = _canonical(Path(git_dir))
    markers = {
        "MERGE_HEAD": root / "MERGE_HEAD",
        "CHERRY_PICK_HEAD": root / "CHERRY_PICK_HEAD",
        "REVERT_HEAD": root / "REVERT_HEAD",
        "rebase-merge": root / "rebase-merge",
        "rebase-apply": root / "rebase-apply",
    }
    return [name for name, marker in markers.items() if marker.exists()]


def _open_files(worktree: Path) -> bool | None:
    try:
        result = subprocess.run(
            ["lsof", "-t", "+D", str(worktree)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0:
        return bool(result.stdout.strip())
    if result.returncode == 1:
        return False
    return None


def _live_state(root: Path, records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        path = record["path"]
        status, _ = _run(path, "status", "--porcelain=v2", "-z", text=False)
        record["clean"] = status == b"" if isinstance(status, bytes) else None
        record["operations"] = _operations(path)
        record["open_files"] = _open_files(path)
        result[str(path)] = record
    return result


def _receipt_integrity(payload: dict[str, Any]) -> str:
    schema = string_value(payload.get("schema_version"))
    integrity = payload.get("integrity")
    algorithm = integrity.get("algorithm") if isinstance(integrity, dict) else None
    digest = integrity.get("digest") if isinstance(integrity, dict) else None
    if schema == TASK_SCHEMA:
        if (
            algorithm == "hmac-sha256"
            and isinstance(digest, str)
            and len(digest) == 64
            and all(character in "0123456789abcdefABCDEF" for character in digest)
        ):
            return "present_unverified"
        return "invalid"
    if schema == LEGACY_TASK_SCHEMA:
        return "legacy_unsigned"
    return "unsupported"


def _receipt_binding(payload: dict[str, Any]) -> str | None:
    worktree = string_value(payload.get("worktree"))
    return str(_canonical(Path(worktree))) if worktree else None


def _receipt_files(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    receipt_root = _receipt_root(root)
    if not receipt_root.is_dir():
        return []
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(receipt_root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            payload = value if isinstance(value, dict) else {}
            if not payload:
                payload = {"schema_version": "invalid", "error": "JSON root must be an object"}
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            payload = {"schema_version": "invalid", "error": str(error)}
        result.append((path, payload))
    return result


def _lease_expiry(payload: dict[str, Any], stale_seconds: int) -> datetime | None:
    explicit = iso_timestamp(payload.get("lease_expires_at"))
    if explicit:
        return explicit
    activity = next(
        (
            iso_timestamp(payload.get(field))
            for field in ("last_activity_at", "last_heartbeat_at", "created_at")
            if iso_timestamp(payload.get(field))
        ),
        None,
    )
    return activity + timedelta(seconds=stale_seconds) if activity else None


def _disposition_action(dispositions: list[str], state: str) -> str:
    if "receipt_malformed" in dispositions:
        return "Preserve the receipt and repair or replace it through the workflow owner."
    if "receipt_integrity_invalid" in dispositions:
        return "Preserve the known receipt and repair its missing or malformed integrity evidence before custody mutation."
    if "receipt_schema_unsupported" in dispositions:
        return "Preserve the lane and upgrade the receipt through the supported workflow."
    if "legacy_unsigned_receipt" in dispositions:
        return (
            "Use the bounded legacy owner-return or adoption review; do not infer custody from age."
        )
    if "competing_custody" in dispositions:
        return "Freeze competing mutation and resolve the exact custody claim before integration."
    if "worktree_not_live" in dispositions:
        return (
            "Verify branch reachability and closure evidence before archiving or deleting anything."
        )
    if "worktree_binding_mismatch" in dispositions or "branch_binding_mismatch" in dispositions:
        return "Preserve the lane and reconcile the receipt against live Git bindings."
    if "head_binding_mismatch" in dispositions:
        return "Re-read the exact branch head and require an owner-bound custody refresh."
    if "live_git_evidence_unavailable" in dispositions:
        return (
            "Retry with complete live Git and process evidence; no adoption decision is authorized."
        )
    if state == "adoptable":
        return "Recheck negative evidence and use an exact-head custody adoption claim."
    if state == "stale":
        return "Preserve the lane through the grace period and recheck live activity."
    if state == "active":
        return "Continue through the owning task and renew the lease."
    if state == "paused":
        return "Wait for the declared return condition or perform reviewed adoption."
    if state == "integrating":
        return "Use the exact-head integration lock and refreshed-target gates."
    if state == "closed":
        return "Verify reachability and retain the closure receipt as evidence."
    return "Preserve the lane and resolve the named custody disposition before mutation."


def _primary_disposition(dispositions: list[str]) -> str:
    return next(
        (item for item in dispositions if item != "receipt_integrity_unverified"),
        dispositions[0] if dispositions else "custody_evidence_insufficient",
    )


def _changed_paths(root: Path, base_sha: str | None, head_sha: str | None) -> list[str]:
    if not base_sha or not head_sha:
        return []
    output, _ = _run(root, "diff", "--name-only", "-z", f"{base_sha}..{head_sha}", text=False)
    if not isinstance(output, bytes):
        return []
    return [item for item in output.decode(errors="replace").split("\0") if item]


def _lane(
    root: Path,
    receipt_path: Path,
    payload: dict[str, Any],
    live_by_path: dict[str, dict[str, Any]],
    duplicate: bool,
    observed_at: datetime,
    stale_seconds: int,
    adoptable_seconds: int,
) -> dict[str, Any]:
    task_id = string_value(payload.get("task_id")) or receipt_path.stem
    branch = string_value(payload.get("branch"))
    worktree = string_value(payload.get("worktree"))
    canonical_worktree = _receipt_binding(payload)
    live = live_by_path.get(canonical_worktree or "")
    recorded_state = string_value(payload.get("state")) or string_value(payload.get("status"))
    integrity = _receipt_integrity(payload)
    state = "unknown"
    blockers: list[str] = []
    evidence = [f"receipt-integrity={integrity}"]
    dispositions: list[str] = []

    if integrity == "present_unverified":
        dispositions.append("receipt_integrity_unverified")
    elif integrity == "legacy_unsigned":
        dispositions.append("legacy_unsigned_receipt")
    elif integrity == "invalid":
        dispositions.append("receipt_integrity_invalid")
    elif string_value(payload.get("schema_version")) == "invalid":
        dispositions.append("receipt_malformed")
    else:
        dispositions.append("receipt_schema_unsupported")

    if recorded_state == "closed" or string_value(payload.get("status")) == "finished":
        state = "closed"
    elif recorded_state == "integrating":
        state = "integrating"
    elif recorded_state == "paused" or string_value(payload.get("status")) == "released":
        state = "paused"
    elif integrity == "legacy_unsigned":
        blockers.append("legacy-receipt-requires-review")
    elif integrity != "present_unverified":
        blockers.append("receipt-schema-or-integrity-unavailable")
    elif duplicate:
        state = "contested"
        blockers.append("multiple-receipts-bind-the-same-worktree")
        dispositions.append("competing_custody")
    elif live is None:
        blockers.append("registered-worktree-is-not-live")
        dispositions.append("worktree_not_live")
    else:
        identity_blockers = 0
        if live.get("branch") != branch:
            blockers.append("branch-mismatch")
            dispositions.append("branch_binding_mismatch")
            identity_blockers += 1
        if live.get("head_sha") != string_value(payload.get("head_sha")):
            blockers.append("head-sha-mismatch")
            dispositions.append("head_binding_mismatch")
            identity_blockers += 1
        operations = live.get("operations", [])
        if operations:
            blockers.extend(f"operation={item}" for item in operations)
            dispositions.append("git_operation_active")
        if live.get("clean") is False:
            blockers.append("worktree-dirty")
            dispositions.append("dirty_worktree")
        elif live.get("clean") is None:
            blockers.append("worktree-status-unavailable")
            dispositions.append("live_git_evidence_unavailable")
        if live.get("open_files") is True:
            blockers.append("open-files-observed")
            dispositions.append("open_files_observed")
        elif live.get("open_files") is None:
            blockers.append("open-file-evidence-unavailable")
            dispositions.append("live_git_evidence_unavailable")

        expiry = _lease_expiry(payload, stale_seconds)
        if not expiry:
            blockers.append("lease-expiry-unavailable")
            dispositions.append("lease_expiry_unavailable")
        elif identity_blockers or live.get("clean") is None or live.get("open_files") is None:
            state = "unknown"
        elif observed_at <= expiry:
            state = "active"
            dispositions.append("lease_current")
        elif observed_at <= expiry + timedelta(seconds=adoptable_seconds):
            state = "stale"
            dispositions.append("lease_expired_grace")
        elif live.get("clean") is True and live.get("open_files") is False and not operations:
            state = "adoptable"
            dispositions.append("adoption_ready")
        else:
            state = "stale"
            dispositions.append("adoption_blocked")

    if state == "unknown" and not blockers:
        blockers.append("insufficient-live-custody-evidence")
        dispositions.append("custody_evidence_insufficient")
    dispositions = list(dict.fromkeys(dispositions))
    evidence.extend(blockers)
    base_sha = string_value(payload.get("base_sha"))
    head_sha = live.get("head_sha") if live else string_value(payload.get("head_sha"))
    changed_paths = _changed_paths(root, base_sha, head_sha)
    if not changed_paths:
        changed_paths = string_values(payload.get("changed_paths"))
    expiry = _lease_expiry(payload, stale_seconds)
    return {
        "task_id": task_id,
        "work_item_id": string_value(payload.get("work_item_id"))
        or string_value(payload.get("task")),
        "branch": branch,
        "worktree": worktree,
        "base_ref": string_value(payload.get("base_ref")),
        "base_sha": base_sha,
        "head_sha": head_sha,
        "recorded_state": recorded_state,
        "state": state,
        "disposition": _primary_disposition(dispositions),
        "dispositions": dispositions,
        "next_action": _disposition_action(dispositions, state),
        "custodian": string_value(payload.get("custodian"))
        or string_value(payload.get("thread_id")),
        "declared_scope": string_values(payload.get("declared_scope")),
        "changed_paths": changed_paths,
        "created_at": string_value(payload.get("created_at")),
        "last_activity_at": string_value(payload.get("last_activity_at"))
        or string_value(payload.get("last_heartbeat_at")),
        "lease_expires_at": expiry.isoformat() if expiry else None,
        "provider_review": string_value(payload.get("provider_review")),
        "workspace_class": "temporary",
        "lease_required": True,
        "blockers": blockers,
        "evidence": evidence,
        "receipt": str(receipt_path),
    }


def _overlap_paths(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    left_paths = set(left.get("changed_paths", [])) | set(left.get("declared_scope", []))
    right_paths = set(right.get("changed_paths", [])) | set(right.get("declared_scope", []))
    return sorted(left_paths & right_paths)


def custody_validation_payload(
    repository_path: Path,
    *,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
    adoptable_seconds: int = DEFAULT_ADOPTABLE_SECONDS,
    as_of: str | None = None,
    workspace_policy_path: Path | None = None,
) -> dict[str, Any]:
    root = _canonical(repository_path)
    if stale_seconds <= 0 or adoptable_seconds <= 0:
        raise ValueError("stale_seconds and adoptable_seconds must be positive")
    observed_at = iso_timestamp(as_of) if as_of else datetime.now(UTC)
    if observed_at is None:
        raise ValueError("as_of must be an ISO-8601 timestamp")
    common_git_dir = _common_git_dir(root)
    records = _worktrees(root)
    live_by_path = _live_state(root, records)
    policy_file = workspace_policy_path or default_workspace_policy_path(root)
    if workspace_policy_path is not None and not policy_file.exists():
        raise ValueError(f"workspace policy does not exist: {policy_file}")
    policy = None
    policy_error: str | None = None
    if policy_file.exists():
        try:
            policy = load_workspace_policy(policy_file)
        except ValueError as error:
            policy_error = str(error)
    receipts = _receipt_files(root)
    binding_counts = Counter(
        binding for _, payload in receipts if (binding := _receipt_binding(payload))
    )
    lanes = [
        _lane(
            root,
            receipt_path,
            payload,
            live_by_path,
            binding_counts.get(_receipt_binding(payload) or "", 0) > 1,
            observed_at,
            stale_seconds,
            adoptable_seconds,
        )
        for receipt_path, payload in receipts
    ]
    overlaps = []
    for index, left in enumerate(lanes):
        for right in lanes[index + 1 :]:
            paths = _overlap_paths(left, right)
            if paths:
                overlaps.append(
                    {
                        "left_task_id": left["task_id"],
                        "right_task_id": right["task_id"],
                        "paths": paths,
                        "status": "historical_overlap"
                        if "closed" in {left["state"], right["state"]}
                        else "integration_serialize",
                    }
                )
    bound_paths = {lane["worktree"] for lane in lanes if lane.get("worktree")}
    active_temporary_lanes = sum(1 for lane in lanes if lane["state"] != "closed")
    workspace_policy = (
        invalid_workspace_policy_projection(
            policy_error,
            policy_path=policy_file,
            active_temporary_lanes=active_temporary_lanes,
        )
        if policy_error
        else workspace_policy_projection(
            policy,
            repository=root,
            observed_workspaces=records,
            active_temporary_lanes=active_temporary_lanes,
            policy_path=policy_file if policy_file.exists() else None,
        )
    )
    unleased_worktrees = [
        str(record["path"])
        for record in records
        if not is_canonical_workspace(record, policy, root)
        and str(record["path"]) not in bound_paths
    ]
    wip_records, wip_errors = read_wip_records(root)
    counts = dict(Counter(lane["state"] for lane in lanes))
    disposition_counts = dict(Counter(lane["disposition"] for lane in lanes))
    if unleased_worktrees:
        wip_errors.append("unleased task worktree observed")
    status = (
        "attention_required"
        if wip_errors
        or workspace_policy["status"] in {"canonical_drift", "invalid"}
        or any(lane["state"] in {"unknown", "contested"} for lane in lanes)
        else "observed"
    )
    if workspace_policy["status"] == "invalid":
        next_safe_step = "Repair the invalid workspace policy before relying on canonical protection or temporary-lane counts."
    elif workspace_policy["status"] == "canonical_drift":
        next_safe_step = "Restore the role-defined canonical workspaces before treating temporary-lane counts as settled."
    elif unleased_worktrees:
        next_safe_step = "Register unleased task worktrees through isolated-change-workflow before editing or integrating."
    elif any(lane["state"] == "adoptable" for lane in lanes):
        next_safe_step = "Recheck negative evidence and use an exact-head custody adoption claim."
    elif status == "attention_required":
        next_safe_step = (
            "Preserve unresolved lanes and obtain the missing receipt, WIP, or live Git evidence."
        )
    else:
        next_safe_step = "Use the workflow integration queue; this validation is read-only and grants no mutation authority."
    return {
        "schema_version": CUSTODY_VALIDATION_SCHEMA,
        "generated_at": observed_at.isoformat(),
        "repository": str(root),
        "common_git_dir": str(common_git_dir),
        "receipt_root": str(_receipt_root(root)),
        "source": "quality_runner_live_git_plus_local_receipts",
        "read_only": True,
        "implementation_allowed": False,
        "mutation_risk": "read-only",
        "status": status,
        "next_safe_step": next_safe_step,
        "lanes": lanes,
        "unleased_worktrees": unleased_worktrees,
        "counts": counts,
        "disposition_counts": disposition_counts,
        "overlaps": overlaps,
        "workspace_policy": workspace_policy,
        "wip": {"records": wip_records, "errors": wip_errors},
        "integrity": {
            "receipt_states": dict(Counter(_receipt_integrity(payload) for _, payload in receipts)),
            "hmac_identity": "not_verified_by_quality_runner",
            "live_git": "observed",
            "provider_review": "not_queried",
        },
        "provenance": {
            "producer": "quality-runner",
            "observed_at": observed_at.isoformat(),
            "stale_seconds": stale_seconds,
            "adoptable_seconds": adoptable_seconds,
        },
    }
