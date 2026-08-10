from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_safe_directory, write_json, write_text
from quality_runner.fleet.agent_usability_scoring import applicable_agent_usability_scores
from quality_runner.fleet.contracts import (
    DIMENSIONS,
    FLEET_AUDIT_SCHEMA,
    FLEET_FINDING_SCHEMA,
    FLEET_INVENTORY_SCHEMA,
    FLEET_REPLAY_SCHEMA,
    FLEET_REPORT_SCHEMA,
    canonical_json,
    digest,
    parse_as_of,
    public_projection,
    stable_id,
)
from quality_runner.fleet.discovery import (
    discover_repositories,
    repository_record_for_root,
    resolve_target_branch,
)
from quality_runner.fleet.dynamic import (
    apply_dynamic_quality_evidence,
)
from quality_runner.fleet.dynamic import (
    dynamic_result as build_dynamic_result,
)
from quality_runner.fleet.legibility import audit_repository
from quality_runner.fleet.reporting import plan_markdown, report_markdown, summary_markdown
from quality_runner.fleet.static_scan import static_scan_repository as _static_scan_repository

DEFAULT_FLEET_ROOT = Path("~/.quality-runner/fleet-audit")
DEFAULT_DYNAMIC_MAX_AGE_DAYS = 30
DEFAULT_DYNAMIC_TIMEOUT_SECONDS = 120


def fleet_audit_payload(
    *,
    projects_root: Path,
    output_dir: Path | None = None,
    dynamic: bool = False,
    changed_only: bool = True,
    dynamic_max_age_days: int = DEFAULT_DYNAMIC_MAX_AGE_DAYS,
    timeout_seconds: int = DEFAULT_DYNAMIC_TIMEOUT_SECONDS,
    target_overrides: dict[str, str] | None = None,
    repository_paths: Sequence[Path] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    resolved_as_of = parse_as_of(as_of)
    root = projects_root.expanduser().resolve()
    overrides = target_overrides or {}
    audit_id = stable_id(
        "audit",
        str(root),
        resolved_as_of,
        dynamic,
        changed_only,
        dynamic_max_age_days,
        timeout_seconds,
        sorted(overrides.items()),
        sorted(str(path.expanduser().resolve()) for path in repository_paths or []),
    )
    artifact_root = _artifact_root(output_dir, audit_id)
    repositories = _repositories_for_scope(root, repository_paths)
    results: list[dict[str, Any]] = []
    for repository in repositories:
        target_override = overrides.get(str(repository["repo_id"]))
        target = resolve_target_branch(repository, override=target_override)
        repository_with_target = {**repository, "target_branch": target}
        static_repository = _static_scan_repository(repository_with_target)
        result = audit_repository(
            repository=static_repository,
            as_of=resolved_as_of,
            run_id=f"{audit_id}-{repository['repo_id']}",
        )
        # Keep the canonical repository identity (including its primary path)
        # in persisted artifacts. The ready target checkout is only the static
        # evidence source; it must not replace the identity or dirty-worktree
        # provenance used by Pronto and dynamic verification.
        result["repository"] = repository_with_target
        dynamic_evidence = build_dynamic_result(
            repository=result["repository"],
            finding=result,
            audit_id=audit_id,
            artifact_root=artifact_root,
            enabled=dynamic,
            changed_only=changed_only,
            max_age_days=dynamic_max_age_days,
            timeout_seconds=timeout_seconds,
            as_of=resolved_as_of,
        )
        result["dynamic"] = dynamic_evidence
        apply_dynamic_quality_evidence(result)
        results.append(result)

    summary = _build_summary(
        audit_id=audit_id,
        as_of=resolved_as_of,
        repositories=results,
        dynamic=dynamic,
        changed_only=changed_only,
    )
    inventory = {
        "schema": FLEET_INVENTORY_SCHEMA,
        "audit_id": audit_id,
        "as_of": resolved_as_of,
        "projects_root": str(root),
        "scope": (
            "explicit repository paths under the bounded projects root"
            if repository_paths is not None
            else "all repository identities under the bounded projects root"
        ),
        "dynamic_policy": {
            "enabled": dynamic,
            "changed_only": changed_only,
            "max_age_days": dynamic_max_age_days,
            "timeout_seconds": timeout_seconds,
        },
        "repositories": [item["repository"] for item in results],
        "provenance_hash": digest(
            {
                "audit_id": audit_id,
                "as_of": resolved_as_of,
                "repositories": [item["repository"] for item in results],
            }
        ),
    }
    artifact_paths = _write_audit_artifacts(
        artifact_root=artifact_root,
        inventory=inventory,
        results=results,
        summary=summary,
    )
    maturity_feed = {
        "status": "not_requested",
        "reason": "immutable snapshot created; run fleet audit feed to update the stable feed",
    }
    return {
        "schema": FLEET_AUDIT_SCHEMA,
        "status": "completed" if results else "blocked",
        "audit_id": audit_id,
        "as_of": resolved_as_of,
        "repository_count": len(results),
        "artifact_root": str(artifact_root),
        "artifact_paths": artifact_paths,
        "summary": summary,
        "maturity_feed": maturity_feed,
        "public_projection": public_projection(summary),
        "implementation_allowed": False,
    }


def _repositories_for_scope(
    projects_root: Path,
    repository_paths: Sequence[Path] | None,
) -> list[dict[str, Any]]:
    if repository_paths is None:
        return discover_repositories(projects_root)
    root = projects_root.expanduser().resolve()
    records: dict[str, dict[str, Any]] = {}
    for path in repository_paths:
        resolved = path.expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"repository path is outside the bounded projects root: {resolved}"
            ) from error
        record = repository_record_for_root(resolved)
        records[str(record["repo_id"])] = record
    return [records[repo_id] for repo_id in sorted(records)]


