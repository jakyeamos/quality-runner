from __future__ import annotations

from typing import Any

READINESS_BLOCKER_CLASSES = (
    "provenance",
    "evidence",
    "review-required",
    "coverage",
    "isolation",
)


def readiness_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "profile": value.get("profile"),
        "status": value.get("status"),
        "required_gate_ids": value.get("required_gate_ids", []),
        "unresolved_gate_ids": value.get("unresolved_gate_ids", []),
        "missing_required_capability_ids": value.get("missing_required_capability_ids", []),
        "evidence_file": value.get("evidence_file"),
    }


def readiness_markdown(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    unresolved = value.get("unresolved_gate_ids")
    unresolved_text = (
        ", ".join(str(item) for item in unresolved)
        if isinstance(unresolved, list) and unresolved
        else "none"
    )
    return [
        f"- Readiness profile: {value.get('profile')}",
        f"- Readiness status: {value.get('status')}",
        f"- Unresolved readiness gates: {unresolved_text}",
    ]


def readiness_blocker_classification(gates: list[dict[str, Any]]) -> str | None:
    classes = {
        str(gate.get("blocker_class"))
        for gate in gates
        if gate.get("status") == "blocked"
        and gate.get("blocker_class") in READINESS_BLOCKER_CLASSES
    }
    return f"{sorted(classes)[0]}-blocker" if classes else None


def string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def optional_string(key: str, value: object) -> dict[str, str]:
    return {key: value} if isinstance(value, str) and value else {}


def optional_value(key: str, value: object) -> dict[str, object]:
    return {key: value} if value is not None else {}


def timeout_diagnostics(value: dict[str, Any]) -> dict[str, Any] | None:
    diagnostics = value.get("timeout_diagnostics")
    return diagnostics if isinstance(diagnostics, dict) else None
