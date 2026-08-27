from __future__ import annotations

from pathlib import Path
from typing import Any, cast

MAC_CONTROL_MANIFEST_SCHEMA = "mac-control-task-manifest/v4"
MAC_CONTROL_PREVIOUS_MANIFEST_SCHEMA = "mac-control-task-manifest/v3"
MAC_CONTROL_V2_MANIFEST_SCHEMA = "mac-control-task-manifest/v2"
MAC_CONTROL_LEGACY_MANIFEST_SCHEMA = "mac-control-task-manifest/v1"
MAC_CONTROL_EVIDENCE_SCHEMA = "mac-control-task-evidence/v2"
MAC_CONTROL_PREVIOUS_EVIDENCE_SCHEMA = "mac-control-task-evidence/v1"
MAC_CONTROL_REPORT_SCHEMA = "pronto-mac-control-ideal-state/v1"
MAC_CONTROL_AUDIT_SCHEMA = "quality-runner-mac-control-audit/v1"
MAC_CONTROL_REPLAY_SCHEMA = "quality-runner-mac-control-replay/v1"
MAC_CONTROL_REPORT_RELATIVE_PATH = Path("current") / "mac-control-ideal-state.json"
MAC_CONTROL_SUMMARY_RELATIVE_PATH = Path("current") / "mac-control-summary.json"
MAC_CONTROL_DEFAULT_ROOT = Path("~/.quality-runner/fleet-audit")
MAC_CONTROL_MANIFEST_RELATIVE_PATH = Path(".mac-control") / "ideal-state.json"

CRITERIA = (
    "stable_identity",
    "correct_semantics",
    "observable_state",
    "useful_hierarchy",
    "efficient_navigation",
    "verifiable_outcomes",
    "route_flexibility",
    "stable_change_behavior",
)
OBSERVABLE_STATES = (
    "enabled",
    "focused",
    "selected",
    "expanded",
    "visible",
    "loading",
    "completed",
)
CHANGE_STATES = ("loading", "modal", "disabled", "permission_unavailable")
ROUTES = (
    "native_api",
    "adapter",
    "accessibility",
    "keyboard",
    "scrolling",
    "visual_fallback_approved",
)
PROVIDERS = (
    "native",
    "mac_control",
    "app_connector",
    "browser_connector",
    "computer_use",
    "caller",
)
METHODS = (
    "native_api",
    "adapter",
    "accessibility",
    "keyboard",
    "shortcut",
    "scroll",
    "pointer",
    "visual",
    "drag",
)
INTERACTION_MODES = ("semantic", "keyboard", "pointer", "scroll", "drag", "mixed")
ORACLE_KINDS = (
    "element_state",
    "window_state",
    "application_state",
    "task_state",
    "receipt_state",
    "provider_readback",
)
SHORTCUT_DISPOSITIONS = ("built_in_verified", "customizable_verified", "not_applicable")
SHORTCUT_CUSTOMIZATION_SURFACES = ("macos_app_shortcut", "app_managed", "chrome_extension")
SHORTCUT_CONFLICT_POLICIES = ("app_managed", "detect_before_assignment", "system_resolved")
SURFACE_KINDS = ("native_app_ui", "browser_chrome", "web_content", "os_dialog", "hybrid_transition")
SEMANTIC_EVIDENCE_LEVEL = "source_grounded"
SEMANTIC_CLAIM_KEYS = {
    "stable_identity": ("selector_kind", "selector_value", "scope", "uniqueness"),
    "correct_semantics": ("role", "accessible_name", "action"),
    "observable_state": ("property", "unavailable_behavior"),
    "useful_hierarchy": ("container", "relationship", "uniqueness"),
    "efficient_navigation": ("strategy", "entry_point"),
    "verifiable_outcomes": ("readback_provider", "property", "operator", "expected"),
    "route_flexibility": ("primary_provider", "secondary_provider", "fallback_policy"),
    "stable_change_behavior": ("scenarios", "failure_behavior"),
}
SELECTOR_KINDS = (
    "ax_identifier",
    "aria_label",
    "data_attribute",
    "dom_test_id",
    "command_id",
)
NAVIGATION_STRATEGIES = (
    "direct_semantic",
    "menu_command",
    "search",
    "shortcut",
    "typed_provider_handoff",
)
READBACK_OPERATORS = ("equals", "not_equals", "contains", "exists")
GENERIC_EXPECTED_STATES = ("visible", "readable", "available", "success", "succeeded", "completed")
FAILURE_BEHAVIORS = ("fail_closed", "block_and_explain", "provider_handoff", "retryable_no_change")
EVIDENCE_PRODUCER_KINDS = ("mac_control", "browser_connector", "app_connector")
EXECUTION_RESULTS = ("succeeded", "failed", "blocked")
VERIFICATION_RESULTS = ("passed", "failed", "blocked")
NATIVE_SURFACES = {"native_app_ui", "browser_chrome", "os_dialog"}
BROWSER_PROVIDERS = {"browser_connector"}
NATIVE_PROVIDERS = {"native", "mac_control", "app_connector"}
SOURCE_EVIDENCE_MAX_BYTES = 2 * 1024 * 1024
SOURCE_EVIDENCE_CONTEXT_RADIUS = 6_000
IMPLEMENTATION_SOURCE_SUFFIXES = {
    ".c",
    ".cpp",
    ".cs",
    ".dart",
    ".go",
    ".h",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".plist",
    ".py",
    ".rb",
    ".rs",
    ".storyboard",
    ".svelte",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".xib",
    ".yaml",
    ".yml",
}
NON_IMPLEMENTATION_SOURCE_COMPONENTS = {
    ".mac-control",
    "docs",
    "fixtures",
    "snapshots",
    "test",
    "tests",
}


