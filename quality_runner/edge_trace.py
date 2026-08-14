from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

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
    return value


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
    profiled = _string_list(
        scenario.get("edge_profile", {}).get("categories")
        if isinstance(scenario.get("edge_profile"), dict)
        else []
    )
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
    steps = trace.get("steps")
    if (
        not isinstance(steps, list)
        or not 1 <= len(steps) <= MAX_TRACE_STEPS
        or any(
            not isinstance(step, dict)
            or not _bounded_string(step.get("action"), 4_000)
            or not _bounded_string(step.get("observation"), 4_000)
            for step in steps
        )
    ):
        errors.append(f"steps must contain 1-{MAX_TRACE_STEPS} bounded action/observation objects")
    replay = trace.get("replay_results")
    if (
        not isinstance(replay, list)
        or len(replay) > MAX_TRACE_REPLAY_ATTEMPTS
        or any(
            not isinstance(item, dict)
            or item.get("status") not in {"reproduced", "not_reproduced", "blocked"}
            or not isinstance(item.get("attempt"), int)
            or not _bounded_string(item.get("observation"), 2_000)
            for item in replay
        )
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
    minimization = trace.get("minimization")
    if not isinstance(minimization, dict):
        errors.append("minimization must be an object")
    elif (
        minimization.get("status") not in {"not_needed", "complete", "partial", "blocked"}
        or not isinstance(minimization.get("original_step_count"), int)
        or not isinstance(minimization.get("minimized_step_count"), int)
        or minimization["minimized_step_count"] > minimization["original_step_count"]
    ):
        errors.append("minimization counts and status are invalid")
    elif status == "failed" and minimization.get("status") != "complete":
        errors.append("confirmed failed traces must be completely minimized")
    cleanup = trace.get("cleanup")
    if (
        not isinstance(cleanup, dict)
        or cleanup.get("status") not in {"complete", "not_required", "blocked"}
        or not _bounded_string(cleanup.get("observation"), 2_000)
    ):
        errors.append("cleanup must record a bounded status and observation")
    elif status != "blocked" and cleanup.get("status") == "blocked":
        errors.append("passed or failed traces cannot leave cleanup blocked")
    artifacts = trace.get("artifacts")
    if (
        not isinstance(artifacts, list)
        or len(artifacts) > 32
        or any(
            not isinstance(item, dict)
            or not _bounded_string(item.get("kind"), 128)
            or not isinstance(item.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
            for item in artifacts
        )
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
        "precondition_count": len(trace["preconditions"]),
        "step_count": len(trace["steps"]),
        "steps": [
            {
                "index": index,
                "action_sha256": hashlib.sha256(str(step["action"]).encode("utf-8")).hexdigest(),
                "observation_sha256": hashlib.sha256(
                    str(step["observation"]).encode("utf-8")
                ).hexdigest(),
            }
            for index, step in enumerate(trace["steps"], start=1)
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
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _bounded_string(value: object, maximum: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _bounded_strings(value: object, *, maximum: int, length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= maximum
        and all(_bounded_string(item, length) for item in value)
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
