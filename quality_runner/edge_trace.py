from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.behavior_contract import (
    EDGE_CATEGORIES,
    EDGE_SENSITIVITIES,
    MAX_FILE_BYTES,
    MAX_TRACE_REPLAY_ATTEMPTS,
    MAX_TRACE_STEPS,
    TRACE_SCHEMA,
)


def read_trace(path: Path) -> dict[str, Any]:
    expanded = path.expanduser()
    if not expanded.is_file() or expanded.is_symlink():
        raise ValueError("trace must be a regular non-symlink JSON file")
    if expanded.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"trace exceeds the {MAX_FILE_BYTES}-byte bound")
    try:
        value = json.loads(expanded.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read edge trace JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("edge trace JSON root must be an object")
    return cast(dict[str, Any], value)


def validate_trace(
    trace: dict[str, Any],
    *,
    behavior: dict[str, Any],
    scenario: dict[str, Any],
    environment: str,
    surface: str,
    status: str,
) -> None:
    errors: list[str] = []
    if trace.get("schema") != TRACE_SCHEMA:
        errors.append(f"schema must be {TRACE_SCHEMA}")
    seed = trace.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0 or seed >= 2**64:
        errors.append("seed must be an unsigned 64-bit integer")
    categories = _string_list(trace.get("categories"))
    profile = scenario.get("edge_profile", {})
    profile = cast(dict[str, Any], profile) if isinstance(profile, dict) else {}
    profiled = _string_list(profile.get("categories"))
    if (
        not categories
        or any(item not in EDGE_CATEGORIES for item in categories)
        or not set(categories).issubset(profiled)
    ):
        errors.append("categories must be a non-empty subset of the scenario edge profile")
    if trace.get("invariant") not in _string_list(behavior.get("invariants")):
        errors.append("invariant must exactly match a declared behavior invariant")
    if trace.get("environment", environment) != environment:
        errors.append("trace environment must match --environment")
    if trace.get("surface", surface) != surface:
        errors.append("trace surface must match --surface")
    if trace.get("sensitivity") not in EDGE_SENSITIVITIES:
        errors.append("sensitivity must be normal or security_sensitive")
    if not _bounded_strings(trace.get("preconditions"), maximum=32, length=2_000):
        errors.append("preconditions must contain at most 32 bounded strings")
    raw_steps = trace.get("steps")
    steps = cast(list[object], raw_steps) if isinstance(raw_steps, list) else []
    if (
        not isinstance(raw_steps, list)
        or not 1 <= len(steps) <= MAX_TRACE_STEPS
        or any(not _valid_step(step) for step in steps)
    ):
        errors.append(f"steps must contain 1-{MAX_TRACE_STEPS} bounded action/observation objects")
    raw_replay = trace.get("replay_results")
    replay_values = cast(list[object], raw_replay) if isinstance(raw_replay, list) else []
    replay = [cast(dict[str, Any], item) for item in replay_values if isinstance(item, dict)]
    if (
        not isinstance(raw_replay, list)
        or len(replay_values) > MAX_TRACE_REPLAY_ATTEMPTS
        or len(replay) != len(replay_values)
        or any(not _valid_replay_item(item) for item in replay_values)
    ):
        errors.append("replay_results must contain at most three bounded replay attempts")
        replay = []
    determinism = trace.get("determinism")
    classification = trace.get("classification")
    if determinism not in {"deterministic", "nondeterministic"}:
        errors.append("determinism must be deterministic or nondeterministic")
    if status == "failed":
        if classification != "confirmed":
            errors.append("failed traces must be classified confirmed")
        expected = 1 if determinism == "deterministic" else 3
        if len(replay) != expected or not any(
            item.get("status") == "reproduced" for item in replay
        ):
            errors.append(
                "failed traces must reproduce once when deterministic or across exactly three attempts when nondeterministic"
            )
    elif status == "passed" and classification != "passed":
        errors.append("passed traces must be classified passed")
    elif status == "blocked" and classification not in {"blocked", "flaky", "inconclusive"}:
        errors.append("blocked traces must be classified blocked, flaky, or inconclusive")
    raw_minimization = trace.get("minimization")
    minimization = (
        cast(dict[str, Any], raw_minimization) if isinstance(raw_minimization, dict) else {}
    )
    if not isinstance(raw_minimization, dict):
        errors.append("minimization must be an object")
    if isinstance(raw_minimization, dict) and (
        minimization.get("status") not in {"not_needed", "complete", "partial", "blocked"}
        or not isinstance(minimization.get("original_step_count"), int)
        or not isinstance(minimization.get("minimized_step_count"), int)
        or minimization["minimized_step_count"] > minimization["original_step_count"]
    ):
        errors.append("minimization counts and status are invalid")
    elif (
        isinstance(raw_minimization, dict)
        and status == "failed"
        and minimization.get("status") != "complete"
    ):
        errors.append("confirmed failed traces must be completely minimized")
    raw_cleanup = trace.get("cleanup")
    cleanup = cast(dict[str, Any], raw_cleanup) if isinstance(raw_cleanup, dict) else {}
    if (
        not isinstance(raw_cleanup, dict)
        or cleanup.get("status") not in {"complete", "not_required", "blocked"}
        or not _bounded_string(cleanup.get("observation"), 2_000)
    ):
        errors.append("cleanup must record a bounded status and observation")
    elif status != "blocked" and cleanup.get("status") == "blocked":
        errors.append("passed or failed traces cannot leave cleanup blocked")
    raw_artifacts = trace.get("artifacts")
    artifacts = cast(list[object], raw_artifacts) if isinstance(raw_artifacts, list) else []
    if (
        not isinstance(raw_artifacts, list)
        or len(artifacts) > 32
        or any(not _valid_artifact(item) for item in artifacts)
    ):
        errors.append("artifacts must contain at most 32 kind/SHA-256 records")
    if not _bounded_string(trace.get("observation"), 2_000):
        errors.append("observation must be a non-empty bounded string")
    if trace.get("sensitivity") == "normal" and _contains_secret_marker(trace):
        errors.append(
            "normal traces may not contain secret-like material; redact or mark sensitive"
        )
    if errors:
        raise ValueError("invalid edge trace: " + "; ".join(errors))


def receipt_trace(
    trace: dict[str, Any],
    *,
    trace_sha256: str,
    environment: str,
    surface: str,
) -> dict[str, Any]:
    common = {
        "kind": "edge_trace",
        "schema": TRACE_SCHEMA,
        "trace_sha256": trace_sha256,
        "seed": trace["seed"],
        "categories": trace["categories"],
        "invariant": trace["invariant"],
        "environment": environment,
        "surface": surface,
        "classification": trace["classification"],
        "determinism": trace["determinism"],
        "sensitivity": trace["sensitivity"],
        "replay_results": trace["replay_results"],
        "minimization": trace["minimization"],
        "cleanup": trace["cleanup"],
        "artifacts": trace["artifacts"],
    }
    if trace["sensitivity"] == "normal":
        return {
            **common,
            "preconditions": trace["preconditions"],
            "steps": trace["steps"],
            "observation": trace["observation"],
        }
    return {
        **common,
        "precondition_count": len(_object_list(trace.get("preconditions"))),
        "step_count": len(_object_list(trace.get("steps"))),
        "steps": [
            {
                "index": index,
                "action_sha256": hashlib.sha256(str(step["action"]).encode("utf-8")).hexdigest(),
                "observation_sha256": hashlib.sha256(
                    str(step["observation"]).encode("utf-8")
                ).hexdigest(),
            }
            for index, step in enumerate(_object_mappings(trace.get("steps")), start=1)
        ],
        "observation": "Security-sensitive reproduction details are held in the private local evidence store.",
    }


def store_private_trace(trace: dict[str, Any], trace_sha256: str) -> str:
    configured = os.environ.get("QUALITY_RUNNER_PRIVATE_EVIDENCE_ROOT")
    root = Path(configured).expanduser() if configured else Path.home() / ".quality-runner/private"
    directory = root / "behavior-assurance/edge-traces"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise ValueError("private edge evidence directory may not be a symlink")
    identifier = f"edge-trace-{trace_sha256}"
    output = directory / f"{identifier}.json"
    if output.exists() and output.is_symlink():
        raise ValueError("private edge evidence file may not be a symlink")
    payload = (json.dumps(trace, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    return identifier


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def _bounded_string(value: object, maximum: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _bounded_strings(value: object, *, maximum: int, length: int) -> bool:
    values = cast(list[object], value) if isinstance(value, list) else []
    return (
        isinstance(value, list)
        and len(values) <= maximum
        and all(_bounded_string(item, length) for item in values)
    )


def _object_list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _object_mappings(value: object) -> list[dict[str, Any]]:
    return [cast(dict[str, Any], item) for item in _object_list(value) if isinstance(item, dict)]


def _valid_step(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    step = cast(dict[str, Any], value)
    return _bounded_string(step.get("action"), 4_000) and _bounded_string(
        step.get("observation"), 4_000
    )


def _valid_replay_item(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    item = cast(dict[str, Any], value)
    return (
        item.get("status") in {"reproduced", "not_reproduced", "blocked"}
        and isinstance(item.get("attempt"), int)
        and _bounded_string(item.get("observation"), 2_000)
    )


def _valid_artifact(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    item = cast(dict[str, Any], value)
    sha256 = item.get("sha256")
    return (
        _bounded_string(item.get("kind"), 128)
        and isinstance(sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", sha256) is not None
    )


def _contains_secret_marker(value: object) -> bool:
    encoded = json.dumps(value, sort_keys=True)
    return (
        re.search(
            r"(?i)(authorization\s*:|bearer\s+[a-z0-9._-]+|password\s*[=:]|"
            r"(?:api[_-]?key|token|secret)\s*[=:]|(?:sk|ghp)_[a-z0-9_-]{12,})",
            encoded,
        )
        is not None
    )
