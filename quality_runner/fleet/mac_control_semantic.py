from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.fleet.mac_control_contracts import (
    BROWSER_PROVIDERS,
    CHANGE_STATES,
    CRITERIA,
    FAILURE_BEHAVIORS,
    GENERIC_EXPECTED_STATES,
    IMPLEMENTATION_SOURCE_SUFFIXES,
    MAC_CONTROL_MANIFEST_SCHEMA,
    NATIVE_PROVIDERS,
    NATIVE_SURFACES,
    NAVIGATION_STRATEGIES,
    NON_IMPLEMENTATION_SOURCE_COMPONENTS,
    READBACK_OPERATORS,
    SELECTOR_KINDS,
    SEMANTIC_CLAIM_KEYS,
    SEMANTIC_EVIDENCE_LEVEL,
    SOURCE_EVIDENCE_CONTEXT_RADIUS,
    SOURCE_EVIDENCE_MAX_BYTES,
    SURFACE_KINDS,
    _nonempty,
    _normalize_applicability,
    _normalize_token,
    bool_mapping,
    object_list,
    object_mapping,
    string_list,
)


def validate_v4_task(task: dict[str, Any], label: str, errors: list[str]) -> None:
    surface_kind = _normalize_token(task.get("surface_kind"))
    if surface_kind not in SURFACE_KINDS:
        errors.append(f"task {label} surface_kind must be one of {', '.join(SURFACE_KINDS)}")

    candidates = object_list(task.get("route_candidates"))
    providers = {_normalize_token(candidate.get("provider")) for candidate in candidates}
    if len(candidates) < 2:
        errors.append(f"task {label} route_flexibility requires at least two route candidates")
    if surface_kind == "web_content":
        if not providers.intersection(BROWSER_PROVIDERS):
            errors.append(f"task {label} web_content requires a browser_connector route")
        if providers.intersection(NATIVE_PROVIDERS):
            errors.append(f"task {label} web_content must not claim a native Mac Control route")
    elif surface_kind in NATIVE_SURFACES:
        if not providers.intersection(NATIVE_PROVIDERS):
            errors.append(f"task {label} {surface_kind} requires a native semantic route")
        if providers.intersection(BROWSER_PROVIDERS):
            errors.append(f"task {label} {surface_kind} must not claim a browser_connector route")
    elif surface_kind == "hybrid_transition" and (
        not providers.intersection(BROWSER_PROVIDERS)
        or not providers.intersection(NATIVE_PROVIDERS)
    ):
        errors.append(f"task {label} hybrid_transition requires native and browser routes")

    accessibility = object_mapping(task.get("accessibility"))
    for candidate in candidates:
        method = _normalize_token(candidate.get("method"))
        if method == "accessibility" and not _nonempty(accessibility.get("identifier")):
            errors.append(f"task {label} accessibility route requires accessibility.identifier")
        if method in {"pointer", "visual", "drag"} and _normalize_token(
            task.get("fallback_policy")
        ) not in {"explicit_handoff", "fresh_state_handoff"}:
            errors.append(
                f"task {label} {method} route requires explicit_handoff or fresh_state_handoff"
            )

    oracle = object_mapping(task.get("verification_oracle"))
    if _normalize_token(oracle.get("expected_state")) in GENERIC_EXPECTED_STATES:
        errors.append(
            f"task {label} verification_oracle expected_state must name a machine-checkable value"
        )

    semantic_evidence = task.get("semantic_evidence")
    if not isinstance(semantic_evidence, dict):
        errors.append(f"task {label} requires semantic_evidence")
        return
    for criterion in semantic_evidence:
        if criterion not in CRITERIA:
            errors.append(f"task {label} semantic_evidence contains unsupported key {criterion}")
    fingerprints: set[str] = set()
    for criterion in CRITERIA:
        evidence = semantic_evidence.get(criterion)
        evidence_label = f"task {label} semantic_evidence.{criterion}"
        if not isinstance(evidence, dict):
            errors.append(f"{evidence_label} is required")
            continue
        if _normalize_token(evidence.get("level")) != SEMANTIC_EVIDENCE_LEVEL:
            errors.append(f"{evidence_label}.level must be {SEMANTIC_EVIDENCE_LEVEL}")
        claims = evidence.get("claims")
        if not isinstance(claims, dict):
            errors.append(f"{evidence_label}.claims must be an object")
            claims = {}
        for key in SEMANTIC_CLAIM_KEYS[criterion]:
            if not _nonempty(claims.get(key)):
                errors.append(f"{evidence_label}.claims.{key} is required")
        _validate_semantic_claims(criterion, claims, task, providers, evidence_label, errors)
        refs = evidence.get("source_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{evidence_label}.source_refs requires at least one source reference")
        else:
            for ref_index, ref in enumerate(refs):
                _validate_source_ref(ref, f"{evidence_label}.source_refs[{ref_index}]", errors)
        fingerprint = json.dumps(
            {"claims": claims, "source_refs": refs}, sort_keys=True, separators=(",", ":")
        )
        if fingerprint in fingerprints:
            errors.append(f"task {label} semantic evidence must be criterion-specific, not cloned")
        fingerprints.add(fingerprint)


