from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

FLEET_AUDIT_SCHEMA = "quality-runner-fleet-audit-v0.1"
FLEET_INVENTORY_SCHEMA = "quality-runner-fleet-inventory-v0.1"
FLEET_CHECKOUT_SCHEMA = "quality-runner-fleet-checkout-v0.1"
FLEET_FINDING_SCHEMA = "quality-runner-environment-legibility-finding-v0.1"
FLEET_PLAN_SCHEMA = "quality-runner-environment-legibility-plan-v0.1"
FLEET_REPLAY_SCHEMA = "quality-runner-fleet-replay-v0.1"
FLEET_REPORT_SCHEMA = "quality-runner-fleet-report-v0.1"
FLEET_STANDARD_REPORT_SCHEMA = "quality-runner-fleet-standard-report-v1"

MATRIX_MAINTENANCE_STANDARD = "matrix-maintenance"
DEVELOPER_LEGIBILITY_STANDARD = "developer-legibility"
STANDARD_DIMENSIONS = {
    MATRIX_MAINTENANCE_STANDARD: "matrix_maintenance",
    DEVELOPER_LEGIBILITY_STANDARD: "developer_legibility",
}
SUPPORTED_FLEET_STANDARDS = tuple(STANDARD_DIMENSIONS)

DIMENSIONS = (
    "architecture_boundaries",
    "artifact_supply_chain",
    "accessibility",
    "change_surface_coverage",
    "code_health",
    "diagnosability.stable_error_codes",
    "compatibility_migration",
    "critical_user_journeys",
    "data_integrity_migration",
    "dependency_vulnerability",
    "developer_legibility",
    "change_surface_hotspots",
    "matrix_maintenance",
    "quality_commands",
    "coding_conventions",
    "security_constraints",
    "secret_privacy",
    "failure_modes",
    "implementation_examples",
    "definition_of_done",
    "approval_gated_paths",
    "deployment_rollback",
    "license_contribution",
    "maintenance_health",
    "observability_runtime_health",
    "ownership_continuity",
    "performance",
    "reliability_resilience",
    "context_routing",
    "skill_contract_quality",
    "strict_policy_visibility",
    "strict_type_debt",
    "web_readiness",
)

DIMENSION_LABELS = {
    "architecture_boundaries": "architecture and boundaries",
    "artifact_supply_chain": "artifact provenance and supply-chain integrity",
    "accessibility": "accessible user experience",
    "change_surface_coverage": "change-surface coverage",
    "code_health": "language-neutral code health",
    "diagnosability.stable_error_codes": "stable error codes",
    "compatibility_migration": "compatibility and migration safety",
    "critical_user_journeys": "critical user-journey verification",
    "data_integrity_migration": "data-integrity and migration safety",
    "dependency_vulnerability": "dependency and vulnerability risk",
    "developer_legibility": "developer legibility",
    "change_surface_hotspots": "change-surface hotspots",
    "quality_commands": "build, test, lint, and quality commands",
    "coding_conventions": "coding conventions",
    "security_constraints": "security and credential constraints",
    "secret_privacy": "secret and privacy controls",
    "failure_modes": "common failure modes",
    "implementation_examples": "good implementation examples",
    "definition_of_done": "definition of done and acceptance criteria",
    "approval_gated_paths": "forbidden and approval-gated paths",
    "deployment_rollback": "deployment and rollback",
    "license_contribution": "license and contribution contract",
    "maintenance_health": "maintenance continuity",
    "observability_runtime_health": "observability and runtime health",
    "ownership_continuity": "ownership and continuity",
    "performance": "user-facing performance evidence",
    "reliability_resilience": "reliability and resilience evidence",
    "context_routing": "context routing and minimum context",
    "skill_contract_quality": "skill contract quality",
    "strict_policy_visibility": "strict policy visibility",
    "strict_type_debt": "strict BasedPyright debt",
    "web_readiness": "holistic web readiness",
    "behavior_assurance": "behavior assurance",
    "dynamic_verification": "dynamic quality verification",
    "matrix_maintenance": "change-matrix maintenance",
}

