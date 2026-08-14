from __future__ import annotations

from typing import Any, cast


def action_group_markdown(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    lines = ["", "### Action Groups", ""]
    for raw_group in cast(list[Any], value):
        group = cast(dict[str, Any], raw_group) if isinstance(raw_group, dict) else None
        if group is None:
            continue
        blocker_class = group.get("class")
        gate_ids = group.get("gate_ids")
        actions = group.get("actions")
        finding_ids = group.get("finding_ids")
        if not isinstance(blocker_class, str):
            continue
        if isinstance(gate_ids, list):
            ids_source: list[Any] | None = cast(list[Any], gate_ids)
        elif isinstance(finding_ids, list):
            ids_source = cast(list[Any], finding_ids)
        else:
            ids_source = None
        ids = (
            [gate_id for gate_id in ids_source if isinstance(gate_id, str) and gate_id]
            if isinstance(ids_source, list)
            else []
        )
        if not ids:
            continue
        lines.append(f"- {blocker_class}: {', '.join(ids)}")
        if isinstance(actions, list):
            for action in cast(list[Any], actions):
                if isinstance(action, str) and action:
                    lines.append(f"  - {action}")
    return lines if len(lines) > 3 else []
