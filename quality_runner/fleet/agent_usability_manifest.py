from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.contracts import FRESHNESS_DAYS

AGENT_USABILITY_MANIFEST_SCHEMA = "agent-usability/v1"
AGENT_USABILITY_MANIFEST_PATH = Path(".agents/agent-usability.json")


def read_manifest(root: Path) -> tuple[dict[str, Any], str | None]:
    path = root / AGENT_USABILITY_MANIFEST_PATH
    if not path.is_file() or path.is_symlink():
        return {}, None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {}, f"Agent-usability manifest could not be parsed: {error}"
    if not isinstance(value, dict):
        return {}, f"Agent-usability manifest must use {AGENT_USABILITY_MANIFEST_SCHEMA}."
    value = cast(dict[str, Any], value)
    if value.get("schema") != AGENT_USABILITY_MANIFEST_SCHEMA:
        return {}, f"Agent-usability manifest must use {AGENT_USABILITY_MANIFEST_SCHEMA}."
    return value, None


def supported_skill_exemption(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    value = cast(dict[str, Any], value)
    if value.get("status") != "not_applicable":
        return False
    reason = value.get("reason")
    evidence = value.get("evidence")
    evidence_values = cast(list[object], evidence) if isinstance(evidence, list) else []
    return (
        isinstance(reason, str)
        and bool(reason.strip())
        and bool(evidence_values)
        and all(isinstance(item, str) and bool(item.strip()) for item in evidence_values)
    )


def evidence_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    items: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, str):
            items.append({"path": item})
        elif isinstance(item, dict):
            typed_item = cast(dict[str, Any], item)
            if isinstance(typed_item.get("path"), str):
                items.append(typed_item)
    return items


def fresh_passed_evidence(item: dict[str, Any], as_of: str) -> bool:
    return item.get("status") == "passed" and is_fresh_date(item.get("observed_at"), as_of)


def is_fresh_date(value: object, as_of: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        current = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current - observed <= timedelta(days=FRESHNESS_DAYS)


def local_file(root: Path, value: str) -> bool:
    if not value or value.startswith(("/", "~")) or ".." in Path(value).parts:
        return False
    current = root
    for part in Path(value).parts:
        current /= part
        if current.is_symlink():
            return False
    try:
        return current.is_file() and current.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    return [item for item in values if isinstance(item, str) and item]


def objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    return [cast(dict[str, Any], item) for item in values if isinstance(item, dict)]