DIMENSION_TERMS: dict[str, tuple[str, ...]] = {
    "architecture_boundaries": ("architecture", "boundary", "ownership", "module", "system design"),
    "developer_legibility": (
        "developer legibility",
        "naming convention",
        "docstring",
        "rationale comment",
        "newcomer",
    ),
    "change_surface_coverage": ("change surface", "change matrix", "dependency map"),
    "coding_conventions": ("convention", "style", "strict", "format", "coding standard"),
    "security_constraints": ("security", "credential", "secret", "authentication", "do not commit"),
    "failure_modes": ("failure", "troubleshoot", "recovery", "incident", "common issue"),
    "implementation_examples": (
        "example",
        "good implementation",
        "reference implementation",
        "pattern",
    ),
    "definition_of_done": (
        "definition of done",
        "acceptance criteria",
        "quality gate",
        "done when",
        "verify",
    ),
    "approval_gated_paths": (
        "approval",
        "forbidden",
        "do not change",
        "destructive",
        "human review",
    ),
    "deployment_rollback": ("deploy", "deployment", "rollback", "release", "revert"),
    "context_routing": ("read when", "load when", "routing", "minimum context", "context index"),
    "skill_contract_quality": ("skill", "trigger", "observable output"),
    "artifact_supply_chain": (
        "attestation",
        "provenance",
        "sbom",
        "signed release",
        "sigstore",
        "slsa",
    ),
    "accessibility": ("accessibility", "aria", "screen reader", "wcag"),
    "code_health": ("dead code", "format", "lint", "typecheck", "type check"),
    "compatibility_migration": (
        "backward compatible",
        "backwards compatible",
        "compatibility",
        "deprecation",
        "migration",
    ),
    "critical_user_journeys": (
        "critical journey",
        "end-to-end",
        "e2e",
        "smoke test",
        "user journey",
    ),
    "data_integrity_migration": (
        "data integrity",
        "migration",
        "rollback",
        "schema change",
    ),
    "dependency_vulnerability": (
        "dependency audit",
        "osv",
        "pip-audit",
        "vulnerability",
    ),
    "license_contribution": ("contributing", "contribution", "license"),
    "maintenance_health": ("changelog", "maintained", "maintenance", "release cadence"),
    "observability_runtime_health": (
        "alert",
        "health check",
        "logging",
        "metrics",
        "observability",
        "tracing",
    ),
    "ownership_continuity": ("codeowners", "maintainer", "owner", "ownership"),
    "performance": ("bundle budget", "latency", "performance", "response time"),
    "reliability_resilience": (
        "fault tolerance",
        "reliability",
        "resilience",
        "retry",
        "smoke test",
    ),
    "secret_privacy": ("privacy", "secret scan", "secrets scan", "sensitive data"),
    "web_readiness": ("browser evidence", "web readiness", "web-readiness"),
}

DEPLOYMENT_MARKERS = (
    ".github/workflows",
    "vercel.json",
    "fly.toml",
    "dockerfile",
    "docker-compose",
    "render.yaml",
    "railway.json",
    "terraform",
    "pulumi",
)

FRESHNESS_DAYS = 90
MAX_DOCUMENT_BYTES = 250_000
MAX_DOCUMENTS = 120


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(prefix: str, *values: object, length: int = 16) -> str:
    return f"{prefix}-{digest(list(values))[:length]}"


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def parse_as_of(value: str | None) -> str:
    if value is None:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("--as-of must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat()


def standard_dimension(standard: str | None) -> str | None:
    if standard is None:
        return None
    try:
        return STANDARD_DIMENSIONS[standard]
    except KeyError as error:
        supported = ", ".join(SUPPORTED_FLEET_STANDARDS)
        raise ValueError(
            f"unsupported fleet standard {standard!r}; choose one of: {supported}"
        ) from error


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def redact_text(value: str, *, root: Path | None = None) -> str:
    result = value
    if root is not None:
        result = result.replace(str(root.expanduser().resolve()), "<repo>")
    home = Path.home()
    result = result.replace(str(home), "<home>")
    result = re.sub(
        r"(?i)(bearer\s+|token\s*[=:]\s*|password\s*[=:]\s*)\S+", r"\1[REDACTED]", result
    )
    result = re.sub(r"(?i)(https?://)([^/@\s]+):([^/@\s]+)@", r"\1[REDACTED]@", result)
    return result


def public_projection(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = payload
    allowed = {
        "schema",
        "status",
        "audit_id",
        "as_of",
        "repository_count",
        "checkout_count",
        "static_completed",
        "dynamic_selected",
        "dynamic_reused",
        "dynamic_passed",
        "dynamic_failed",
        "dynamic_blocked",
        "dynamic_unavailable",
        "dynamic_timeout",
        "dynamic_unknown",
        "dynamic_not_applicable",
        "mean_maturity",
        "dimension_means",
        "finding_counts",
        "sample_size",
        "confidence",
        "unresolved_measurement_gaps",
        "methodology",
    }
    projection: dict[str, Any] = {key: summary[key] for key in sorted(allowed) if key in summary}
    projection["unresolved_measurement_gaps"] = _aggregate_public_gaps(
        cast(dict[str, Any], summary).get("unresolved_measurement_gaps")
    )
    projection["privacy"] = {
        "aggregate_only": True,
        "raw_paths": False,
        "raw_prompts": False,
        "raw_code": False,
        "raw_diffs": False,
        "raw_transcripts": False,
        "credentials": False,
        "manual_review_required": True,
    }
    return projection


def _aggregate_public_gaps(value: object) -> list[str]:
    counts: dict[str, int] = {}
    if isinstance(value, list):
        for item in cast(list[Any], value):
            if not isinstance(item, str):
                continue
            parts = item.split(":")
            key = ":".join(parts[-2:]) if len(parts) >= 2 else item
            counts[key] = counts.get(key, 0) + 1
    return [
        f"{key} ({count} repositories)" if count != 1 else key
        for key, count in sorted(counts.items())
    ]
