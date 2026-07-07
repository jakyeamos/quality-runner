from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner.artifacts import write_json
from quality_runner.schema_constants import INTENT_SCHEMA

INTENT_TEXT_FIELDS = (
    "goal",
    "constraints",
    "non_goals",
    "tradeoffs",
    "risk_areas",
    "verification_expectations",
)


def resolve_workflow_intent(
    *,
    repo_root: Path,
    run_id: str,
    goal: str | None = None,
    intent_file: Path | None = None,
    source: str = "cli",
    supplied_by: str = "user",
) -> dict[str, Any] | None:
    if intent_file is not None:
        return load_intent_file(
            repo_root=repo_root,
            run_id=run_id,
            intent_file=intent_file,
            source=source,
            supplied_by=supplied_by,
        )
    if goal is not None and goal.strip():
        return build_intent_packet(
            run_id=run_id,
            goal=goal.strip(),
            source=source,
            supplied_by=supplied_by,
        )
    return None


def load_intent_file(
    *,
    repo_root: Path,
    run_id: str,
    intent_file: Path,
    source: str = "file",
    supplied_by: str = "user",
) -> dict[str, Any]:
    path = intent_file.expanduser().resolve()
    repo = repo_root.expanduser().resolve()
    if not path.is_relative_to(repo):
        raise ValueError("intent file must live inside the target repository")
    if path.is_symlink():
        raise ValueError("intent file must not be a symlink")
    if not path.exists():
        raise FileNotFoundError(f"intent file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"intent file is not a file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"intent file is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("intent file must contain a JSON object")
    goal = payload.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("intent file must include a non-empty goal string")
    packet = build_intent_packet(
        run_id=run_id,
        goal=goal.strip(),
        source=source,
        supplied_by=supplied_by,
    )
    for field in INTENT_TEXT_FIELDS:
        if field == "goal":
            continue
        value = payload.get(field)
        if value is None:
            continue
        normalized = _normalize_text_field(field, value)
        if normalized is not None:
            packet[field] = normalized
    return packet


def build_intent_packet(
    *,
    run_id: str,
    goal: str,
    source: str,
    supplied_by: str,
    constraints: list[str] | None = None,
    non_goals: list[str] | None = None,
    tradeoffs: list[str] | None = None,
    risk_areas: list[str] | None = None,
    verification_expectations: list[str] | None = None,
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "schema": INTENT_SCHEMA,
        "run_id": run_id,
        "goal": goal,
        "source": source,
        "supplied_by": supplied_by,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    for field, value in (
        ("constraints", constraints),
        ("non_goals", non_goals),
        ("tradeoffs", tradeoffs),
        ("risk_areas", risk_areas),
        ("verification_expectations", verification_expectations),
    ):
        normalized = _normalize_text_field(field, value)
        if normalized is not None:
            packet[field] = normalized
    return packet


def intent_for_run(intent: dict[str, Any] | None, run_id: str) -> dict[str, Any] | None:
    if intent is None:
        return None
    return {**intent, "run_id": run_id}


def workflow_intent_from_cli_args(
    args: object,
    *,
    repo_root: Path,
    run_id: str | None,
) -> dict[str, Any] | None:
    goal = getattr(args, "intent", None)
    intent_file = getattr(args, "intent_file", None)
    if not goal and not intent_file:
        return None
    return resolve_workflow_intent(
        repo_root=repo_root,
        run_id=run_id or "pending",
        goal=goal,
        intent_file=Path(intent_file).expanduser().resolve() if intent_file else None,
    )


def intent_markdown_lines(intent: object) -> list[str]:
    if not isinstance(intent, dict):
        return []
    lines = ["## Intent", ""]
    goal = intent.get("goal")
    if isinstance(goal, str) and goal:
        lines.append(f"- Goal: {goal}")
    for field, title in (
        ("constraints", "Constraints"),
        ("non_goals", "Non-goals"),
        ("tradeoffs", "Tradeoffs"),
        ("risk_areas", "Risk areas"),
        ("verification_expectations", "Verification expectations"),
    ):
        items = intent.get(field)
        if isinstance(items, list) and items:
            lines.append(f"- {title}:")
            lines.extend(f"  - {item}" for item in items if isinstance(item, str) and item)
    lines.append("")
    return lines


def add_intent_cli_arguments(parser: Any) -> None:
    parser.add_argument(
        "--intent",
        default=None,
        help="Author intent goal for this run (what the user set out to accomplish)",
    )
    parser.add_argument(
        "--intent-file",
        default=None,
        help="Path to intent JSON inside the target repo",
    )


def attach_intent_artifacts(
    *,
    run_dir: Path,
    intent: dict[str, Any] | None,
    artifact_paths: dict[str, str],
) -> dict[str, str]:
    if intent is None:
        return artifact_paths
    updated = dict(artifact_paths)
    updated["intent_json"] = str(write_json(run_dir / "intent.json", intent))
    return updated


def _normalize_text_field(field: str, value: object) -> list[str] | None:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return items or None
    if value is not None:
        raise ValueError(f"intent field {field} must be a string or string list")
    return None