def local_environment_audit_payload(
    *,
    repo_path: Path,
    output_dir: Path | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    root = repo_path.expanduser().resolve()
    repository = repository_record_for_root(root)
    resolved_as_of = parse_as_of(as_of)
    audit_id = stable_id("local-audit", str(root), resolved_as_of)
    result = audit_repository(repository=repository, as_of=resolved_as_of, run_id=audit_id)
    artifact_root = _artifact_root(output_dir, audit_id, local=True)
    summary = _build_summary(
        audit_id=audit_id,
        as_of=resolved_as_of,
        repositories=[result],
        dynamic=False,
        changed_only=True,
    )
    paths = _write_audit_artifacts(
        artifact_root=artifact_root,
        inventory={
            "schema": FLEET_INVENTORY_SCHEMA,
            "audit_id": audit_id,
            "as_of": resolved_as_of,
            "projects_root": str(root.parent),
            "scope": "single repository environment-legibility profile",
            "repositories": [result["repository"]],
            "provenance_hash": digest(result["repository"]),
        },
        results=[result],
        summary=summary,
    )
    return {
        "schema": FLEET_AUDIT_SCHEMA,
        "status": "completed",
        "audit_id": audit_id,
        "repo_id": repository["repo_id"],
        "as_of": resolved_as_of,
        "artifact_root": str(artifact_root),
        "artifact_paths": paths,
        "summary": summary,
        "implementation_allowed": False,
    }


def fleet_show_payload(
    *, repo_id: str, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = _resolve_artifact_root(output_dir, audit_id)
    path = artifact_root / "findings" / f"{repo_id}.json"
    payload = _read_json(path)
    return {
        "schema": FLEET_FINDING_SCHEMA,
        "status": "found",
        "audit_id": artifact_root.name,
        "repo_id": repo_id,
        "finding": payload,
        "plan": payload.get("plan"),
        "private": True,
    }


def fleet_replay_payload(
    *, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = _resolve_artifact_root(output_dir, audit_id)
    inventory = _read_json(artifact_root / "inventory.json")
    summary = _read_json(artifact_root / "summary.json")
    results: list[dict[str, Any]] = []
    findings_root = artifact_root / "findings"
    for path in sorted(findings_root.glob("*.json")):
        results.append(_read_json(path))
    rebuilt = _build_summary(
        audit_id=str(inventory["audit_id"]),
        as_of=str(inventory["as_of"]),
        repositories=results,
        dynamic=bool(inventory.get("dynamic_policy", {}).get("enabled", False)),
        changed_only=bool(inventory.get("dynamic_policy", {}).get("changed_only", True)),
    )
    deterministic = canonical_json(rebuilt) == canonical_json(summary)
    return {
        "schema": FLEET_REPLAY_SCHEMA,
        "status": "passed" if deterministic else "failed",
        "audit_id": inventory.get("audit_id"),
        "deterministic": deterministic,
        "source_summary_hash": digest(summary),
        "replayed_summary_hash": digest(rebuilt),
        "repository_count": len(results),
        "artifact_root": str(artifact_root),
        "implementation_allowed": False,
    }


def fleet_report_payload(
    *, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = _resolve_artifact_root(output_dir, audit_id)
    summary = _read_json(artifact_root / "summary.json")
    projection = public_projection(summary)
    report = {
        "schema": FLEET_REPORT_SCHEMA,
        "status": "review_required",
        "audit_id": summary.get("audit_id"),
        "as_of": summary.get("as_of"),
        "summary": projection,
        "methodology": summary.get("methodology"),
        "privacy": projection.get("privacy"),
        "publication": {"manual_review_required": True, "published": False},
    }
    paths = {
        "report_json": str(write_json(artifact_root / "report.json", report)),
        "report_md": str(write_text(artifact_root / "report.md", report_markdown(report))),
    }
    return {**report, "artifact_root": str(artifact_root), "artifact_paths": paths}


def _build_summary(
    *,
    audit_id: str,
    as_of: str,
    repositories: list[dict[str, Any]],
    dynamic: bool,
    changed_only: bool,
) -> dict[str, Any]:
    dimension_scores: dict[str, list[float]] = {dimension: [] for dimension in DIMENSIONS}
    finding_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    dynamic_counts = {
        key: 0
        for key in (
            "selected",
            "reused",
            "passed",
            "failed",
            "blocked",
            "unavailable",
            "timeout",
            "unknown",
        )
    }
    unresolved: list[str] = []
    for result in repositories:
        for finding in result.get("findings", []):
            status = str(finding.get("status", "unknown"))
            finding_counts[status] = finding_counts.get(status, 0) + 1
            priority = str(finding.get("priority", "P2"))
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
            score = finding.get("score")
            dimension = finding.get("dimension")
            if isinstance(score, int | float) and isinstance(dimension, str) and score >= 0:
                dimension_scores.setdefault(dimension, []).append(float(score))
            if status in {"unknown", "stale", "blocked"}:
                unresolved.append(f"{result.get('repo_id')}:{dimension}:{status}")
        for score_record in applicable_agent_usability_scores(result.get("agent_usability")):
            dimension = str(score_record["dimension"])
            status = str(score_record["status"])
            dimension_scores.setdefault(dimension, []).append(float(score_record["score"]))
            if status in {"unknown", "stale", "blocked"}:
                unresolved.append(f"{result.get('repo_id')}:{dimension}:{status}")
        dynamic_result = result.get("dynamic")
        if isinstance(dynamic_result, dict):
            state = str(dynamic_result.get("status", "unknown"))
            if dynamic_result.get("selected") is True:
                dynamic_counts["selected"] += 1
            if state == "reused":
                dynamic_counts["reused"] += 1
            elif state == "passed":
                dynamic_counts["passed"] += 1
            elif state == "failed":
                dynamic_counts["failed"] += 1
            elif state == "blocked":
                dynamic_counts["blocked"] += 1
            elif state == "unavailable":
                dynamic_counts["unavailable"] += 1
            elif state == "timeout":
                dynamic_counts["timeout"] += 1
            elif state == "unknown":
                dynamic_counts["unknown"] += 1
    all_scores = [score for scores in dimension_scores.values() for score in scores]
    means = {
        dimension: round(sum(scores) / len(scores), 3) if scores else None
        for dimension, scores in sorted(dimension_scores.items())
    }
    stable_repositories = sorted(repositories, key=lambda item: str(item.get("repo_id", "")))
    return {
        "schema": "quality-runner-fleet-summary-v0.1",
        "status": "completed",
        "audit_id": audit_id,
        "as_of": as_of,
        "repository_count": len(repositories),
        "checkout_count": sum(
            int(item.get("repository", {}).get("checkout_count", 0)) for item in repositories
        ),
        "static_completed": len(repositories),
        "dynamic_policy": {"enabled": dynamic, "changed_only": changed_only},
        "dynamic_selected": dynamic_counts["selected"],
        "dynamic_reused": dynamic_counts["reused"],
        "dynamic_passed": dynamic_counts["passed"],
        "dynamic_failed": dynamic_counts["failed"],
        "dynamic_blocked": dynamic_counts["blocked"],
        "dynamic_unavailable": dynamic_counts["unavailable"],
        "dynamic_timeout": dynamic_counts["timeout"],
        "mean_maturity": round(sum(all_scores) / len(all_scores), 3) if all_scores else None,
        "dimension_means": means,
        "finding_counts": dict(sorted(finding_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "sample_size": {
            "repositories": len(repositories),
            "applicable_dimension_scores": len(all_scores),
        },
        "confidence": "medium" if repositories else "low",
        "unresolved_measurement_gaps": sorted(set(unresolved)),
        "methodology": {
            "rubric": "0 absent, 1 informal, 2 discoverable, 3 executable/currently validated, 4 maintained/routed/automatically checked",
            "unknown_evidence_is_not_green": True,
            "not_applicable_requires_bounded_evidence": True,
            "dynamic_scope": "changed, new, dirty, priority, stale, failed, or incomplete evidence only",
            "target_branch_policy": "documented development branch, default dev; no maturity-based branch selection",
            "source_checkouts_modified": False,
        },
        "provenance_hash": digest(
            {
                "audit_id": audit_id,
                "as_of": as_of,
                "repositories": [
                    item.get("static_provenance_hash") for item in stable_repositories
                ],
                "dynamic": [item.get("dynamic") for item in stable_repositories],
            }
        ),
    }


def _write_audit_artifacts(
    *,
    artifact_root: Path,
    inventory: dict[str, Any],
    results: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, str]:
    prepare_safe_directory(artifact_root)
    findings_dir = prepare_safe_directory(artifact_root / "findings")
    plans_dir = prepare_safe_directory(artifact_root / "plans")
    write_json(artifact_root / "inventory.json", inventory)
    write_json(artifact_root / "summary.json", summary)
    write_text(artifact_root / "summary.md", summary_markdown(summary))
    for result in results:
        repo_id = str(result["repo_id"])
        finding_path = write_json(findings_dir / f"{repo_id}.json", result)
        plan = result.get("plan", {})
        plan_path = write_json(plans_dir / f"{repo_id}.json", plan)
        plan_md_path = write_text(plans_dir / f"{repo_id}.md", plan_markdown(plan))
        result["artifact_paths"] = {
            "finding_json": str(finding_path),
            "plan_json": str(plan_path),
            "plan_md": str(plan_md_path),
        }
    replay_manifest = {
        "schema": FLEET_REPLAY_SCHEMA,
        "audit_id": inventory["audit_id"],
        "as_of": inventory["as_of"],
        "inventory_hash": digest(inventory),
        "summary_hash": digest(summary),
        "finding_hashes": {str(result["repo_id"]): digest(result) for result in results},
        "provenance_hash": digest({"inventory": inventory, "summary": summary}),
    }
    write_json(artifact_root / "replay-manifest.json", replay_manifest)
    return {
        "inventory_json": str(artifact_root / "inventory.json"),
        "summary_json": str(artifact_root / "summary.json"),
        "summary_md": str(artifact_root / "summary.md"),
        "replay_manifest": str(artifact_root / "replay-manifest.json"),
        "findings_dir": str(findings_dir),
        "plans_dir": str(plans_dir),
    }


def _artifact_root(output_dir: Path | None, audit_id: str, *, local: bool = False) -> Path:
    if output_dir is not None:
        base = output_dir.expanduser().resolve()
        return base if base.name == audit_id else base / audit_id
    base = DEFAULT_FLEET_ROOT.expanduser().resolve()
    return base / (f"local/{audit_id}" if local else audit_id)


def _resolve_artifact_root(output_dir: Path | None, audit_id: str | None) -> Path:
    if output_dir is not None:
        candidate = output_dir.expanduser().resolve()
        if (candidate / "inventory.json").is_file():
            return candidate
        if audit_id:
            return candidate / audit_id
        return _latest_audit(candidate)
    base = DEFAULT_FLEET_ROOT.expanduser().resolve()
    if audit_id:
        direct = base / audit_id
        if direct.is_dir():
            return direct
        local = base / "local" / audit_id
        if local.is_dir():
            return local
    return _latest_audit(base)


def _latest_audit(root: Path) -> Path:
    candidates = [path for path in root.glob("**/inventory.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no fleet audit artifacts found under {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime).parent


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
