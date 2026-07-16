from __future__ import annotations

from typing import Any

VERIFICATION_MODE_VALUES = frozenset({"command", "evidence"})

_COMMAND_MARKERS = (
    "rerun quality-runner",
    "pytest",
    "ruff",
    "pnpm",
    "git diff",
)
_EVIDENCE_MARKERS = (
    "accept",
    "document",
    "evidence",
    "measure",
    "owner",
    "review",
)


def verification_contract_fields(
    finding: dict[str, Any],
    *,
    explicit_mode: object = None,
) -> dict[str, Any]:
    """Return the structured verification contract for a finding."""

    verification = finding.get("verification")
    category = finding.get("category")
    mode = verification_mode_for(
        verification,
        category=category if isinstance(category, str) else None,
        explicit_mode=explicit_mode,
    )
    fields: dict[str, Any] = {"verification_mode": mode}
    if mode == "evidence":
        fields["verification_requirements"] = list(EVIDENCE_REQUIREMENTS)
    return fields


EVIDENCE_REQUIREMENTS = (
    "Review the cited file and line evidence in context.",
    "Record the maintainer or owner decision and rationale.",
    "Attach a command result, artifact, or external-review reference before closure.",
)


def verification_mode_for(
    verification: object,
    *,
    category: str | None = None,
    explicit_mode: object = None,
) -> str:
    """Classify verification as executable command proof or review evidence."""

    if isinstance(explicit_mode, str) and explicit_mode in VERIFICATION_MODE_VALUES:
        return explicit_mode

    text = " ".join(item for item in _string_values(verification)).lower()
    if _has_command_marker(text):
        return "command"
    if _is_evidence_category(category) or any(marker in text for marker in _EVIDENCE_MARKERS):
        return "evidence"
    return "command"


def has_machine_checkable_verification(slice_item: dict[str, Any]) -> bool:
    """Validate the structured verification contract used by handoff slices."""

    verification = slice_item.get("verification_gates")
    if not _non_empty_string_list(verification):
        return False

    mode = slice_item.get("verification_mode")
    if mode == "evidence":
        return _non_empty_string_list(slice_item.get("verification_requirements"))
    if mode is not None and (not isinstance(mode, str) or mode != "command"):
        return False
    return _has_command_verification(verification)


def verification_contract_is_valid(payload: dict[str, Any]) -> bool:
    """Validate mode and evidence requirements without requiring a slice shape."""

    mode = payload.get("verification_mode")
    if mode is None:
        return True
    if not isinstance(mode, str) or mode not in VERIFICATION_MODE_VALUES:
        return False
    if mode == "evidence":
        return _non_empty_string_list(payload.get("verification_requirements"))
    return True


def _has_command_verification(value: object) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, str) or not item:
            continue
        lowered = item.lower()
        if _has_command_marker(lowered):
            return True
        if "`" in item or " run " in f" {lowered} ":
            return True
    return False


def _has_command_marker(text: str) -> bool:
    return any(marker in text for marker in _COMMAND_MARKERS)


def _is_evidence_category(category: str | None) -> bool:
    return bool(
        category and (category.startswith("skill:") or category.startswith("security:agent-review"))
    )


def _string_values(value: object) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _non_empty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
    )
