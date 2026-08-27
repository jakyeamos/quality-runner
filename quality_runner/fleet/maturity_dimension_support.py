from __future__ import annotations

from pathlib import Path
from typing import Any, cast


def assessment(
    score: int | None,
    status: str,
    message: str,
    evidence: list[dict[str, str]],
    *,
    applicability: str = "applicable",
) -> dict[str, Any]:
    return {
        "score": score,
        "status": status,
        "applicability": applicability,
        "severity": "observation",
        "priority": "P1",
        "confidence": "high" if evidence else "medium",
        "message": message,
        "evidence": evidence[:16],
        "validation_commands": ["uv run --locked qr fleet audit run --repo-path REPO --json"],
    }


def not_applicable(message: str, evidence: list[dict[str, str]]) -> dict[str, Any]:
    return assessment(None, "not_applicable", message, evidence, applicability="not_applicable")


def unknown_applicability(message: str, evidence: list[dict[str, str]]) -> dict[str, Any]:
    return assessment(None, "unknown", message, evidence, applicability="unknown")


def score_status(score: int) -> str:
    if score == 4:
        return "maintained"
    if score == 3:
        return "validated"
    if score == 2:
        return "discoverable"
    if score == 1:
        return "present"
    return "absent"


def commands_by_id(scan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    raw = scan.get("quality_commands")
    if not isinstance(raw, list):
        return result
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[str, Any], item)
        if not isinstance(typed_item.get("id"), str):
            continue
        result.setdefault(str(typed_item["id"]), []).append(typed_item)
    return result


def surfaces(scan: dict[str, Any]) -> list[dict[str, str]]:
    raw = scan.get("repo_surfaces")
    if not isinstance(raw, list):
        return []
    values: list[dict[str, str]] = []
    for item in cast(list[object], raw):
        if isinstance(item, dict):
            typed_item = cast(dict[str, Any], item)
            values.append({str(key): str(value) for key, value in typed_item.items()})
    return values


def command_evidence(
    commands: dict[str, list[dict[str, Any]]], identifiers: tuple[str, ...]
) -> list[dict[str, str]]:
    return [
        {
            "path": str(item.get("source", "discovered")),
            "detail": str(item.get("command", identifier)),
        }
        for identifier in identifiers
        for item in commands.get(identifier, [])[:2]
    ]


def matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def term_evidence(terms: list[str]) -> list[dict[str, str]]:
    return [{"path": "documentation", "detail": f"documented term: {term}"} for term in terms[:8]]


def surface_evidence(item: dict[str, str]) -> dict[str, str]:
    return {
        "path": item.get("path", "."),
        "detail": item.get("evidence", item.get("kind", "detected surface")),
    }


def path_evidence(value: object, detail: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    return [{"path": str(path), "detail": detail} for path in values[:8] if isinstance(path, str)]


def existing_paths(root: Path, candidates: tuple[str, ...]) -> list[str]:
    return [candidate for candidate in candidates if (root / candidate).is_file()]


def capability_item(capability_id: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((item for item in items if item.get("id") == capability_id), None)


def verification_result(item: dict[str, Any] | None) -> str:
    if item is None:
        return "unknown"
    state = item.get("verification_state")
    if not isinstance(state, dict):
        return "unknown"
    return str(cast(dict[str, Any], state).get("result", "unknown"))


def capability_evidence(item: dict[str, Any] | None) -> list[dict[str, str]]:
    if item is None:
        return []
    source = item.get("source") or item.get("reason") or "."
    detail = item.get("command") or item.get("status") or "security capability"
    return [{"path": str(source), "detail": str(detail)}]
