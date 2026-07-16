from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quality_runner.manifest import git_state_for_repo
from quality_runner.readiness_evidence import (
    load_release_evidence,
)
from quality_runner.readiness_evidence import (
    validate_release_evidence as _validate_release_evidence,
)
from quality_runner.readiness_gate_helpers import (
    blocked_gate as _blocked_gate,
)
from quality_runner.readiness_gate_helpers import (
    dedupe_gates as _dedupe_gates,
)
from quality_runner.readiness_gates import (
    acceptance_gate as _acceptance_gate,
)
from quality_runner.readiness_gates import (
    aggregate_gate as _aggregate_gate,
)
from quality_runner.readiness_gates import (
    manifest_gate as _manifest_gate,
)
from quality_runner.readiness_gates import (
    migration_evidence_gate as _migration_evidence_gate,
)
from quality_runner.readiness_gates import (
    provenance_gate as _provenance_gate,
)
from quality_runner.readiness_gates import (
    publication_gate as _publication_gate,
)
from quality_runner.readiness_gates import (
    read_only_gate as _read_only_gate,
)

RELEASE_PROFILE = "release"
READINESS_GATE_IDS = (
    "evidence_provenance",
    "read_only_integrity",
    "release_manifest_coherence",
    "package_consumer_smoke",
    "migration_safety",
    "release_acceptance_evidence",
    "publication_visibility_review",
    "aggregate_coverage",
)
CONDITIONAL_READINESS_GATE_IDS = {"migration_safety", "publication_visibility_review"}
DEFAULT_EVIDENCE_FILE = ".quality-runner/release-evidence.json"
READINESS_COMMAND_ALIASES = {
    "package-smoke": "package_consumer_smoke",
    "consumer-smoke": "package_consumer_smoke",
    "installed-smoke": "package_consumer_smoke",
    "release-smoke": "package_consumer_smoke",
    "migration-safety": "migration_safety",
    "migration-smoke": "migration_safety",
    "migration-rollback": "migration_safety",
    "db-migration": "migration_safety",
}


def canonical_readiness_command_id(value: str) -> str:
    return READINESS_COMMAND_ALIASES.get(value, value)


def validate_release_evidence(payload: object) -> list[str]:
    return _validate_release_evidence(payload)


def is_release_profile(standards_packet: dict[str, Any]) -> bool:
    return standards_packet.get("profile") == RELEASE_PROFILE


