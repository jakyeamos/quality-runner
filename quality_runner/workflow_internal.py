from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def generated_run_id(now: datetime | None = None, suffix: str | None = None) -> str:
    timestamp = datetime.now(UTC) if now is None else now.astimezone(UTC)
    run_suffix = uuid4().hex[:8] if suffix is None else suffix
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{run_suffix}"


def verify_payload_status(
    gate_verification: dict[str, Any],
    remediation_plan: dict[str, Any],
) -> str:
    gate_status = gate_verification.get("status")
    if gate_status == "passed" and remediation_plan.get("slices"):
        return "passed-with-findings"
    return gate_status if isinstance(gate_status, str) else "blocked"
