from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FLEET_AUDIT_SCHEMA = "quality-runner-fleet-audit-v0.1"
FLEET_INVENTORY_SCHEMA = "quality-runner-fleet-inventory-v0.1"
FLEET_CHECKOUT_SCHEMA = "quality-runner-fleet-checkout-v0.1"
FLEET_FINDING_SCHEMA = "quality-runner-environment-legibility-finding-v0.1"
FLEET_PLAN_SCHEMA = "quality-runner-environment-legibility-plan-v0.1"
FLEET_REPLAY_SCHEMA = "quality-runner-fleet-replay-v0.1"
FLEET_REPORT_SCHEMA = "quality-runner-fleet-report-v0.1"

DIMENSIONS = (
    "architecture_boundaries",
    "change_surface_coverage",
    "quality_commands",
    "coding_conventions",
    "security_constraints",
    "failure_modes",
    "implementation_examples",
    "definition_of_done",
    "approval_gated_paths",
    "deployment_rollback",
    "context_routing",
    "skill_contract_quality",
)

DIMENSION_LABELS = {
    "architecture_boundaries": "architecture and boundaries",
    "change_surface_coverage": "change-surface coverage",
    "quality_commands": "build, test, lint, and quality commands",
    "coding_conventions": "coding conventions",
    "security_constraints": "security and credential constraints",
    "failure_modes": "common failure modes",
    "implementation_examples": "good implementation examples",
    "definition_of_done": "definition of done and acceptance criteria",
    "approval_gated_paths": "forbidden and approval-gated paths",
    "deployment_rollback": "deployment and rollback",
    "context_routing": "context routing and minimum context",
    "skill_contract_quality": "skill contract quality",
}

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
        "mean_maturity",
        "dimension_means",
        "finding_counts",
        "sample_size",
        "confidence",
        "unresolved_measurement_gaps",
        "methodology",
    }
    projection = {key: summary[key] for key in sorted(allowed) if key in summary}
    projection["unresolved_measurement_gaps"] = _aggregate_public_gaps(
        summary.get("unresolved_measurement_gaps")
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
        for item in value:
            if not isinstance(item, str):
                continue
            parts = item.split(":")
            key = ":".join(parts[-2:]) if len(parts) >= 2 else item
            counts[key] = counts.get(key, 0) + 1
    return [
        f"{key} ({count} repositories)" if count != 1 else key
        for key, count in sorted(counts.items())
    ]
