from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast


def maintained_control(*, root: Path, dimension: str, as_of: str) -> list[dict[str, str]] | None:
    """Return structured control evidence only when its local contract is complete."""

    path = root / "environment-legibility.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reviewed = date.fromisoformat(str(payload["last_reviewed"]))
        controls = payload["controls"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if payload.get("schema") != "quality-runner-environment-legibility/v1":
        return None
    if (date.fromisoformat(as_of[:10]) - reviewed).days > 35:
        return None
    if not isinstance(controls, list):
        return None
    control = next(
        (
            item
            for item in controls
            if isinstance(item, dict) and item.get("dimension") == dimension
        ),
        None,
    )
    if not isinstance(control, dict):
        return None
    evidence = control.get("evidence")
    validation = control.get("validation")
    validation_evidence = control.get("validation_evidence")
    enforcement = control.get("enforcement")
    values = (evidence, validation, validation_evidence)
    if not all(isinstance(value, list) and value for value in values):
        return None
    if not all(
        all(isinstance(item, str) and item for item in cast(list[object], value))
        for value in values
    ):
        return None
    if not isinstance(enforcement, dict) or enforcement.get("mode") not in {"required", "routed"}:
        return None
    resolved_evidence: list[dict[str, str]] = []
    for relative_path in cast(list[str], evidence):
        target = (root / relative_path).resolve()
        if root not in target.parents or not target.is_file():
            return None
        resolved_evidence.append({"path": relative_path, "detail": "structured control evidence"})
    resolved_evidence.append(
        {"path": "environment-legibility.json", "detail": f"{dimension} enforcement contract"}
    )
    resolved_evidence.extend(
        {"path": "environment-legibility.json", "detail": f"validation evidence: {item}"}
        for item in cast(list[str], validation_evidence)
    )
    return resolved_evidence
