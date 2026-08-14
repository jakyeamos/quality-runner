from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import prepare_safe_directory
from quality_runner.fleet.contracts import digest

FLEET_MATURITY_FEED_SCHEMA = "quality-runner-maturity-feed/v1"
DEFAULT_FLEET_ROOT = Path("~/.quality-runner/fleet-audit")
MATURITY_FEED_RELATIVE_PATH = Path("current") / "maturity.json"
_VALID_AUDIT_STATUSES = {"completed", "complete_with_blockers"}
_FORBIDDEN_KEYS = {
    "prompt",
    "prompts",
    "raw_prompt",
    "raw_prompts",
    "code",
    "diff",
    "diffs",
    "raw_code",
    "raw_diff",
    "raw_diffs",
    "transcript",
    "transcripts",
    "raw_transcript",
    "raw_transcripts",
    "credential",
    "credentials",
    "raw_credential",
    "raw_credentials",
    "stdout",
    "stderr",
    "raw_output",
    "command_output",
}


class MaturityFeedError(ValueError):
    """Raised when a persisted fleet audit cannot produce a safe maturity feed."""


def build_maturity_feed(
    artifact_root: Path,
    *,
    replay: Mapping[str, Any],
    expected_projects_root: Path | None = None,
) -> dict[str, Any]:
    """Build a redacted, Pronto-facing feed from one persisted QR audit."""

    root = artifact_root.expanduser().resolve()
    inventory = _read_object(root / "inventory.json")
    summary = _read_object(root / "summary.json")
    if not inventory or not summary:
        raise MaturityFeedError(f"fleet audit is missing inventory or summary: {root}")
    audit_id = _required_string(inventory, "audit_id")
    if _required_string(summary, "audit_id") != audit_id:
        raise MaturityFeedError("inventory and summary audit IDs do not match")
    if replay.get("status") != "passed" or replay.get("deterministic") is not True:
        raise MaturityFeedError("fleet audit replay must pass before maturity publication")
    if str(summary.get("status")) not in _VALID_AUDIT_STATUSES:
        raise MaturityFeedError("fleet audit status is not publishable")

    projects_root = _required_string(inventory, "projects_root")
    if expected_projects_root is not None:
        expected = str(expected_projects_root.expanduser().resolve())
        if projects_root != expected:
            raise MaturityFeedError(
                f"fleet audit projects root does not match the production scope: {projects_root}"
            )
    scope = _required_string(inventory, "scope")
    if "all repository identities" not in scope:
        raise MaturityFeedError("maturity feed requires a fleet-wide audit scope")

    repositories = _objects(inventory.get("repositories"))
    if not repositories or int(summary.get("repository_count", 0)) != len(repositories):
        raise MaturityFeedError("fleet audit repository coverage is incomplete")
    if int(summary.get("static_completed", 0)) != len(repositories):
        raise MaturityFeedError("fleet audit static coverage is incomplete")

    projections = [
        _repository_projection(
            repository,
            _read_finding(root / "findings" / f"{_required_string(repository, 'repo_id')}.json"),
        )
        for repository in repositories
    ]
    projections.sort(key=lambda item: str(item["repo_id"]))

    source = {
        "audit_id": audit_id,
        "as_of": _required_string(summary, "as_of"),
        "projects_root": projects_root,
        "artifact_schema": _required_string(summary, "schema"),
        "summary_hash": digest(summary),
    }
    feed: dict[str, Any] = {
        "schema": FLEET_MATURITY_FEED_SCHEMA,
        "status": str(summary["status"]),
        "feed_timestamp": str(summary["as_of"]),
        "generated_at": str(summary["as_of"]),
        "source": source,
        "replay": {
            "status": "passed",
            "deterministic": True,
            "source_summary_hash": replay.get("source_summary_hash"),
            "replayed_summary_hash": replay.get("replayed_summary_hash"),
        },
        "repository_count": int(summary["repository_count"]),
        "checkout_count": int(summary.get("checkout_count", 0)),
        "mean_maturity": summary.get("mean_maturity"),
        "dimension_means": _number_mapping(summary.get("dimension_means")),
        "maturity_certified_repository_count": sum(
            1 for item in projections if item.get("maturity_status") == "certified"
        ),
        "maturity_status_counts": _count_values(projections, "maturity_status", fallback="unknown"),
        "finding_counts": _number_mapping(summary.get("finding_counts")),
        "unresolved_measurement_gaps": _string_list(summary.get("unresolved_measurement_gaps")),
        "repositories": projections,
        "privacy": {
            "private_local_feed": True,
            "raw_paths": False,
            "raw_prompts": False,
            "raw_code": False,
            "raw_diffs": False,
            "raw_transcripts": False,
            "credentials": False,
        },
    }
    feed["provenance_hash"] = _feed_hash(feed)
    validate_maturity_feed(feed)
    return feed


