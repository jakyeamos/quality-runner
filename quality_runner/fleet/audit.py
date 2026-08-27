from __future__ import annotations

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import prepare_safe_directory, write_json, write_text
from quality_runner.ci_gate_audit import audit_ci_gate_candidates
from quality_runner.fleet import audit_coverage
from quality_runner.fleet.contracts import (
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
    standard_dimensions,
)
from quality_runner.fleet.coordinator import (
    coordinate_dynamic_result,
    dynamic_repository_watchdog_seconds,
)
from quality_runner.fleet.discovery import (
    load_fleet_policy,
    repositories_for_scope,
    repository_record_for_root,
    resolve_target_branch,
)
from quality_runner.fleet.dynamic import (
    apply_dynamic_quality_evidence,
)
from quality_runner.fleet.dynamic import (
    dynamic_result as build_dynamic_result,
)
from quality_runner.fleet.legibility import audit_repository, build_remediation_plan
from quality_runner.fleet.mac_control import mac_control_audit_payload
from quality_runner.fleet.replay_integrity import replay_manifest_errors
from quality_runner.fleet.reporting import plan_markdown, report_markdown, summary_markdown
from quality_runner.fleet.scope_manifest import load_fleet_scope_manifest, population_coverage
from quality_runner.fleet.standard_audit import build_standard_report
from quality_runner.fleet.static_scan import static_scan_repository as _static_scan_repository
from quality_runner.fleet.summary import build_fleet_summary

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
    standard: str | None = None,
    scope_manifest: Path | None = None,
    mac_control: bool = True,
    mac_control_live: bool = False,
    macctl_path: str = "macctl",
    mac_control_evidence_dir: Path | None = None,
    custody_dispositions: Path | None = None,
    parallelism: int = 1,
) -> dict[str, Any]:
    standard_dimensions(standard)
    if parallelism <= 0:
        raise ValueError("parallelism must be positive")
    if standard is not None and dynamic:
        raise ValueError("standard-scoped fleet audits are static-only; omit --dynamic")
    if mac_control_live and not mac_control:
        raise ValueError("--mac-control-live requires the Mac Control lane")
    resolved_as_of = parse_as_of(as_of)
    root = projects_root.expanduser().resolve()
    fleet_policy = load_fleet_policy(root)
    overrides = target_overrides or {}
    if scope_manifest is not None and repository_paths is not None:
        raise ValueError("scope manifest and explicit repository paths are mutually exclusive")
    scope_manifest_payload = (
        load_fleet_scope_manifest(scope_manifest, projects_root=root)
        if scope_manifest is not None
        else None
    )
    custody_disposition_payload = audit_coverage.load_custody_dispositions(custody_dispositions)
    resolved_repository_paths = (
        [Path(path) for path in scope_manifest_payload["eligible_paths"]]
        if scope_manifest_payload is not None
        else repository_paths
    )
    audit_id = stable_id(
        "audit",
        str(root),
        resolved_as_of,
        dynamic,
        changed_only,
        dynamic_max_age_days,
        timeout_seconds,
        standard,
        sorted(overrides.items()),
        sorted(str(path.expanduser().resolve()) for path in resolved_repository_paths or []),
        scope_manifest_payload.get("manifest_hash") if scope_manifest_payload else None,
        digest(custody_disposition_payload) if custody_disposition_payload else None,
        fleet_policy,
    )
    artifact_root = _artifact_root(output_dir, audit_id)
    repositories = repositories_for_scope(
        root, resolved_repository_paths, fleet_policy=fleet_policy
    )
    coverage = population_coverage(
        repositories=repositories,
        repository_paths=repository_paths,
        fleet_policy=fleet_policy,
        scope_manifest=scope_manifest_payload,
    )

    def audit_one(repository: dict[str, Any]) -> dict[str, Any]:
        target_override = overrides.get(str(repository["repo_id"]))
        target = resolve_target_branch(repository, override=target_override)
        scope_attestation = (
            scope_manifest_payload.get("repository_attestations", {}).get(
                str(repository["primary_path"])
            )
            if scope_manifest_payload is not None
            else None
        )
        repository_with_target = {
            **repository,
            "target_branch": target,
            **({"scope_attestation": scope_attestation} if scope_attestation else {}),
        }
        repository_with_target["audit_coverage"] = audit_coverage.assess_audit_coverage(
            repository_with_target,
            custody_dispositions=custody_disposition_payload.get(
                str(Path(str(repository["primary_path"])).expanduser().resolve()), []
            ),
        )
        static_repository = _static_scan_repository(repository_with_target)
        result = audit_repository(
            repository=static_repository,
            as_of=resolved_as_of,
            run_id=f"{audit_id}-{repository['repo_id']}",
            standard=standard,
        )
        target_branch = target.get("branch") if isinstance(target.get("branch"), str) else None
        target_head = target.get("head") if isinstance(target.get("head"), str) else None
        result["ci_gate_audit"] = audit_ci_gate_candidates(
            Path(str(static_repository["primary_path"])),
            generated_at=resolved_as_of,
            branch=target_branch,
            head_sha=target_head,
        )
        # Keep the canonical repository identity (including its primary path)
        # in persisted artifacts. The ready target checkout is only the static
        # evidence source; it must not replace the identity or dirty-worktree
        # provenance used by Pronto and dynamic verification.
        result["repository"] = repository_with_target
        dynamic_evidence = coordinate_dynamic_result(
            build=build_dynamic_result,
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
        result["plan"] = build_remediation_plan(
            repository=result["repository"],
            findings=result["findings"],
            scan=result["scan"],
            as_of=resolved_as_of,
        )
        return result

    if parallelism == 1 or len(repositories) < 2:
        results = [audit_one(repository) for repository in repositories]
    else:
        with ThreadPoolExecutor(max_workers=min(parallelism, len(repositories))) as executor:
            results = list(executor.map(audit_one, repositories))

    summary = build_fleet_summary(
        audit_id=audit_id,
        as_of=resolved_as_of,
        repositories=results,
        dynamic=dynamic,
        changed_only=changed_only,
        standard=standard,
        population_coverage=coverage,
    )
    inventory: dict[str, Any] = {
        "schema": FLEET_INVENTORY_SCHEMA,
        "audit_id": audit_id,
        "as_of": resolved_as_of,
        "projects_root": str(root),
        "scope": (
            "complete repository population from a validated scope manifest"
            if scope_manifest_payload is not None
            else "explicit repository paths under the bounded projects root"
            if resolved_repository_paths is not None
            else "all repository identities under the bounded projects root"
        ),
        "population_coverage": coverage,
        "dynamic_policy": {
            "enabled": dynamic,
            "changed_only": changed_only,
            "max_age_days": dynamic_max_age_days,
            "timeout_seconds": timeout_seconds,
            "repository_watchdog_timeout_seconds": dynamic_repository_watchdog_seconds(
                timeout_seconds
            ),
        },
        "custody_dispositions": {
            "status": "applied" if custody_disposition_payload else "not_provided",
            "repository_count": len(custody_disposition_payload),
            "provenance_hash": digest(custody_disposition_payload)
            if custody_disposition_payload
            else None,
        },
        "fleet_policy": {**fleet_policy, "applies_to": "automatic discovery"},
        "repositories": [item["repository"] for item in results],
        "provenance_hash": digest(
            {
                "audit_id": audit_id,
                "as_of": resolved_as_of,
                "repositories": [item["repository"] for item in results],
                **({"standard": standard} if standard is not None else {}),
            }
        ),
    }
    if standard is not None:
        inventory["standard"] = standard
    maturity_feed = {
        "status": "not_requested",
        "reason": "immutable snapshot created; run fleet audit feed to update the stable feed",
    }
    if standard is not None:
        maturity_checkpoint = {
            "status": "not_applicable",
            "reason": "standard-scoped snapshots do not form the canonical maturity checkpoint",
        }
    elif not mac_control:
        maturity_checkpoint = {
            "status": "not_requested",
            "reason": "Mac Control was explicitly disabled for this QR audit",
        }
    else:
        # Mac Control is part of the same coordinated checkpoint as QR. Audit
        # the exact target checkout used by the QR target projection, including
        # stale or blocked targets, so its observed commit cannot drift to an
        # unfolded primary worktree. The
        # persisted QR repository identity still retains the original primary
        # path and all custody/audit-coverage evidence.
        mac_control_repository_paths = _mac_control_repository_paths(
            cast(list[dict[str, Any]], inventory["repositories"])
        )
        try:
            mac_control_audit = mac_control_audit_payload(
                projects_root=root,
                output_dir=artifact_root / "mac-control",
                repository_paths=mac_control_repository_paths,
                as_of=resolved_as_of,
                live=mac_control_live,
                macctl_path=macctl_path,
                evidence_dir=mac_control_evidence_dir,
            )
        except (OSError, ValueError) as error:
            maturity_checkpoint = {
                "status": "blocked",
                "reason": f"Mac Control lane could not be created: {error}",
            }
        else:
            maturity_checkpoint = {
                "status": "ready_for_publication",
                "audit_id": mac_control_audit["audit_id"],
                "as_of": mac_control_audit["as_of"],
                "artifact_root": mac_control_audit["artifact_root"],
                "live": mac_control_live,
            }
    inventory["maturity_checkpoint"] = maturity_checkpoint
    artifact_paths = _write_audit_artifacts(
        artifact_root=artifact_root,
        inventory=inventory,
        results=results,
        summary=summary,
        standard_report=build_standard_report(
            audit_id=audit_id,
            as_of=resolved_as_of,
            projects_root=root,
            scope=str(inventory["scope"]),
            repositories=results,
            standard=standard,
        )
        if standard is not None
        else None,
    )
    checkpoint_path = artifact_root / "maturity-checkpoint.json"
    write_json(checkpoint_path, maturity_checkpoint)
    artifact_paths["maturity_checkpoint_json"] = str(checkpoint_path)
    return {
        "schema": FLEET_AUDIT_SCHEMA,
        "status": "completed" if results else "blocked",
        "audit_id": audit_id,
        "as_of": resolved_as_of,
        "repository_count": len(results),
        "standard": standard,
        "artifact_root": str(artifact_root),
        "artifact_paths": artifact_paths,
        "summary": summary,
        "standard_report": _read_json(Path(artifact_paths["standard_report_json"]))
        if "standard_report_json" in artifact_paths
        else None,
        "maturity_feed": (
            {
                "status": "not_applicable",
                "reason": "standard-scoped snapshots are not canonical maturity feeds",
            }
            if standard is not None
            else maturity_feed
        ),
        "maturity_checkpoint": maturity_checkpoint,
        "public_projection": public_projection(summary),
        "implementation_allowed": False,
    }


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
    summary = build_fleet_summary(
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


def _mac_control_repository_paths(repositories: Sequence[dict[str, Any]]) -> list[Path]:
    """Select an exact target checkout for the coordinated Mac Control lane."""

    paths: list[Path] = []
    for repository in repositories:
        target_value = repository.get("target_branch")
        target = cast(dict[str, Any], target_value) if isinstance(target_value, dict) else {}
        target_head = target.get("head") if isinstance(target.get("head"), str) else None
        target_checkout_id = (
            target.get("checkout_id") if isinstance(target.get("checkout_id"), str) else None
        )
        raw_checkouts = repository.get("checkouts", [])
        checkouts = cast(list[object], raw_checkouts) if isinstance(raw_checkouts, list) else []
        exact_checkout: dict[str, Any] | None = None
        for raw_checkout in checkouts:
            if not isinstance(raw_checkout, dict):
                continue
            checkout = cast(dict[str, Any], raw_checkout)
            if (
                isinstance(checkout.get("path"), str)
                and checkout.get("exists") is True
                and (
                    checkout.get("checkout_id") == target_checkout_id
                    or checkout.get("head") == target_head
                )
                and (not target_head or checkout.get("head") == target_head)
            ):
                exact_checkout = checkout
                break
        if exact_checkout is not None:
            paths.append(Path(str(exact_checkout["path"])))
        else:
            paths.append(Path(str(_static_scan_repository(repository)["primary_path"])))
    return paths


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
    manifest = _read_json(artifact_root / "replay-manifest.json")
    results: list[dict[str, Any]] = []
    findings_root = artifact_root / "findings"
    for path in sorted(findings_root.glob("*.json")):
        results.append(_read_json(path))
    rebuilt = build_fleet_summary(
        audit_id=str(inventory["audit_id"]),
        as_of=str(inventory["as_of"]),
        repositories=results,
        dynamic=bool(inventory.get("dynamic_policy", {}).get("enabled", False)),
        changed_only=bool(inventory.get("dynamic_policy", {}).get("changed_only", True)),
        standard=inventory.get("standard"),
        population_coverage=cast(dict[str, Any], inventory.get("population_coverage", {})),
    )
    manifest_errors = replay_manifest_errors(
        manifest=manifest, inventory=inventory, summary=summary, findings=results
    )
    deterministic = canonical_json(rebuilt) == canonical_json(summary) and not manifest_errors
    return {
        "schema": FLEET_REPLAY_SCHEMA,
        "status": "passed" if deterministic else "failed",
        "audit_id": inventory.get("audit_id"),
        "deterministic": deterministic,
        "manifest_valid": not manifest_errors,
        "manifest_errors": manifest_errors,
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
    report: dict[str, Any] = {
        "schema": FLEET_REPORT_SCHEMA,
        "status": "review_required",
        "audit_id": summary.get("audit_id"),
        "as_of": summary.get("as_of"),
        "summary": projection,
        "methodology": summary.get("methodology"),
        "privacy": projection.get("privacy"),
        "publication": {"manual_review_required": True, "published": False},
    }
    standard = summary.get("standard")
    if isinstance(standard, str) and standard:
        standard_report_path = artifact_root / "standard-report.json"
        if standard_report_path.is_file():
            report["standard"] = standard
            report["standard_report"] = _read_json(standard_report_path)
            report["publication"]["canonical_maturity_feed"] = "not_applicable"
    paths = {
        "report_json": str(write_json(artifact_root / "report.json", report)),
        "report_md": str(write_text(artifact_root / "report.md", report_markdown(report))),
    }
    return {**report, "artifact_root": str(artifact_root), "artifact_paths": paths}


def _write_audit_artifacts(
    *,
    artifact_root: Path,
    inventory: dict[str, Any],
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    standard_report: dict[str, Any] | None = None,
) -> dict[str, str]:
    prepare_safe_directory(artifact_root)
    findings_dir = prepare_safe_directory(artifact_root / "findings")
    plans_dir = prepare_safe_directory(artifact_root / "plans")
    write_json(artifact_root / "inventory.json", inventory)
    write_json(artifact_root / "summary.json", summary)
    write_text(artifact_root / "summary.md", summary_markdown(summary))
    if standard_report is not None:
        write_json(artifact_root / "standard-report.json", standard_report)
    for result in results:
        repo_id = str(result["repo_id"])
        write_json(findings_dir / f"{repo_id}.json", result)
        plan = result.get("plan", {})
        write_json(plans_dir / f"{repo_id}.json", plan)
        write_text(plans_dir / f"{repo_id}.md", plan_markdown(plan))
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
    paths = {
        "inventory_json": str(artifact_root / "inventory.json"),
        "summary_json": str(artifact_root / "summary.json"),
        "summary_md": str(artifact_root / "summary.md"),
        "replay_manifest": str(artifact_root / "replay-manifest.json"),
        "findings_dir": str(findings_dir),
        "plans_dir": str(plans_dir),
    }
    if standard_report is not None:
        paths["standard_report_json"] = str(artifact_root / "standard-report.json")
    return paths


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


resolve_artifact_root = _resolve_artifact_root


def _latest_audit(root: Path) -> Path:
    candidates = [path for path in root.glob("**/inventory.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no fleet audit artifacts found under {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime).parent


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