def build_readiness_capabilities(
    *,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    quality_commands: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not is_release_profile(standards_packet):
        return [], []
    available = [
        _evidence_capability(capability_id)
        for capability_id in (
            "evidence_provenance",
            "read_only_integrity",
            "release_manifest_coherence",
            "release_acceptance_evidence",
            "aggregate_coverage",
        )
    ]
    missing: list[dict[str, Any]] = []
    package_command = _quality_command(quality_commands, "package_consumer_smoke")
    if package_command is None:
        missing.append(
            _missing_capability(
                "package_consumer_smoke",
                "release profile requires an installed-package consumer smoke command",
            )
        )
    else:
        available.append(_command_capability(package_command))
    if _stateful_surface(scan):
        migration_command = _quality_command(quality_commands, "migration_safety")
        if migration_command is None:
            missing.append(
                _missing_capability(
                    "migration_safety",
                    "database migration surface requires rollback and reconciliation evidence",
                )
            )
        else:
            available.append(_command_capability(migration_command))
    return available, missing


def add_readiness_capabilities(
    *,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    quality_commands: list[dict[str, str]],
    available: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness_available, readiness_missing = build_readiness_capabilities(
        scan=scan,
        standards_packet=standards_packet,
        quality_commands=quality_commands,
    )
    available.extend(readiness_available)
    missing.extend(readiness_missing)
    return build_readiness_policy_summary(
        scan=scan,
        standards_packet=standards_packet,
        available=available,
        missing=missing,
    )


def build_readiness_policy_summary(
    *,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    available: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_release_profile(standards_packet):
        return {
            "profile": standards_packet.get("profile"),
            "status": "not-applicable",
            "required_gate_ids": [],
            "unresolved_gate_ids": [],
            "missing_required_capability_ids": [],
        }
    required = _required_readiness_gate_ids(scan=scan, capability_map={"available": available})
    missing_ids = {
        item.get("id")
        for item in missing
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    unresolved = sorted(gate_id for gate_id in required if gate_id in missing_ids)
    missing_required = _missing_required_capability_ids(missing)
    repo_root_value = standards_packet.get("repo_root")
    repo_root = Path(repo_root_value) if isinstance(repo_root_value, str) else Path.cwd()
    config = standards_packet.get("config")
    evidence_file = str(
        resolve_evidence_path(
            repo_root=repo_root,
            config=config if isinstance(config, dict) else {},
            override=None,
        )
    )
    return {
        "profile": RELEASE_PROFILE,
        "status": "blocked" if unresolved or missing_required else "pending",
        "required_gate_ids": required,
        "unresolved_gate_ids": unresolved,
        "missing_required_capability_ids": missing_required,
        "evidence_file": evidence_file,
        "verification": "not-run",
    }


def resolve_evidence_path(
    *, repo_root: Path, config: dict[str, Any], override: Path | None
) -> Path:
    readiness = config.get("readiness")
    configured = readiness.get("evidence_file") if isinstance(readiness, dict) else None
    candidate = override if override is not None else Path(configured or DEFAULT_EVIDENCE_FILE)
    resolved = candidate.expanduser()
    if not resolved.is_absolute():
        resolved = repo_root / resolved
    return Path(os.path.abspath(resolved))


def apply_readiness_evidence_override(
    *,
    capability_map: dict[str, Any],
    standards_packet: dict[str, Any],
    repo_root: Path,
    evidence_file: Path | None,
) -> dict[str, Any]:
    if evidence_file is None or not is_release_profile(standards_packet):
        return capability_map
    readiness = capability_map.get("readiness")
    if not isinstance(readiness, dict):
        return capability_map
    config = standards_packet.get("config")
    updated = dict(capability_map)
    updated["readiness"] = {
        **readiness,
        "evidence_file": str(
            resolve_evidence_path(
                repo_root=repo_root,
                config=config if isinstance(config, dict) else {},
                override=evidence_file,
            )
        ),
    }
    return updated


def evaluate_readiness(
    *,
    repo_root: Path,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    capability_map: dict[str, Any],
    gate_verification: dict[str, Any],
    verification_context: dict[str, Any] | None,
    evidence_file: Path | None,
) -> dict[str, Any]:
    if not is_release_profile(standards_packet):
        return {
            "profile": standards_packet.get("profile"),
            "status": "not-applicable",
            "required_gate_ids": [],
            "unresolved_gate_ids": [],
            "missing_required_capability_ids": [],
            "gates": [],
        }
    config = standards_packet.get("config")
    evidence_path = resolve_evidence_path(
        repo_root=repo_root,
        config=config if isinstance(config, dict) else {},
        override=evidence_file,
    )
    evidence, evidence_error = load_release_evidence(repo_root, evidence_path)
    current_git = git_state_for_repo(repo_root)
    existing = {
        str(gate.get("id")): gate
        for gate in gate_verification.get("gates", [])
        if isinstance(gate, dict) and isinstance(gate.get("id"), str)
    }
    required = _required_readiness_gate_ids(scan=scan, capability_map=capability_map)
    readiness_gates = [
        _provenance_gate(
            scan=scan,
            current_git=current_git,
            evidence=evidence,
            evidence_error=evidence_error,
        ),
        _manifest_gate(
            repo_root=repo_root,
            current_git=current_git,
            evidence=evidence,
            evidence_error=evidence_error,
            observed_digest=_observed_artifact_digest(gate_verification),
        ),
        _acceptance_gate(evidence=evidence, evidence_error=evidence_error),
        _aggregate_gate(scan=scan, capability_map=capability_map),
    ]
    if _stateful_surface(scan):
        readiness_gates.append(
            _migration_evidence_gate(
                evidence=evidence,
                evidence_error=evidence_error,
                existing=existing,
            )
        )
    if _publication_review_required(capability_map):
        readiness_gates.append(
            _publication_gate(
                existing=existing,
                capability_map=capability_map,
                evidence=evidence,
                evidence_error=evidence_error,
            )
        )
    readiness_gates.append(
        _read_only_gate(
            gate_verification=gate_verification,
            verification_context=verification_context,
        )
    )
    missing_by_id = {
        str(item.get("id")): str(item.get("reason"))
        for item in capability_map.get("missing", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    unresolved: list[str] = []
    for gate_id in required:
        gate = next((item for item in readiness_gates if item.get("id") == gate_id), None)
        existing_gate = existing.get(gate_id)
        if gate is None and existing_gate is not None:
            gate = existing_gate
        if gate is None:
            gate = _blocked_gate(
                gate_id,
                missing_by_id.get(gate_id, "required release gate was not discovered"),
                "evidence",
            )
            readiness_gates.append(gate)
        if gate.get("status") != "passed":
            unresolved.append(gate_id)
    missing_required = _missing_required_capability_ids(
        [item for item in capability_map.get("missing", []) if isinstance(item, dict)]
    )
    for capability_id in missing_required:
        missing_item = next(
            (
                item
                for item in capability_map.get("missing", [])
                if isinstance(item, dict) and item.get("id") == capability_id
            ),
            {},
        )
        readiness_gates.append(
            _blocked_gate(
                capability_id,
                str(
                    missing_item.get("reason")
                    or "required executable capability was not discovered"
                ),
                "evidence",
            )
        )
    return {
        "profile": RELEASE_PROFILE,
        "status": "blocked" if unresolved or missing_required else "passed",
        "required_gate_ids": required,
        "unresolved_gate_ids": sorted(set(unresolved)),
        "missing_required_capability_ids": missing_required,
        "evidence_file": str(evidence_path),
        "gates": _dedupe_gates(readiness_gates),
        "verification_context": verification_context or {},
    }


def _required_readiness_gate_ids(
    *, scan: dict[str, Any], capability_map: dict[str, Any]
) -> list[str]:
    required = [
        gate_id for gate_id in READINESS_GATE_IDS if gate_id not in CONDITIONAL_READINESS_GATE_IDS
    ]
    if _stateful_surface(scan):
        required.insert(required.index("release_acceptance_evidence"), "migration_safety")
    if _publication_review_required(capability_map):
        required.insert(required.index("aggregate_coverage"), "publication_visibility_review")
    return required


def _missing_required_capability_ids(missing: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(item["id"])
            for item in missing
            if isinstance(item.get("id"), str)
            and item["id"] not in READINESS_GATE_IDS
            and item.get("required_by") in {"profile", "config", "release"}
        }
    )


def _has_surface(scan: dict[str, Any], surface_id: str) -> bool:
    surfaces = scan.get("repo_surfaces")
    return isinstance(surfaces, list) and any(
        isinstance(surface, dict) and surface.get("id") == surface_id for surface in surfaces
    )


def _stateful_surface(scan: dict[str, Any]) -> bool:
    return _has_surface(scan, "db_migrations") or _has_surface(scan, "stateful_cutover")


def _publication_review_required(capability_map: dict[str, Any]) -> bool:
    return any(
        isinstance(capability, dict)
        and capability.get("id") == "security_publication_visibility_review"
        for capability in capability_map.get("available", [])
    )


def _observed_artifact_digest(gate_verification: dict[str, Any]) -> str | None:
    provenance = gate_verification.get("provenance")
    if isinstance(provenance, dict) and isinstance(provenance.get("artifact_digest"), str):
        return provenance["artifact_digest"]
    for gate in gate_verification.get("gates", []):
        if isinstance(gate, dict) and isinstance(gate.get("artifact_digest"), str):
            return gate["artifact_digest"]
    return None


def _quality_command(commands: list[dict[str, str]], capability_id: str) -> dict[str, str] | None:
    return next((command for command in commands if command.get("id") == capability_id), None)


def _command_capability(command: dict[str, str]) -> dict[str, Any]:
    return {
        "id": command["id"],
        "type": "command",
        "capability_kind": "local_command",
        "source": command["source"],
        "command": command["command"],
        "language": command.get("language", "unknown"),
        "required_by": "release",
        "owner": command.get("owner", "repository"),
        "severity": "blocker",
        "verification_state": {
            "discovery": "command-discovered",
            "execution": "not-run",
            "result": "unknown",
        },
    }


def _evidence_capability(capability_id: str) -> dict[str, Any]:
    return {
        "id": capability_id,
        "type": "evidence",
        "capability_kind": "evidence",
        "source": "quality-runner release readiness policy",
        "required_by": "release",
        "severity": "blocker",
        "verification_state": {
            "discovery": "available",
            "execution": "not-applicable",
            "result": "unknown",
        },
    }


def _missing_capability(capability_id: str, reason: str) -> dict[str, Any]:
    return {
        "id": capability_id,
        "type": "evidence",
        "capability_kind": "evidence",
        "reason": reason,
        "language": "unknown",
        "required_by": "release",
        "severity": "blocker",
    }