class MacControlAuditError(ValueError):
    pass


def validate_manifest(manifest: object) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    manifest = object_mapping(cast(object, manifest))
    errors: list[str] = []
    schema = manifest.get("schema")
    if schema not in {
        MAC_CONTROL_MANIFEST_SCHEMA,
        MAC_CONTROL_PREVIOUS_MANIFEST_SCHEMA,
        MAC_CONTROL_V2_MANIFEST_SCHEMA,
        MAC_CONTROL_LEGACY_MANIFEST_SCHEMA,
    }:
        errors.append(
            f"schema must be {MAC_CONTROL_MANIFEST_SCHEMA}, "
            f"{MAC_CONTROL_PREVIOUS_MANIFEST_SCHEMA}, {MAC_CONTROL_V2_MANIFEST_SCHEMA}, "
            f"or {MAC_CONTROL_LEGACY_MANIFEST_SCHEMA}"
        )
    applicability = normalize_applicability(manifest.get("applicability"))
    if applicability is None:
        errors.append("applicability must be applicable or not_applicable")
    if not nonempty(manifest.get("repository_id")):
        errors.append("repository_id is required")
    if not nonempty(manifest.get("repository_name")):
        errors.append("repository_name is required")
    if not nonempty(manifest.get("applicability_reason")):
        errors.append("applicability_reason is required")
    if applicability == "not_applicable":
        if manifest.get("tasks") not in (None, []):
            errors.append("not_applicable manifests must not declare tasks")
        return errors
    criteria = manifest.get("criteria")
    if schema == MAC_CONTROL_MANIFEST_SCHEMA:
        if criteria not in (None, {}):
            errors.append(
                "v4 criteria must be empty; semantic dimensions are derived from task evidence"
            )
    elif not isinstance(criteria, dict):
        errors.append("criteria must be an object")
    else:
        criteria = object_mapping(cast(object, criteria))
        for criterion in CRITERIA:
            if criteria.get(criterion) is not True:
                errors.append(f"criteria.{criterion} must be true")
        for criterion in criteria:
            if criterion not in CRITERIA:
                errors.append(f"criteria contains unsupported key {criterion}")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("applicable manifests must declare at least one task")
        return errors
    tasks = cast(list[object], tasks)
    task_ids: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object")
            continue
        task = object_mapping(cast(object, task))
        task_id = str(task.get("task_id", "")).strip()
        label = task_id or f"tasks[{index}]"
        if not task_id:
            errors.append(f"{label} requires task_id")
        elif task_id in task_ids:
            errors.append(f"task {task_id} is duplicated")
        task_ids.add(task_id)
        for key in (
            "stable_target_id",
            "hierarchy",
            "semantic_action",
            "observable_postcondition",
            "navigation_strategy",
        ):
            if not nonempty(task.get(key)):
                errors.append(f"task {label} requires {key}")
        accessibility = task.get("accessibility")
        if accessibility is not None and not isinstance(accessibility, dict):
            errors.append(f"task {label} accessibility must be an object")
        elif isinstance(accessibility, dict):
            accessibility = object_mapping(cast(object, accessibility))
            if not any(nonempty(accessibility.get(key)) for key in ("identifier", "label", "role")):
                errors.append(f"task {label} accessibility needs identifier, label, or role")
        if schema in {
            MAC_CONTROL_MANIFEST_SCHEMA,
            MAC_CONTROL_PREVIOUS_MANIFEST_SCHEMA,
            MAC_CONTROL_V2_MANIFEST_SCHEMA,
        }:
            _validate_v2_task(task, label, errors)
            if schema in {MAC_CONTROL_MANIFEST_SCHEMA, MAC_CONTROL_PREVIOUS_MANIFEST_SCHEMA}:
                _validate_shortcut_acceleration(task, label, errors)
            if schema == MAC_CONTROL_MANIFEST_SCHEMA:
                _validate_v4_task(task, label, errors)
            continue
        if not nonempty(task.get("selected_route")):
            errors.append(f"task {label} requires selected_route")
        if str(task.get("navigation_strategy", "")).strip().casefold() in {
            "sequential_tabbing",
            "sequential tabbing",
        }:
            errors.append(f"task {label} must not rely on sequential tabbing")
        _require_values(
            task.get("observable_states"),
            OBSERVABLE_STATES,
            f"task {label} observable_states",
            errors,
        )
        _require_values(
            task.get("change_states"), CHANGE_STATES, f"task {label} change_states", errors
        )
        eligible = task.get("eligible_routes")
        if not isinstance(eligible, list) or not eligible:
            errors.append(f"task {label} requires eligible_routes")
        else:
            eligible = cast(list[object], eligible)
            normalized_routes = {
                normalize_token(item) for item in eligible if isinstance(item, str)
            }
            for route in normalized_routes - set(ROUTES):
                errors.append(f"task {label} has unsupported route {route}")
            if normalize_token(task.get("selected_route")) not in normalized_routes:
                errors.append(f"task {label} selected_route must be eligible")
    return errors


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize_applicability(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().casefold().replace("-", "_").replace(" ", "_")
    return token if token in {"applicable", "not_applicable"} else None


def normalize_token(value: object) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")


def bool_mapping(value: object) -> dict[str, bool]:
    return (
        {
            str(key): child
            for key, child in cast(dict[object, object], value).items()
            if isinstance(child, bool)
        }
        if isinstance(value, dict)
        else {}
    )


def string_list(value: object) -> list[str]:
    return (
        sorted(
            {item for item in cast(list[object], value) if isinstance(item, str) and item.strip()}
        )
        if isinstance(value, list)
        else []
    )


def string_mapping(value: object) -> dict[str, str]:
    return (
        {
            str(key): child
            for key, child in cast(dict[object, object], value).items()
            if isinstance(key, str) and isinstance(child, str)
        }
        if isinstance(value, dict)
        else {}
    )


def object_mapping(value: object) -> dict[str, Any]:
    return (
        {str(key): child for key, child in cast(dict[object, object], value).items()}
        if isinstance(value, dict)
        else {}
    )


def object_list(value: object) -> list[dict[str, Any]]:
    return (
        [
            object_mapping(cast(object, item))
            for item in cast(list[object], value)
            if isinstance(item, dict)
        ]
        if isinstance(value, list)
        else []
    )


def _require_values(
    value: object, required: tuple[str, ...], label: str, errors: list[str]
) -> None:
    values: set[str] = (
        {normalize_token(item) for item in cast(list[object], value)}
        if isinstance(value, list)
        else set()
    )
    for expected in required:
        if expected not in values:
            errors.append(f"{label} is missing {expected}")


def task_entries(value: object) -> list[dict[str, Any]]:
    from quality_runner.fleet.mac_control_task_evidence import task_entries as implementation

    return implementation(value)


def merge_task_evidence(
    tasks: list[dict[str, Any]],
    value: object,
    errors: list[str],
    *,
    evidence_schema: str,
) -> None:
    from quality_runner.fleet.mac_control_task_evidence import (
        merge_task_evidence as implementation,
    )

    implementation(tasks, value, errors, evidence_schema=evidence_schema)


def validate_evidence_producer(value: object) -> list[str]:
    from quality_runner.fleet.mac_control_task_evidence import (
        validate_evidence_producer as implementation,
    )

    return implementation(value)


def semantic_source_paths(manifest: object) -> list[str]:
    from quality_runner.fleet.mac_control_task_evidence import (
        semantic_source_paths as implementation,
    )

    return implementation(manifest)


def _validate_v2_task(task: dict[str, Any], label: str, errors: list[str]) -> None:
    from quality_runner.fleet.mac_control_task_validation import validate_v2_task

    validate_v2_task(task, label, errors)


def _validate_shortcut_acceleration(task: dict[str, Any], label: str, errors: list[str]) -> None:
    from quality_runner.fleet.mac_control_task_validation import (
        validate_shortcut_acceleration,
    )

    validate_shortcut_acceleration(task, label, errors)


def _validate_v4_task(task: dict[str, Any], label: str, errors: list[str]) -> None:
    from quality_runner.fleet.mac_control_semantic import validate_v4_task

    validate_v4_task(task, label, errors)


def evaluate_semantic_evidence(repository_root: Path, manifest: object) -> dict[str, Any]:
    from quality_runner.fleet.mac_control_semantic import (
        evaluate_semantic_evidence as implementation,
    )

    return implementation(repository_root, manifest)


def require_accounting(
    declared: object,
    exemptions: object,
    supported: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    present: set[str] = (
        {normalize_token(item) for item in cast(list[object], declared)}
        if isinstance(declared, list)
        else set()
    )
    exemption_map: dict[str, str] = (
        {
            normalize_token(key): value
            for key, value in cast(dict[object, object], exemptions).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        if isinstance(exemptions, dict)
        else {}
    )
    for state in present - set(supported):
        errors.append(f"{label} contains unsupported state {state}")
    for state in set(exemption_map) - set(supported):
        errors.append(f"{label} exempts unsupported state {state}")
    for state in present.intersection(exemption_map):
        errors.append(f"{label} must not both declare and exempt {state}")
    for state in supported:
        if state not in present and state not in exemption_map:
            errors.append(f"{label} must declare or exempt {state}")
    for state, reason in exemption_map.items():
        if not reason.strip():
            errors.append(f"{label} exemption for {state} requires a reason")
