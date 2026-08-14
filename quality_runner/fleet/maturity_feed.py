from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import prepare_safe_directory
from quality_runner.fleet.contracts import digest
from quality_runner.fleet.maturity_projection import (
    MaturityProjectionError,
)
from quality_runner.fleet.maturity_projection import (
    repository_projection as build_repository_projection,
)
from quality_runner.fleet.quality_outcomes import (
    QUALITY_OUTCOME_TAXONOMY,
    quality_outcome_counts,
)
from quality_runner.fleet.repository_maturity import (
    PILLAR_DEFINITIONS,
    pillar_means,
)

FLEET_MATURITY_FEED_SCHEMA = "quality-runner-maturity-feed/v2"
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
    standard = inventory.get("standard")
    if isinstance(standard, str) and standard.strip():
        raise MaturityFeedError(
            "standard-scoped fleet audits do not publish the canonical maturity feed; "
            "inspect standard-report.json instead"
        )
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
    maturity_models = [_object(projection.get("repository_maturity")) for projection in projections]
    holistic_scores = [
        float(model["score"])
        for model in maturity_models
        if isinstance(model.get("score"), (int, float))
    ]
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
        "mean_maturity": (
            round(sum(holistic_scores) / len(holistic_scores), 3) if holistic_scores else None
        ),
        "source_dimension_mean": summary.get("mean_maturity"),
        "dimension_means": _number_mapping(summary.get("dimension_means")),
        "pillar_means": pillar_means(maturity_models),
        "maturity_certified_repository_count": sum(
            1 for item in projections if item.get("maturity_status") == "certified"
        ),
        "maturity_status_counts": _count_values(projections, "maturity_status", fallback="unknown"),
        "quality_outcome_counts": quality_outcome_counts(projections),
        "quality_outcome_taxonomy": QUALITY_OUTCOME_TAXONOMY,
        "behavior_assurance": _behavior_assurance_summary(projections),
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
    for repository in repositories:
        _validate_repository_maturity(repository)
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


def _validate_repository_maturity(repository: Mapping[str, Any]) -> None:
    model = _object(repository.get("repository_maturity"))
    if model.get("schema") != "quality-runner-repository-maturity/v2":
        raise MaturityFeedError("repository maturity model is missing or unsupported")
    pillars = _objects(model.get("pillars"))
    expected_ids = [str(definition["id"]) for definition in PILLAR_DEFINITIONS]
    pillar_ids = [str(pillar.get("id", "")) for pillar in pillars]
    if pillar_ids != expected_ids:
        raise MaturityFeedError("repository maturity pillars are incomplete or out of order")
    if round(sum(float(pillar.get("weight", 0)) for pillar in pillars), 6) != 1.0:
        raise MaturityFeedError("repository maturity pillar weights must sum to one")
    for definition, pillar in zip(PILLAR_DEFINITIONS, pillars, strict=True):
        score = pillar.get("score")
        if score is not None and (
            not isinstance(score, (int, float)) or not 0 <= float(score) <= 4
        ):
            raise MaturityFeedError("repository maturity pillar score is invalid")
        capabilities = _objects(pillar.get("capabilities"))
        expected_capability_ids = list(definition["capabilities"])
        if [str(item.get("id", "")) for item in capabilities] != expected_capability_ids:
            raise MaturityFeedError(
                "repository maturity capabilities are incomplete or out of order"
            )
        for capability in capabilities:
            if capability.get("applicability") not in {
                "applicable",
                "not_applicable",
                "unknown",
            }:
                raise MaturityFeedError("repository maturity capability applicability is invalid")
            capability_score = capability.get("score")
            if capability_score is not None and (
                not isinstance(capability_score, (int, float))
                or not 0 <= float(capability_score) <= 4
            ):
                raise MaturityFeedError("repository maturity capability score is invalid")
            if not isinstance(capability.get("dimension_scores"), dict) or not isinstance(
                capability.get("producer_dimensions"), list
            ):
                raise MaturityFeedError("repository maturity capability evidence is invalid")
        for coverage_key in ("capability_coverage", "fresh_capability_coverage"):
            coverage = pillar.get(coverage_key)
            if not isinstance(coverage, (int, float)) or not 0 <= float(coverage) <= 1:
                raise MaturityFeedError("repository maturity capability coverage is invalid")
    score = model.get("score")
    if score is not None and (not isinstance(score, (int, float)) or not 0 <= float(score) <= 4):
        raise MaturityFeedError("repository maturity score is invalid")
    if repository.get("maturity_score") != score:
        raise MaturityFeedError("repository maturity projection score does not match its model")
    critical_cap = _object(model.get("critical_cap"))
    if critical_cap.get("applied") is True:
        maximum = critical_cap.get("maximum_score")
        if not isinstance(maximum, (int, float)) or score is None or float(score) > float(maximum):
            raise MaturityFeedError("repository maturity critical cap is invalid")


def _repository_projection(repository: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    try:
        return build_repository_projection(repository, finding)
    except MaturityProjectionError as error:
        raise MaturityFeedError(str(error)) from error


def _behavior_assurance_summary(projections: list[dict[str, Any]]) -> dict[str, Any]:
    assessments = [_object(item.get("behavior_assurance")) for item in projections]
    status_counts = _count_values(assessments, "result_status", fallback="unknown")
    applicability_counts = _count_values(assessments, "applicability", fallback="unknown")
    ready_count = sum(1 for item in assessments if item.get("release_ready") is True)
    required_count = sum(int(item.get("required_scenario_count", 0)) for item in assessments)
    passed_count = sum(int(item.get("passed_scenario_count", 0)) for item in assessments)
    gap_count = sum(len(_objects(item.get("gaps"))) for item in assessments)
    coverages = [_object(item.get("coverage")) for item in assessments]
    coverage = {
        key: sum(int(item.get(key, 0)) for item in coverages)
        for key in ("total", "profiled", "verified", "stale", "failed", "blocked", "unknown")
    }
    contract_schema_counts = _count_values(assessments, "contract_schema", fallback="missing")
    profile_status_counts = _count_values(assessments, "edge_profile_status", fallback="missing")
    state_counts = _count_values(assessments, "state", fallback="unknown")
    return {
        "schema": "quality-runner-behavior-assurance-summary/v2",
        "status": "ready" if ready_count == len(assessments) else "gaps_present",
        "repository_count": len(assessments),
        "ready_repository_count": ready_count,
        "applicability_counts": applicability_counts,
        "result_status_counts": status_counts,
        "contract_schema_counts": contract_schema_counts,
        "edge_profile_status_counts": profile_status_counts,
        "state_counts": state_counts,
        "required_scenario_count": required_count,
        "passed_scenario_count": passed_count,
        "gap_count": gap_count,
        "coverage": coverage,
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
    return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)]


def _number_mapping(value: object) -> dict[str, int | float | None]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): cast(int | float | None, child)
        for key, child in value.items()
        if child is None or isinstance(child, (int, float))
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value if isinstance(item, str))


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
        for child_key, child_value in value.items():
            _assert_safe_tree(child_value, key=str(child_key), parent_key=key)
    elif isinstance(value, list):
        for child in value:
            _assert_safe_tree(child, parent_key=key)