def publish_maturity_feed(feed: Mapping[str, Any], fleet_root: Path) -> Path:
    """Atomically publish one validated feed at the stable QR path."""

    payload = dict(feed)
    validate_maturity_feed(payload)
    root = fleet_root.expanduser()
    current = root / "current"
    _prepare_directory(current)
    target = current / MATURITY_FEED_RELATIVE_PATH.name
    if target.is_symlink():
        raise MaturityFeedError(f"maturity feed target must not be a symlink: {target}")

    content = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".maturity-", suffix=".tmp", dir=str(current)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def read_maturity_feed(path: Path) -> dict[str, Any]:
    """Read and validate a stable QR maturity feed."""

    payload = _read_object(path)
    if not payload:
        raise MaturityFeedError(f"maturity feed is missing or invalid: {path}")
    validate_maturity_feed(payload)
    return payload


def validate_maturity_feed(feed: Mapping[str, Any]) -> None:
    """Validate the feed contract and reject private evidence leakage."""

    if feed.get("schema") != FLEET_MATURITY_FEED_SCHEMA:
        raise MaturityFeedError("unsupported maturity feed schema")
    if str(feed.get("status")) not in _VALID_AUDIT_STATUSES:
        raise MaturityFeedError("maturity feed status is not publishable")
    source = _object(feed.get("source"))
    if (
        not _required_string(source, "audit_id")
        or not _required_string(source, "as_of")
        or not _required_string(source, "projects_root")
    ):
        raise MaturityFeedError("maturity feed source is incomplete")
    if not _required_string(feed, "feed_timestamp"):
        raise MaturityFeedError("maturity feed timestamp is missing")
    replay = _object(feed.get("replay"))
    if replay.get("status") != "passed" or replay.get("deterministic") is not True:
        raise MaturityFeedError("maturity feed replay evidence is incomplete")
    summary_hash = _required_string(source, "summary_hash")
    if (
        replay.get("source_summary_hash") != summary_hash
        or replay.get("replayed_summary_hash") != summary_hash
    ):
        raise MaturityFeedError("maturity feed replay hashes do not match its source summary")
    repositories = _objects(feed.get("repositories"))
    if int(feed.get("repository_count", 0)) != len(repositories) or not repositories:
        raise MaturityFeedError("maturity feed repository count is invalid")
    repository_ids = [_required_string(repository, "repo_id") for repository in repositories]
    if len(set(repository_ids)) != len(repository_ids):
        raise MaturityFeedError("maturity feed repository IDs must be unique")
    if not isinstance(feed.get("provenance_hash"), str):
        raise MaturityFeedError("maturity feed provenance hash is missing")
    if _feed_hash(feed) != feed.get("provenance_hash"):
        raise MaturityFeedError("maturity feed provenance hash does not match its content")
    privacy = _object(feed.get("privacy"))
    required_privacy_flags = (
        "raw_paths",
        "raw_prompts",
        "raw_code",
        "raw_diffs",
        "raw_transcripts",
        "credentials",
    )
    if privacy.get("private_local_feed") is not True or any(
        privacy.get(key) is not False for key in required_privacy_flags
    ):
        raise MaturityFeedError("maturity feed privacy contract is incomplete")
    _assert_safe_tree(feed)