def _validate_semantic_claims(
    criterion: str,
    claims: dict[str, Any],
    task: dict[str, Any],
    providers: set[str],
    label: str,
    errors: list[str],
) -> None:
    if criterion == "stable_identity":
        selector_kind = _normalize_token(claims.get("selector_kind"))
        if selector_kind not in SELECTOR_KINDS:
            errors.append(f"{label}.claims.selector_kind is unsupported")
        surface_kind = _normalize_token(task.get("surface_kind"))
        if surface_kind == "web_content" and selector_kind not in {
            "aria_label",
            "data_attribute",
            "dom_test_id",
        }:
            errors.append(f"{label}.claims.selector_kind must be DOM-native for web_content")
        if surface_kind in NATIVE_SURFACES and selector_kind not in {
            "ax_identifier",
            "command_id",
        }:
            errors.append(f"{label}.claims.selector_kind must be native for {surface_kind}")
        if (
            str(claims.get("selector_value", "")).strip()
            != str(task.get("stable_target_id", "")).strip()
        ):
            errors.append(f"{label}.claims.selector_value must equal stable_target_id")
        if _normalize_token(claims.get("uniqueness")) != "exactly_one":
            errors.append(f"{label}.claims.uniqueness must be exactly_one")
    elif (
        criterion == "useful_hierarchy"
        and _normalize_token(claims.get("uniqueness")) != "exactly_one"
    ):
        errors.append(f"{label}.claims.uniqueness must be exactly_one")
    elif criterion == "efficient_navigation":
        strategy = _normalize_token(claims.get("strategy"))
        if strategy not in NAVIGATION_STRATEGIES:
            errors.append(f"{label}.claims.strategy is unsupported")
        if strategy != _normalize_token(task.get("navigation_strategy")):
            errors.append(f"{label}.claims.strategy must match task navigation_strategy")
        if (
            strategy == "direct_semantic"
            and str(claims.get("entry_point", "")).strip()
            != str(task.get("stable_target_id", "")).strip()
        ):
            errors.append(f"{label}.claims.entry_point must equal stable_target_id")
    elif criterion == "verifiable_outcomes":
        if _normalize_token(claims.get("operator")) not in READBACK_OPERATORS:
            errors.append(f"{label}.claims.operator is unsupported")
        if _normalize_token(claims.get("expected")) in GENERIC_EXPECTED_STATES:
            errors.append(f"{label}.claims.expected must name a machine-checkable value")
        if (
            str(claims.get("expected", "")).strip()
            != str(
                object_mapping(task.get("verification_oracle")).get("expected_state", "")
            ).strip()
        ):
            errors.append(f"{label}.claims.expected must match verification_oracle.expected_state")
        if _normalize_token(claims.get("readback_provider")) not in providers:
            errors.append(f"{label}.claims.readback_provider must match a route candidate")
    elif criterion == "route_flexibility":
        primary = _normalize_token(claims.get("primary_provider"))
        secondary = _normalize_token(claims.get("secondary_provider"))
        if primary not in providers:
            errors.append(f"{label}.claims.primary_provider must match a route candidate")
        if secondary not in providers:
            errors.append(f"{label}.claims.secondary_provider must match a route candidate")
        if primary == secondary:
            errors.append(f"{label}.claims.secondary_provider must differ from primary_provider")
        if _normalize_token(claims.get("fallback_policy")) != _normalize_token(
            task.get("fallback_policy")
        ):
            errors.append(f"{label}.claims.fallback_policy must match the task fallback_policy")
    elif criterion == "stable_change_behavior":
        scenarios = {
            _normalize_token(value)
            for value in str(claims.get("scenarios", "")).split(",")
            if value.strip()
        }
        for state in CHANGE_STATES:
            if state not in scenarios:
                errors.append(f"{label}.claims.scenarios is missing {state}")
        if _normalize_token(claims.get("failure_behavior")) not in FAILURE_BEHAVIORS:
            errors.append(f"{label}.claims.failure_behavior is unsupported")


