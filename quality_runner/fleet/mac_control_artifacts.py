from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_safe_directory, write_json, write_text
from quality_runner.fleet.contracts import canonical_json, digest
from quality_runner.fleet.mac_control_contracts import (
    CRITERIA,
    MAC_CONTROL_DEFAULT_ROOT,
    MAC_CONTROL_REPLAY_SCHEMA,
    MAC_CONTROL_REPORT_RELATIVE_PATH,
    MAC_CONTROL_SUMMARY_RELATIVE_PATH,
    MacControlAuditError,
    string_list,
)


def mac_control_replay_payload(
    *, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = resolve_artifact_root(output_dir, audit_id)
    inventory = read_object(artifact_root / "inventory.json")
    report = read_object(artifact_root / "mac-control-ideal-state.json")
    summary = read_object(artifact_root / "summary.json")
    rebuilt = build_summary(
        audit_id=str(inventory.get("audit_id", "")),
        observed_at=str(inventory.get("as_of", "")),
        projects_root=Path(str(inventory.get("projects_root", "."))),
        repositories=objects(report.get("repositories")),
        live=bool(object_value(inventory.get("live_policy")).get("requested", False)),
    )
    deterministic = bool(inventory and report and summary) and canonical_json(
        rebuilt
    ) == canonical_json(summary)
    return {
        "schema": MAC_CONTROL_REPLAY_SCHEMA,
        "status": "passed" if deterministic else "failed",
        "audit_id": inventory.get("audit_id"),
        "deterministic": deterministic,
        "source_report_hash": digest(report),
        "replayed_report_hash": digest(report),
        "source_summary_hash": digest(summary),
        "replayed_summary_hash": digest(rebuilt),
        "repository_count": len(objects(report.get("repositories"))),
        "artifact_root": str(artifact_root),
        "implementation_allowed": False,
    }


def mac_control_report_payload(
    *, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = resolve_artifact_root(output_dir, audit_id)
    report = read_object(artifact_root / "mac-control-ideal-state.json")
    summary = read_object(artifact_root / "summary.json")
    return {
        "schema": "quality-runner-mac-control-report/v1",
        "status": "review_required",
        "audit_id": report.get("run_id"),
        "as_of": report.get("observed_at"),
        "summary": summary,
        "report": report,
        "publication": {"manual_review_required": True, "published": False},
        "artifact_root": str(artifact_root),
        "artifact_paths": {
            "report_json": str(write_json(artifact_root / "report.json", report)),
        },
    }


def mac_control_feed_payload(
    *, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = resolve_artifact_root(output_dir, audit_id)
    replay = mac_control_replay_payload(output_dir=artifact_root)
    if replay.get("status") != "passed":
        raise MacControlAuditError("Mac Control audit replay failed; report was not published")
    report = read_object(artifact_root / "mac-control-ideal-state.json")
    root = (
        MAC_CONTROL_DEFAULT_ROOT
        if output_dir is None
        else publication_root(output_dir, artifact_root)
    )
    current = root.expanduser() / "current"
    prepare_safe_directory(current)
    report_path = write_json(current / MAC_CONTROL_REPORT_RELATIVE_PATH.name, report)
    summary = read_object(artifact_root / "summary.json")
    summary_path = write_json(current / MAC_CONTROL_SUMMARY_RELATIVE_PATH.name, summary)
    return {
        "schema": "quality-runner-mac-control-publication/v1",
        "status": "published",
        "audit_id": report.get("run_id"),
        "artifact_root": str(artifact_root),
        "report_path": str(report_path),
        "summary_path": str(summary_path),
        "provenance_hash": digest(report),
        "replay": replay,
        "implementation_allowed": False,
    }


def build_summary(
    *,
    audit_id: str,
    observed_at: str,
    projects_root: Path,
    repositories: list[dict[str, Any]],
    live: bool,
) -> dict[str, Any]:
    applicability_counts: dict[str, int] = {}
    task_count = 0
    measured_task_count = 0
    attempt_count = 0
    success_count = 0
    implementation_criteria_passed_count = 0
    implementation_criteria_total = 0
    implementation_statuses: list[str] = []
    live_statuses: list[str] = []
    failing_repositories: list[str] = []
    for entry in repositories:
        applicability = str(entry.get("applicability", "unknown"))
        applicability_counts[applicability] = applicability_counts.get(applicability, 0) + 1
        tasks = objects(entry.get("supported_tasks"))
        task_count += len(tasks)
        measured_task_count += sum(1 for task in tasks if _task_is_measured(task))
        attempt_count += sum(
            task.get("attempts", 0)
            for task in tasks
            if isinstance(task.get("attempts"), int) and task.get("attempts", 0) >= 0
        )
        success_count += sum(
            task.get("successes", 0)
            for task in tasks
            if isinstance(task.get("successes"), int) and task.get("successes", 0) >= 0
        )
        implementation = _implementation_lane(entry)
        live_lane = _live_lane(entry)
        implementation_status = implementation["status"]
        implementation_statuses.append(implementation_status)
        live_statuses.append(live_lane["status"])
        implementation_criteria_passed_count += int(implementation["criteria_passed_count"])
        implementation_criteria_total += int(implementation["criteria_total"])
        if (
            applicability == "unknown"
            or implementation_status in {"failed", "blocked"}
            or (
                applicability == "applicable"
                and (implementation["status"] != "passed" or live_lane["status"] != "passed")
            )
        ):
            failing_repositories.append(str(entry.get("repository_id", "unknown")))
    implementation_status = _aggregate_lane_status(
        implementation_statuses, applicability_counts.get("applicable", 0)
    )
    live_status = _aggregate_lane_status(live_statuses, applicability_counts.get("applicable", 0))
    return {
        "schema": "quality-runner-mac-control-summary/v1",
        "audit_id": audit_id,
        "as_of": observed_at,
        "projects_root": str(projects_root),
        "repository_count": len(repositories),
        "applicability_counts": dict(sorted(applicability_counts.items())),
        "task_count": task_count,
        "measured_task_count": measured_task_count,
        "attempt_count": attempt_count,
        "success_count": success_count,
        "implementation_status": implementation_status,
        "implementation_criteria_passed_count": implementation_criteria_passed_count,
        "implementation_criteria_total": implementation_criteria_total,
        "live_status": live_status,
        "live_task_count": task_count,
        "failing_repository_ids": sorted(failing_repositories),
        "live_requested": live,
        "status": (
            "passed"
            if repositories and not failing_repositories and not applicability_counts.get("unknown")
            else "review_required"
        ),
        "implementation_allowed": False,
    }


def _implementation_lane(entry: dict[str, Any]) -> dict[str, Any]:
    applicability = str(entry.get("applicability", "unknown"))
    lane = entry.get("implementation_contract")
    if isinstance(lane, dict):
        if applicability != "applicable":
            return {
                "status": _normalize_lane_status(
                    lane.get("status"), applicability, fallback="failed"
                ),
                "criteria_passed_count": 0,
                "criteria_total": 0,
            }
        criteria_passed_count = lane.get("criteria_passed_count")
        criteria_total = lane.get("criteria_total")
        if not isinstance(criteria_passed_count, int):
            criteria_passed_count = _criteria_passed_count(entry.get("criteria"))
        if not isinstance(criteria_total, int):
            criteria_total = len(CRITERIA)
        return {
            "status": _normalize_lane_status(lane.get("status"), applicability, fallback="failed"),
            "criteria_passed_count": criteria_passed_count,
            "criteria_total": criteria_total,
        }
    criteria_passed_count = _criteria_passed_count(entry.get("criteria"))
    validation_errors = string_list(entry.get("validation_errors"))
    if applicability == "not_applicable":
        status = "not_applicable"
    elif applicability != "applicable":
        status = "blocked"
    elif validation_errors or not entry.get("evidence"):
        status = "failed"
    else:
        status = "passed"
    return {
        "status": status,
        "criteria_passed_count": criteria_passed_count,
        "criteria_total": len(CRITERIA) if applicability == "applicable" else 0,
    }


def _live_lane(entry: dict[str, Any]) -> dict[str, Any]:
    applicability = str(entry.get("applicability", "unknown"))
    lane = entry.get("live_task_evidence")
    if isinstance(lane, dict):
        task_count = lane.get("task_count")
        measured_task_count = lane.get("measured_task_count")
        return {
            "status": _normalize_lane_status(
                lane.get("status"), applicability, fallback="review_required"
            ),
            "task_count": task_count if isinstance(task_count, int) else 0,
            "measured_task_count": (
                measured_task_count if isinstance(measured_task_count, int) else 0
            ),
        }
    tasks = objects(entry.get("supported_tasks"))
    if applicability == "not_applicable":
        status = "not_applicable"
    elif applicability != "applicable":
        status = "blocked"
    elif not tasks:
        status = "review_required"
    elif all(_task_is_measured(task) for task in tasks):
        status = "passed"
    elif any(_task_has_failed_attempt(task) for task in tasks):
        status = "failed"
    else:
        status = "review_required"
    return {
        "status": status,
        "task_count": len(tasks),
        "measured_task_count": sum(1 for task in tasks if _task_is_measured(task)),
    }


def _criteria_passed_count(value: object) -> int:
    return sum(
        1 for criterion in CRITERIA if isinstance(value, dict) and value.get(criterion) is True
    )


def _task_is_measured(task: dict[str, Any]) -> bool:
    attempts = task.get("attempts")
    successes = task.get("successes")
    return (
        isinstance(attempts, int)
        and attempts > 0
        and isinstance(successes, int)
        and successes == attempts
        and bool(task.get("evidence"))
    )


def _task_has_failed_attempt(task: dict[str, Any]) -> bool:
    attempts = task.get("attempts")
    successes = task.get("successes")
    return (
        isinstance(attempts, int)
        and attempts > 0
        and isinstance(successes, int)
        and successes != attempts
    )


def _normalize_lane_status(value: object, applicability: str, *, fallback: str) -> str:
    status = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    if applicability == "not_applicable":
        return status if status in {"failed", "blocked"} else "not_applicable"
    if applicability != "applicable":
        return "blocked"
    return status if status in {"passed", "failed", "blocked", "review_required"} else fallback


def _aggregate_lane_status(statuses: list[str], applicable_count: int) -> str:
    applicable_statuses = [
        status for status in statuses if status not in {"not_applicable", "unknown"}
    ]
    if applicable_count == 0:
        return "not_applicable"
    for status in ("blocked", "failed", "review_required"):
        if status in applicable_statuses:
            return status
    return "passed"


def write_artifacts(
    *,
    artifact_root: Path,
    inventory: dict[str, Any],
    report: dict[str, Any],
    summary: dict[str, Any],
    provider_results: dict[str, dict[str, Any]],
) -> dict[str, str]:
    prepare_safe_directory(artifact_root)
    providers = prepare_safe_directory(artifact_root / "providers")
    write_json(artifact_root / "inventory.json", inventory)
    report_path = write_json(artifact_root / "mac-control-ideal-state.json", report)
    summary_path = write_json(artifact_root / "summary.json", summary)
    write_text(artifact_root / "summary.md", summary_markdown(summary))
    for repo_id, provider in provider_results.items():
        write_json(providers / f"{repo_id}.json", provider)
    replay = {
        "schema": MAC_CONTROL_REPLAY_SCHEMA,
        "audit_id": inventory["audit_id"],
        "inventory_hash": digest(inventory),
        "report_hash": digest(report),
        "summary_hash": digest(summary),
        "provider_hashes": {
            repo_id: digest(value) for repo_id, value in sorted(provider_results.items())
        },
        "provenance_hash": digest({"inventory": inventory, "report": report, "summary": summary}),
    }
    replay_path = write_json(artifact_root / "replay-manifest.json", replay)
    return {
        "inventory_json": str(artifact_root / "inventory.json"),
        "report_json": str(report_path),
        "summary_json": str(summary_path),
        "summary_md": str(artifact_root / "summary.md"),
        "providers_dir": str(providers),
        "replay_manifest": str(replay_path),
    }


def summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Mac Control ideal-state audit",
            "",
            f"- Audit: `{summary.get('audit_id')}`",
            f"- Repositories: {summary.get('repository_count', 0)}",
            (
                f"- Implementation contract: "
                f"{summary.get('implementation_criteria_passed_count', 0)}/"
                f"{summary.get('implementation_criteria_total', 0)} criteria · "
                f"{summary.get('implementation_status', 'review_required')}"
            ),
            (
                f"- Live task evidence: {summary.get('measured_task_count', 0)}/"
                f"{summary.get('task_count', 0)} tasks measured · "
                f"{summary.get('live_status', 'review_required')}"
            ),
            f"- Status: **{summary.get('status', 'review_required')}**",
            "",
        ]
    )


def artifact_root(output_dir: Path | None, audit_id: str) -> Path:
    if output_dir is not None:
        base = output_dir.expanduser().resolve()
        return base if base.name == audit_id else base / audit_id
    return MAC_CONTROL_DEFAULT_ROOT.expanduser().resolve() / "mac-control" / audit_id


def resolve_artifact_root(output_dir: Path | None, audit_id: str | None) -> Path:
    if output_dir is not None:
        candidate = output_dir.expanduser().resolve()
        if (candidate / "inventory.json").is_file():
            return candidate
        if audit_id:
            return candidate / audit_id
        return latest(candidate)
    base = MAC_CONTROL_DEFAULT_ROOT.expanduser().resolve() / "mac-control"
    if audit_id and (base / audit_id).is_dir():
        return base / audit_id
    return latest(base)


def latest(root: Path) -> Path:
    candidates = [
        path for path in root.glob("**/inventory.json") if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        raise FileNotFoundError(f"no Mac Control audit artifacts found under {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime).parent


def publication_root(output_dir: Path, artifact_root_path: Path) -> Path:
    candidate = output_dir.expanduser()
    try:
        if candidate.resolve() == artifact_root_path.resolve():
            return candidate.parent
    except OSError:
        pass
    return candidate


def read_json(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def read_object(path: Path) -> dict[str, Any]:
    return read_json(path) or {}


def objects(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def object_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
