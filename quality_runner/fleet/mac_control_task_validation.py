from __future__ import annotations

from typing import Any

from quality_runner.fleet.mac_control_contracts import (
    CHANGE_STATES,
    INTERACTION_MODES,
    METHODS,
    OBSERVABLE_STATES,
    ORACLE_KINDS,
    PROVIDERS,
    SHORTCUT_CONFLICT_POLICIES,
    SHORTCUT_CUSTOMIZATION_SURFACES,
    SHORTCUT_DISPOSITIONS,
    _nonempty,
    _normalize_token,
    _require_accounting,
)


def validate_v2_task(task: dict[str, Any], label: str, errors: list[str]) -> None:
    if _nonempty(task.get("selected_route")):
        errors.append(f"task {label} selected_route is runtime evidence, not a manifest field")

    _require_accounting(
        task.get("observable_states"),
        task.get("state_exemptions"),
        OBSERVABLE_STATES,
        f"task {label} observable_states",
        errors,
    )
    _require_accounting(
        task.get("change_states"),
        task.get("change_state_exemptions"),
        CHANGE_STATES,
        f"task {label} change_states",
        errors,
    )

    if not _nonempty(task.get("focus_policy")):
        errors.append(f"task {label} requires focus_policy")
    if not _nonempty(task.get("foreground_postcondition")):
        errors.append(f"task {label} requires foreground_postcondition")
    if not _nonempty(task.get("fallback_policy")):
        errors.append(f"task {label} requires fallback_policy")

    oracle = task.get("verification_oracle")
    if not isinstance(oracle, dict):
        errors.append(f"task {label} verification_oracle must be an object")
    else:
        for key in ("oracle_id", "expected_state"):
            if not _nonempty(oracle.get(key)):
                errors.append(f"task {label} verification_oracle requires {key}")
        kind = _normalize_token(oracle.get("kind"))
        if kind not in ORACLE_KINDS:
            errors.append(f"task {label} verification_oracle kind is unsupported: {kind or 'missing'}")
        if oracle.get("independent_readback") is not True:
            errors.append(f"task {label} verification_oracle requires independent_readback true")

    candidates = task.get("route_candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append(f"task {label} requires route_candidates")
        return
    candidate_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        candidate_label = f"task {label} route_candidates[{index}]"
        if not isinstance(candidate, dict):
            errors.append(f"{candidate_label} must be an object")
            continue
        candidate_id = str(candidate.get("id", "")).strip()
        if not candidate_id:
            errors.append(f"{candidate_label} requires id")
        elif candidate_id in candidate_ids:
            errors.append(f"task {label} route candidate {candidate_id} is duplicated")
        candidate_ids.add(candidate_id)
        _require_supported_token(candidate, "provider", PROVIDERS, candidate_label, errors)
        _require_supported_token(candidate, "method", METHODS, candidate_label, errors)
        _require_supported_token(
            candidate, "interaction_mode", INTERACTION_MODES, candidate_label, errors
        )


def validate_shortcut_acceleration(
    task: dict[str, Any], label: str, errors: list[str]
) -> None:
    shortcut = task.get("shortcut_acceleration")
    if not isinstance(shortcut, dict):
        errors.append(f"task {label} shortcut_acceleration must be an object")
        return

    disposition = _normalize_token(shortcut.get("disposition"))
    if disposition not in SHORTCUT_DISPOSITIONS:
        errors.append(
            f"task {label} shortcut_acceleration disposition is unsupported: "
            f"{disposition or 'missing'}"
        )
        return
    if disposition == "not_applicable":
        if not _nonempty(shortcut.get("reason")):
            errors.append(f"task {label} not_applicable shortcut requires a reason")
        return

    if not _nonempty(shortcut.get("command_id")):
        errors.append(f"task {label} shortcut_acceleration requires command_id")
    conflict_policy = _normalize_token(shortcut.get("conflict_policy"))
    if conflict_policy not in SHORTCUT_CONFLICT_POLICIES:
        errors.append(
            f"task {label} shortcut_acceleration conflict_policy is unsupported: "
            f"{conflict_policy or 'missing'}"
        )
    if shortcut.get("contextual_availability") is not True:
        errors.append(f"task {label} shortcut_acceleration requires contextual_availability true")

    if disposition == "built_in_verified":
        if not _nonempty(shortcut.get("chord")):
            errors.append(f"task {label} built_in_verified shortcut requires chord")
        return

    customization_surface = _normalize_token(shortcut.get("customization_surface"))
    if customization_surface not in SHORTCUT_CUSTOMIZATION_SURFACES:
        errors.append(
            f"task {label} customizable shortcut customization_surface is unsupported: "
            f"{customization_surface or 'missing'}"
        )
    if not _nonempty(shortcut.get("menu_path")):
        errors.append(f"task {label} customizable shortcut requires an exact menu_path")
    if shortcut.get("reversible_assignment") is not True:
        errors.append(f"task {label} customizable shortcut requires reversible_assignment true")


def _require_supported_token(
    value: dict[str, Any],
    key: str,
    supported: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    token = _normalize_token(value.get(key))
    if token not in supported:
        errors.append(f"{label} {key} is unsupported: {token or 'missing'}")
