from __future__ import annotations

from typing import Any, cast

from quality_runner.schema_constants import REMEDIATION_CONTEXT_SCHEMA


def remediation_context_summary(
    context: dict[str, Any] | None,
    *,
    artifact_path: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(context, dict):
        return None
    context_map = context
    summary = _dict(context_map.get("summary"))
    if summary is None and "status" in context_map:
        summary = context
    if summary is None:
        return None

    def _count(name: str) -> int:
        value = summary.get(name)
        return value if isinstance(value, int) and value >= 0 else 0

    result: dict[str, Any] = {
        "schema": context_map.get("schema", REMEDIATION_CONTEXT_SCHEMA),
        "status": summary.get("status", "needs-understanding"),
        "blocking": bool(summary.get("blocking", True)),
        "record_count": _count("record_count"),
        "finding_count": _count("finding_count"),
        "ready_count": _count("ready_count"),
        "pending_count": _count("pending_count"),
    }
    if isinstance(artifact_path, str) and artifact_path:
        result["artifact_path"] = artifact_path
    return result


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None
