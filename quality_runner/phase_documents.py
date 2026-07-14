from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import PHASE_BATCH_RESULT_SCHEMA


def render_plan(plan: dict[str, Any]) -> str:
    lines = [
        f"# Plan {plan['id']}: {plan['title']}",
        "",
        "<!-- quality-runner-plan-json:start -->",
        json.dumps(plan, indent=2, sort_keys=True),
        "<!-- quality-runner-plan-json:end -->",
        "",
        "## Goal",
        "",
        f"Remediate the QR cluster `{plan['source_slice_id']}` without expanding the stated scope.",
        "",
        "## QR Evidence",
        "",
        f"- Source run: `{plan['source'].get('run_id') or 'handoff-only'}`",
        f"- Source slice: `{plan['source_slice_id']}`",
        f"- Priority: `{plan['priority']}`",
        f"- Findings: {', '.join(plan['finding_ids']) or 'none recorded'}",
        "",
        "## Scope",
        "",
        f"- In scope: {plan['scope'].get('in_scope', 'the linked QR cluster')}",
        f"- Out of scope: {plan['scope'].get('out_of_scope', 'unrelated findings and design decisions')}",
        "",
        "## Tasks",
        "",
    ]
    lines.extend(f"{index}. {task}" for index, task in enumerate(plan["tasks"], start=1))
    if not plan["tasks"]:
        lines.append("1. Apply the bounded remediation described by the QR slice.")
    lines.extend(["", "## Verification", ""])
    lines.extend(f"- {item}" for item in plan["verification_gates"])
    lines.extend(["", "## Stop Conditions", ""])
    lines.extend(
        f"- {item}"
        for item in plan["stop_conditions"]
        or ["The current code no longer matches the QR evidence."]
    )
    lines.extend(
        [
            "",
            "## Completion Criteria",
            "",
            "- Batch result is recorded.",
            "- QR evidence is refreshed.",
            "- Required findings are resolved or dispositioned with evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def render_summary(plan: dict[str, Any], result: dict[str, Any]) -> str:
    lines = [
        f"# Summary {plan['id']}: {plan['title']}",
        "",
        f"- Status: `{result['status']}`",
        f"- QR run: `{result.get('qr_run_id') or 'not supplied'}`",
        f"- Commit reference: `{result.get('commit') or 'not supplied'}`",
        "",
        "## Summary",
        "",
        result["summary"],
        "",
        "## Verification",
        "",
    ]
    verification = result["verification"]
    lines.extend(
        f"- `{item.get('command')}`: `{item.get('status')}`" for item in verification
    )
    lines.extend(["", "## Remaining Findings", ""])
    lines.extend(f"- {item}" for item in result["remaining_findings"] or ["None recorded."])
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {item}" for item in result["blockers"] or ["None recorded."])
    return "\n".join(lines) + "\n"


def render_verification(payload: dict[str, Any]) -> str:
    lines = [
        f"# Phase {int(payload['phase']):02d} Verification",
        "",
        f"- Status: `{payload['status']}`",
        f"- QR run: `{payload['run_id']}`",
        "",
        "## Plans",
        "",
        *[f"- `{item}`: verified" for item in payload["verified_plan_ids"]],
        *[f"- `{item}`: unresolved" for item in payload["unresolved_plan_ids"]],
        *[f"- `{item}`: failed" for item in payload["failed_checks"]],
        "",
    ]
    return "\n".join(lines)


def load_batch_result(path: Path) -> dict[str, Any]:
    payload = _load_json(path.expanduser().resolve())
    required = {"schema", "status", "summary", "verification", "remaining_findings", "blockers"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"batch result is missing fields: {', '.join(missing)}")
    if payload["schema"] != PHASE_BATCH_RESULT_SCHEMA:
        raise ValueError(f"batch result schema must be {PHASE_BATCH_RESULT_SCHEMA}")
    if payload["status"] not in {"complete", "blocked", "failed", "skipped", "in_progress"}:
        raise ValueError("batch result status is invalid")
    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise ValueError("batch result summary must be a non-empty string")
    if not isinstance(payload["verification"], list) or not all(
        isinstance(item, dict) for item in payload["verification"]
    ):
        raise ValueError("batch result verification must be a list of objects")
    for field in ("remaining_findings", "blockers"):
        if not isinstance(payload[field], list) or not all(
            isinstance(item, str) for item in payload[field]
        ):
            raise ValueError(f"batch result {field} must be a string list")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required JSON artifact does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must contain an object: {path}")
    return payload
