from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from quality_runner.artifacts import write_json
from quality_runner.ci_gate_audit import audit_ci_gate_candidates
from quality_runner.fleet import audit_coverage
from quality_runner.fleet.audit_artifacts import (
    _artifact_root,
    _read_json,
    _write_audit_artifacts,
)
from quality_runner.fleet.audit_artifacts import (
    fleet_replay_payload as fleet_replay_payload,
)
from quality_runner.fleet.audit_artifacts import (
    fleet_report_payload as fleet_report_payload,
)
from quality_runner.fleet.audit_artifacts import (
    fleet_show_payload as fleet_show_payload,
)
from quality_runner.fleet.audit_artifacts import (
    resolve_artifact_root as resolve_artifact_root,
)
from quality_runner.fleet.contracts import (
    FLEET_AUDIT_SCHEMA,
    FLEET_INVENTORY_SCHEMA,
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
from quality_runner.fleet.scope_manifest import load_fleet_scope_manifest, population_coverage
from quality_runner.fleet.standard_audit import build_standard_report
from quality_runner.fleet.static_scan import static_scan_repository as _static_scan_repository
from quality_runner.fleet.summary import build_fleet_summary

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
    inventory = {
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
        mac_control_repository_paths = _mac_control_repository_paths(inventory["repositories"])
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
            scope=inventory["scope"],
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
        target = repository.get("target_branch")
        target_head = target.get("head") if isinstance(target, dict) else None
        target_checkout_id = target.get("checkout_id") if isinstance(target, dict) else None
        exact_checkout = next(
            (
                checkout
                for checkout in repository.get("checkouts", [])
                if isinstance(checkout, dict)
                and isinstance(checkout.get("path"), str)
                and checkout.get("exists") is True
                and (
                    checkout.get("checkout_id") == target_checkout_id
                    or checkout.get("head") == target_head
                )
                and (not target_head or checkout.get("head") == target_head)
            ),
            None,
        )
        if exact_checkout is not None:
            paths.append(Path(str(exact_checkout["path"])))
        else:
            paths.append(Path(str(_static_scan_repository(repository)["primary_path"])))
    return paths