def _validate_source_ref(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    path = str(value.get("path", "")).strip()
    path_value = Path(path)
    if not path or path_value.is_absolute() or ".." in path_value.parts:
        errors.append(f"{label}.path must be a repository-relative path without traversal")
    normalized_parts = {part.casefold() for part in path_value.parts}
    if normalized_parts.intersection(NON_IMPLEMENTATION_SOURCE_COMPONENTS):
        errors.append(
            f"{label}.path must reference implementation source, not docs, tests, or fixtures"
        )
    if path_value.suffix.casefold() not in IMPLEMENTATION_SOURCE_SUFFIXES:
        errors.append(f"{label}.path must use a supported implementation-source extension")
    if not _nonempty(value.get("anchor")):
        errors.append(f"{label}.anchor is required")
    tokens = value.get("evidence_tokens")
    if not isinstance(tokens, list) or not tokens or any(not _nonempty(token) for token in tokens):
        errors.append(f"{label}.evidence_tokens requires non-empty source tokens")


def evaluate_semantic_evidence(repository_root: Path, manifest: object) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        return _empty_semantic_evaluation("not_source_grounded")
    applicability = _normalize_applicability(manifest.get("applicability"))
    if applicability == "not_applicable":
        return _empty_semantic_evaluation("not_applicable", criteria_total=0)
    schema = str(manifest.get("schema", "")).strip()
    if schema != MAC_CONTROL_MANIFEST_SCHEMA:
        criteria = bool_mapping(manifest.get("criteria"))
        result = _empty_semantic_evaluation("declaration_only")
        result["declaration_criteria_count"] = sum(
            1 for criterion in CRITERIA if criteria.get(criterion) is True
        )
        result["dimension_states"] = {
            criterion: {
                "status": "declaration_only",
                "grounded_task_count": 0,
                "task_count": len(object_list(manifest.get("tasks"))),
                "evidence": [],
                "failure_reasons": [
                    f"{schema or 'missing schema'} is declaration-only; migrate to {MAC_CONTROL_MANIFEST_SCHEMA}"
                ],
            }
            for criterion in CRITERIA
        }
        return result

    tasks = object_list(manifest.get("tasks"))
    cache: dict[Path, tuple[str | None, str | None]] = {}
    dimension_states: dict[str, dict[str, Any]] = {}
    all_errors: list[str] = []
    all_evidence: list[str] = []
    criteria: dict[str, bool] = {}
    root = repository_root.resolve()
    for criterion in CRITERIA:
        grounded_tasks = 0
        criterion_errors: list[str] = []
        criterion_evidence: list[str] = []
        for task in tasks:
            task_id = str(task.get("task_id", "unnamed"))
            semantic_evidence = object_mapping(task.get("semantic_evidence"))
            evidence = object_mapping(semantic_evidence.get(criterion))
            refs = evidence.get("source_refs")
            if not isinstance(refs, list) or not refs:
                criterion_errors.append(f"task {task_id} {criterion} has no source references")
                continue
            task_errors: list[str] = []
            for ref in refs:
                ref_errors, ref_evidence = _ground_source_ref(root, ref, cache)
                task_errors.extend(f"task {task_id} {criterion}: {error}" for error in ref_errors)
                if ref_evidence:
                    criterion_evidence.append(ref_evidence)
            if task_errors:
                criterion_errors.extend(task_errors)
            else:
                grounded_tasks += 1
        grounded = bool(tasks) and grounded_tasks == len(tasks)
        criteria[criterion] = grounded
        dimension_states[criterion] = {
            "status": "source_grounded" if grounded else "not_source_grounded",
            "grounded_task_count": grounded_tasks,
            "task_count": len(tasks),
            "evidence": sorted(set(criterion_evidence)),
            "failure_reasons": sorted(set(criterion_errors)),
        }
        all_errors.extend(criterion_errors)
        all_evidence.extend(criterion_evidence)
    passed = sum(1 for criterion in CRITERIA if criteria.get(criterion) is True)
    level = (
        "source_grounded"
        if passed == len(CRITERIA)
        else "partially_source_grounded"
        if passed
        else "not_source_grounded"
    )
    return {
        "evidence_level": level,
        "criteria": criteria,
        "criteria_passed_count": passed,
        "criteria_total": len(CRITERIA),
        "declaration_criteria_count": 0,
        "dimension_states": dimension_states,
        "grounding_errors": sorted(set(all_errors)),
        "evidence": sorted(set(all_evidence)),
    }


def _empty_semantic_evaluation(level: str, *, criteria_total: int | None = None) -> dict[str, Any]:
    total = len(CRITERIA) if criteria_total is None else criteria_total
    return {
        "evidence_level": level,
        "criteria": {criterion: False for criterion in CRITERIA} if total else {},
        "criteria_passed_count": 0,
        "criteria_total": total,
        "declaration_criteria_count": 0,
        "dimension_states": {},
        "grounding_errors": [],
        "evidence": [],
    }


def _ground_source_ref(
    repository_root: Path,
    value: object,
    cache: dict[Path, tuple[str | None, str | None]],
) -> tuple[list[str], str | None]:
    if not isinstance(value, dict):
        return ["source reference is not an object"], None
    relative = Path(str(value.get("path", "")).strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        return ["source path is not repository-relative"], None
    unresolved_source = repository_root / relative
    if unresolved_source.is_symlink():
        return [f"source file must not be a symlink: {relative.as_posix()}"], None
    source = unresolved_source.resolve()
    try:
        source.relative_to(repository_root)
    except ValueError:
        return [f"source path escapes repository: {relative.as_posix()}"], None
    if source not in cache:
        if not source.is_file():
            cache[source] = (None, f"source file is unavailable: {relative.as_posix()}")
        elif source.stat().st_size > SOURCE_EVIDENCE_MAX_BYTES:
            cache[source] = (None, f"source file exceeds 2 MiB: {relative.as_posix()}")
        else:
            try:
                cache[source] = (source.read_text(encoding="utf-8"), None)
            except (OSError, UnicodeError) as error:
                cache[source] = (
                    None,
                    f"source file is unreadable: {relative.as_posix()} ({error})",
                )
    contents, read_error = cache[source]
    if read_error:
        return [read_error], None
    assert contents is not None
    anchor = str(value.get("anchor", "")).strip()
    tokens = string_list(value.get("evidence_tokens"))
    errors: list[str] = []
    anchor_count = contents.count(anchor) if anchor else 0
    if anchor_count == 0:
        errors.append(f"anchor not found in {relative.as_posix()}: {anchor or '<missing>'}")
        scoped_contents = ""
    elif anchor_count > 1:
        errors.append(f"anchor is not unique in {relative.as_posix()}: {anchor}")
        scoped_contents = ""
    else:
        anchor_index = contents.index(anchor)
        scoped_contents = contents[
            max(0, anchor_index - SOURCE_EVIDENCE_CONTEXT_RADIUS) : anchor_index
            + len(anchor)
            + SOURCE_EVIDENCE_CONTEXT_RADIUS
        ]
    for token in tokens:
        if token not in scoped_contents:
            errors.append(f"evidence token not found near anchor in {relative.as_posix()}: {token}")
    evidence = f"source:{relative.as_posix()}#{anchor}" if not errors else None
    return errors, evidence
