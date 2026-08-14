from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import digest, parse_as_of, stable_id
from quality_runner.fleet.discovery import discover_repositories, repository_record_for_root
from quality_runner.fleet.mac_control_artifacts import (
    artifact_root,
    build_summary,
    mac_control_feed_payload,
    mac_control_replay_payload,
    mac_control_report_payload,
    write_artifacts,
)
from quality_runner.fleet.mac_control_audit import _audit_repository
from quality_runner.fleet.mac_control_contracts import (
    MAC_CONTROL_AUDIT_SCHEMA,
    MAC_CONTROL_MANIFEST_RELATIVE_PATH,
    MAC_CONTROL_MANIFEST_SCHEMA,
    MAC_CONTROL_REPORT_SCHEMA,
    MacControlAuditError,
    validate_manifest,
)

__all__ = [
    "MAC_CONTROL_MANIFEST_SCHEMA",
    "mac_control_audit_payload",
    "mac_control_feed_payload",
    "mac_control_report_payload",
    "mac_control_replay_payload",
    "validate_manifest",
]


def mac_control_audit_payload(
    *,
    projects_root: Path,
    output_dir: Path | None = None,
    repository_paths: list[Path] | None = None,
    as_of: str | None = None,
    live: bool = False,
    macctl_path: str = "macctl",
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_as_of = parse_as_of(as_of)
    root = projects_root.expanduser().resolve()
    repositories = _repositories_for_scope(root, repository_paths)
    audit_id = stable_id(
        "mac-control",
        str(root),
        resolved_as_of,
        live,
        macctl_path if live else None,
        str(evidence_dir.expanduser().resolve()) if evidence_dir else None,
        sorted(str(path.expanduser().resolve()) for path in repository_paths or []),
    )
    artifact_dir = artifact_root(output_dir, audit_id)
    entries: list[dict[str, Any]] = []
    provider_results: dict[str, dict[str, Any]] = {}
    for repository in repositories:
        entry, provider = _audit_repository(
            repository,
            commit=_repository_commit(repository),
            observed_at=resolved_as_of,
            live=live,
            macctl_path=macctl_path,
            evidence_dir=evidence_dir,
        )
        entries.append(entry)
        if provider is not None:
            provider_results[str(repository["repo_id"])] = provider

    report = {
        "schema_version": MAC_CONTROL_REPORT_SCHEMA,
        "producer": "mac-control",
        "run_id": audit_id,
        "observed_at": resolved_as_of,
        # Pronto evaluates its current maturity-applicable subset.  QR keeps
        # the broader fleet inventory so the denominator is auditable.
        "scope": "quality_runner_fleet",
        "repositories": entries,
    }
    summary = build_summary(
        audit_id=audit_id,
        observed_at=resolved_as_of,
        projects_root=root,
        repositories=entries,
        live=live,
    )
    inventory = {
        "schema": MAC_CONTROL_AUDIT_SCHEMA,
        "audit_id": audit_id,
        "as_of": resolved_as_of,
        "projects_root": str(root),
        "scope": (
            "explicit repository paths under the bounded projects root"
            if repository_paths is not None
            else "all repository identities under the bounded projects root"
        ),
        "manifest_path": str(MAC_CONTROL_MANIFEST_RELATIVE_PATH),
        "live_policy": {
            "requested": live,
            "provider": "mac-control",
            "macctl_path": macctl_path if live else None,
            "gui_execution_implicit": False,
        },
        "evidence_dir": str(evidence_dir.expanduser().resolve()) if evidence_dir else None,
        "repositories": [
            {
                "repo_id": repository["repo_id"],
                "primary_path": repository["primary_path"],
                "observed_commit": _repository_commit(repository),
            }
            for repository in repositories
        ],
        "provenance_hash": digest(
            {
                "audit_id": audit_id,
                "as_of": resolved_as_of,
                "repositories": [
                    {"repo_id": entry["repository_id"], "commit": entry["observed_commit"]}
                    for entry in entries
                ],
            }
        ),
    }
    paths = write_artifacts(
        artifact_root=artifact_dir,
        inventory=inventory,
        report=report,
        summary=summary,
        provider_results=provider_results,
    )
    return {
        "schema": MAC_CONTROL_AUDIT_SCHEMA,
        "status": "completed" if entries else "blocked",
        "audit_id": audit_id,
        "as_of": resolved_as_of,
        "repository_count": len(entries),
        "artifact_root": str(artifact_dir),
        "artifact_paths": paths,
        "summary": summary,
        "report": report,
        "implementation_allowed": False,
    }


def _repositories_for_scope(
    root: Path, repository_paths: list[Path] | None
) -> list[dict[str, Any]]:
    if repository_paths is None:
        return discover_repositories(root)
    records: dict[str, dict[str, Any]] = {}
    for path in repository_paths:
        resolved = path.expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise MacControlAuditError(
                f"repository path is outside the bounded projects root: {resolved}"
            ) from error
        record = repository_record_for_root(resolved)
        records[str(record["repo_id"])] = record
    return [records[key] for key in sorted(records)]


def _repository_commit(repository: dict[str, Any]) -> str:
    for checkout in repository.get("checkouts", []):
        if (
            isinstance(checkout, dict)
            and checkout.get("is_primary")
            and isinstance(checkout.get("head"), str)
        ):
            return checkout["head"]
    for checkout in repository.get("checkouts", []):
        if isinstance(checkout, dict) and isinstance(checkout.get("head"), str):
            return checkout["head"]
    return ""