def _repository_projection(repository: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    repo_id = _required_string(repository, "repo_id")
    finding_repo_id = _required_string(finding, "repo_id")
    if repo_id != finding_repo_id:
        raise MaturityFeedError(f"repository and finding IDs do not match: {repo_id}")
    primary_path = _required_string(repository, "primary_path")
    target = _object(repository.get("target_branch"))
    findings = _objects(finding.get("findings"))
    dimension_scores: dict[str, float | None] = {}
    dimension_gaps: list[dict[str, Any]] = []
    applicable_scores: list[float] = []
    statuses: list[str] = []
    blockers = 0
    for item in findings:
        dimension = _required_string(item, "dimension")
        status = str(item.get("status", "unknown"))
        statuses.append(status)
        raw_score = item.get("score")
        score = float(raw_score) if isinstance(raw_score, (int, float)) else None
        dimension_scores[dimension] = score if status != "not_applicable" else None
        if status != "not_applicable" and score is not None:
            applicable_scores.append(score)
        if status != "not_applicable" and (score is None or score < 4):
            dimension_gaps.append(
                {
                    "dimension": dimension,
                    "status": status,
                    "score": score,
                    "message": str(item.get("message", "Evidence is incomplete."))[:240],
                }
            )
        if status == "blocked" or item.get("severity") == "blocker" or item.get("priority") == "P0":
            blockers += 1

    dynamic = _object(finding.get("dynamic"))
    dynamic_status = str(dynamic.get("status", "not_selected"))
    if blockers or dynamic_status in {"failed", "timeout", "blocked"}:
        quality_status = "blocked"
    elif any(status in {"unknown", "stale"} for status in statuses):
        quality_status = "unknown"
    elif (
        dynamic_status in {"passed", "reused"}
        and statuses
        and all(status in {"validated", "maintained", "not_applicable"} for status in statuses)
    ):
        quality_status = "healthy"
    else:
        quality_status = "attention"

    maturity_score = (
        round(sum(applicable_scores) / len(applicable_scores), 3) if applicable_scores else None
    )
    target_status = str(target.get("status", "unknown"))
    certified = bool(
        target_status == "ready"
        and applicable_scores
        and all(score == 4 for score in applicable_scores)
        and dynamic_status in {"passed", "reused"}
    )
    maturity_status = (
        "certified" if certified else "not_certified" if maturity_score is not None else "unknown"
    )
    return {
        "repo_id": repo_id,
        "display_name": Path(primary_path).name,
        "local_identity": {"primary_path": primary_path},
        "target_branch": str(target.get("branch")) if target.get("branch") else None,
        "target_branch_status": target_status,
        "target_head": target.get("head"),
        "maturity_score": maturity_score,
        "maturity_status": maturity_status,
        "dimension_scores": dict(sorted(dimension_scores.items())),
        "dimension_gaps": sorted(dimension_gaps, key=lambda item: item["dimension"])[:16],
        "quality_status": quality_status,
        "finding_count": len(findings),
        "blocker_count": blockers,
        "dynamic_status": dynamic_status,
    }


def _feed_hash(feed: Mapping[str, Any]) -> str:
    return digest({key: value for key, value in feed.items() if key != "provenance_hash"})


def _prepare_directory(path: Path) -> None:
    try:
        prepare_safe_directory(path)
    except (OSError, ValueError) as error:
        raise MaturityFeedError(f"maturity feed directory is unsafe: {path}") from error


def _read_finding(path: Path) -> dict[str, Any]:
    finding = _read_object(path)
    if not finding:
        raise MaturityFeedError(f"fleet audit finding is missing or invalid: {path}")
    return finding


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise MaturityFeedError(f"maturity feed field is missing: {key}")
    return item


def _object(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in cast(list[Any], value) if isinstance(item, dict)]


def _number_mapping(value: object) -> dict[str, int | float | None]:
    if not isinstance(value, dict):
        return {}
    typed_value = cast(dict[str, Any], value)
    return {
        str(key): cast(int | float | None, child)
        for key, child in typed_value.items()
        if child is None or isinstance(child, (int, float))
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in cast(list[Any], value) if isinstance(item, str))


def _count_values(values: list[dict[str, Any]], key: str, *, fallback: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        label = str(value.get(key) or fallback)
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _assert_safe_tree(
    value: object, *, key: str | None = None, parent_key: str | None = None
) -> None:
    privacy_flag = parent_key == "privacy" and key in {
        "raw_paths",
        "raw_prompts",
        "raw_code",
        "raw_diffs",
        "raw_transcripts",
        "credentials",
    }
    if key is not None and key.casefold() in _FORBIDDEN_KEYS and not privacy_flag:
        raise MaturityFeedError(f"maturity feed contains forbidden evidence field: {key}")
    if isinstance(value, dict):
        typed_value = cast(dict[str, Any], value)
        for child_key, child_value in typed_value.items():
            _assert_safe_tree(child_value, key=str(child_key), parent_key=key)
    elif isinstance(value, list):
        for child in cast(list[Any], value):
            _assert_safe_tree(child, parent_key=key)
