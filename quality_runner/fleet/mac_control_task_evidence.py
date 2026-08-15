from __future__ import annotations

from typing import Any

from quality_runner.fleet.mac_control_contracts import (
    EVIDENCE_PRODUCER_KINDS,
    EXECUTION_RESULTS,
    MAC_CONTROL_EVIDENCE_SCHEMA,
    MAC_CONTROL_MANIFEST_RELATIVE_PATH,
    MAC_CONTROL_PREVIOUS_EVIDENCE_SCHEMA,
    VERIFICATION_RESULTS,
    _nonempty,
    _normalize_token,
    object_list,
    object_mapping,
    string_list,
    string_mapping,
)


def task_entries(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries: list[dict[str, Any]] = []
    for task in value:
        if not isinstance(task, dict):
            continue
        entries.append(
            {
                "task_id": str(task.get("task_id", "")),
                "surface_kind": str(task.get("surface_kind", "")),
                "stable_target_id": str(task.get("stable_target_id", "")),
                "hierarchy": str(task.get("hierarchy", "")),
                "semantic_action": str(task.get("semantic_action", "")),
                "observable_postcondition": str(task.get("observable_postcondition", "")),
                "observable_states": string_list(task.get("observable_states")),
                "navigation_strategy": str(task.get("navigation_strategy", "")),
                "eligible_routes": string_list(task.get("eligible_routes")),
                "selected_route": str(task.get("selected_route", "")),
                "change_states": string_list(task.get("change_states")),
                "accessibility": object_mapping(task.get("accessibility")),
                "state_exemptions": string_mapping(task.get("state_exemptions")),
                "change_state_exemptions": string_mapping(task.get("change_state_exemptions")),
                "focus_policy": str(task.get("focus_policy", "")),
                "foreground_postcondition": str(task.get("foreground_postcondition", "")),
                "fallback_policy": str(task.get("fallback_policy", "")),
                "verification_oracle": object_mapping(task.get("verification_oracle")),
                "route_candidates": object_list(task.get("route_candidates")),
                "shortcut_acceleration": object_mapping(task.get("shortcut_acceleration")),
                "semantic_evidence": object_mapping(task.get("semantic_evidence")),
                "attempts": 0,
                "successes": 0,
                "evidence": [],
                "measurement_valid": False,
                "measurement_errors": [],
            }
        )
    return entries


def merge_task_evidence(
    tasks: list[dict[str, Any]],
    value: object,
    errors: list[str],
    *,
    evidence_schema: str,
) -> None:
    by_id = {task.get("task_id"): task for task in tasks}
    if not isinstance(value, list):
        errors.append("evidence sidecar tasks must be an array")
        return
    seen_task_ids: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            errors.append("evidence task entry must be an object")
            continue
        task_id = str(item.get("task_id", ""))
        task = by_id.get(task_id)
        if task is None:
            errors.append(f"evidence:unknown_task={task_id or 'unnamed'}")
            continue
        if task_id in seen_task_ids:
            errors.append(f"evidence task {task_id} is duplicated")
            continue
        seen_task_ids.add(task_id)
        if evidence_schema != MAC_CONTROL_EVIDENCE_SCHEMA:
            _merge_legacy_task_evidence(task, item)
            task["measurement_errors"] = [
                f"{MAC_CONTROL_PREVIOUS_EVIDENCE_SCHEMA} is readable but cannot satisfy live measurement"
            ]
            continue
        _merge_v2_task_evidence(task, item, errors)


def validate_evidence_producer(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["evidence sidecar producer must be an object"]
    errors: list[str] = []
    if not _nonempty(value.get("id")):
        errors.append("evidence sidecar producer.id is required")
    if _normalize_token(value.get("kind")) not in EVIDENCE_PRODUCER_KINDS:
        errors.append(
            "evidence sidecar producer.kind must be mac_control, browser_connector, or app_connector"
        )
    if not _nonempty(value.get("version")):
        errors.append("evidence sidecar producer.version is required")
    return errors


def semantic_source_paths(manifest: object) -> list[str]:
    if not isinstance(manifest, dict):
        return []
    paths = {MAC_CONTROL_MANIFEST_RELATIVE_PATH.as_posix()}
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        return sorted(paths)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        evidence = task.get("semantic_evidence")
        if not isinstance(evidence, dict):
            continue
        for claim in evidence.values():
            if not isinstance(claim, dict):
                continue
            refs = claim.get("source_refs")
            if not isinstance(refs, list):
                continue
            for ref in refs:
                if isinstance(ref, dict) and _nonempty(ref.get("path")):
                    paths.add(str(ref["path"]).strip())
    return sorted(paths)


def _merge_legacy_task_evidence(task: dict[str, Any], item: dict[str, Any]) -> None:
    attempts = item.get("attempts")
    successes = item.get("successes")
    if isinstance(attempts, int) and attempts >= 0:
        task["attempts"] = attempts
    if isinstance(successes, int) and successes >= 0:
        task["successes"] = successes
    if isinstance(item.get("selected_route"), str) and item["selected_route"].strip():
        task["selected_route"] = item["selected_route"].strip()
    task["evidence"] = string_list(item.get("evidence"))


def _merge_v2_task_evidence(task: dict[str, Any], item: dict[str, Any], errors: list[str]) -> None:
    task_id = str(task.get("task_id") or "unnamed")
    attempts = item.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        message = f"evidence task {task_id} requires at least one structured attempt"
        errors.append(message)
        task["measurement_errors"] = [message]
        return
    candidates = {
        str(candidate.get("id", "")).strip(): candidate
        for candidate in object_list(task.get("route_candidates"))
        if _nonempty(candidate.get("id"))
    }
    oracle = object_mapping(task.get("verification_oracle"))
    semantic = object_mapping(task.get("semantic_evidence"))
    outcome_claims = object_mapping(
        object_mapping(semantic.get("verifiable_outcomes")).get("claims")
    )
    seen_attempt_ids: set[str] = set()
    task_errors: list[str] = []
    success_count = 0
    evidence: list[str] = []
    selected_routes: set[str] = set()
    for index, attempt in enumerate(attempts):
        label = f"evidence task {task_id} attempts[{index}]"
        if not isinstance(attempt, dict):
            task_errors.append(f"{label} must be an object")
            continue
        attempt_id = str(attempt.get("attempt_id", "")).strip()
        if not attempt_id:
            task_errors.append(f"{label}.attempt_id is required")
        elif attempt_id in seen_attempt_ids:
            task_errors.append(f"{label}.attempt_id {attempt_id} is duplicated")
        seen_attempt_ids.add(attempt_id)
        selected_route = str(attempt.get("selected_route", "")).strip()
        candidate = candidates.get(selected_route)
        if candidate is None:
            task_errors.append(f"{label}.selected_route must match a declared route candidate")
        else:
            selected_routes.add(selected_route)
        for timestamp in ("started_at", "completed_at"):
            if not _nonempty(attempt.get(timestamp)):
                task_errors.append(f"{label}.{timestamp} is required")
        execution_result = _normalize_token(attempt.get("execution_result"))
        verification_result = _normalize_token(attempt.get("verification_result"))
        if execution_result not in EXECUTION_RESULTS:
            task_errors.append(f"{label}.execution_result is unsupported")
        if verification_result not in VERIFICATION_RESULTS:
            task_errors.append(f"{label}.verification_result is unsupported")

        receipt = object_mapping(attempt.get("receipt"))
        receipt_id = str(receipt.get("receipt_id", "")).strip()
        if not receipt_id:
            task_errors.append(f"{label}.receipt.receipt_id is required")
        if not _nonempty(receipt.get("schema")):
            task_errors.append(f"{label}.receipt.schema is required")
        receipt_provider = _normalize_token(receipt.get("provider"))
        receipt_method = _normalize_token(receipt.get("method"))
        if candidate is not None:
            if receipt_provider != _normalize_token(candidate.get("provider")):
                task_errors.append(
                    f"{label}.receipt.provider must match the selected route provider"
                )
            if receipt_method != _normalize_token(candidate.get("method")):
                task_errors.append(f"{label}.receipt.method must match the selected route method")
        receipt_digest = str(receipt.get("sha256", "")).strip().casefold()
        if len(receipt_digest) != 64 or any(
            character not in "0123456789abcdef" for character in receipt_digest
        ):
            task_errors.append(f"{label}.receipt.sha256 must be a 64-character hex digest")

        postcondition = object_mapping(attempt.get("postcondition"))
        if (
            str(postcondition.get("oracle_id", "")).strip()
            != str(oracle.get("oracle_id", "")).strip()
        ):
            task_errors.append(f"{label}.postcondition.oracle_id must match the task oracle")
        if _normalize_token(postcondition.get("kind")) != _normalize_token(oracle.get("kind")):
            task_errors.append(f"{label}.postcondition.kind must match the task oracle")
        expected = str(postcondition.get("expected_state", "")).strip()
        if expected != str(oracle.get("expected_state", "")).strip():
            task_errors.append(f"{label}.postcondition.expected_state must match the task oracle")
        operator = _normalize_token(postcondition.get("operator"))
        if operator != _normalize_token(outcome_claims.get("operator")):
            task_errors.append(
                f"{label}.postcondition.operator must match verifiable_outcomes evidence"
            )
        readback_provider = _normalize_token(postcondition.get("readback_provider"))
        if readback_provider != _normalize_token(outcome_claims.get("readback_provider")):
            task_errors.append(
                f"{label}.postcondition.readback_provider must match verifiable_outcomes evidence"
            )
        observed = str(postcondition.get("observed_state", "")).strip()
        if not observed:
            task_errors.append(f"{label}.postcondition.observed_state is required")
        computed_pass = _postcondition_passed(operator, observed, expected)
        if postcondition.get("passed") is not computed_pass:
            task_errors.append(
                f"{label}.postcondition.passed does not match the declared operator and states"
            )
        if (verification_result == "passed") is not computed_pass:
            task_errors.append(
                f"{label}.verification_result does not match independent postcondition readback"
            )
        if execution_result == "succeeded" and verification_result == "passed":
            success_count += 1
        if receipt_id and receipt_digest:
            evidence.append(f"receipt:{receipt_id}:sha256:{receipt_digest}")
        if attempt_id:
            evidence.append(f"postcondition:{attempt_id}:{verification_result or 'unknown'}")

    task["attempts"] = len(attempts)
    task["successes"] = success_count
    task["selected_route"] = next(iter(selected_routes)) if len(selected_routes) == 1 else ""
    task["evidence"] = sorted(set(evidence))
    task["measurement_errors"] = sorted(set(task_errors))
    task["measurement_valid"] = not task_errors and bool(attempts)
    errors.extend(task_errors)


def _postcondition_passed(operator: str, observed: str, expected: str) -> bool:
    if operator == "equals":
        return observed == expected
    if operator == "not_equals":
        return observed != expected
    if operator == "contains":
        return expected in observed
    if operator == "exists":
        return bool(observed)
    return False
