from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from quality_runner import __version__
from quality_runner.artifacts import write_json
from quality_runner.timeout_baseline_support import (
    build_timeout_identity,
    canonical_sha256,
    write_run_baseline_artifact,
)
from quality_runner.timeout_baseline_support import (
    list_value as _list_value,
)
from quality_runner.timeout_baseline_support import (
    load_gate_execution_plan as _load_gate_execution_plan,
)
from quality_runner.timeout_baseline_support import (
    mapping as _mapping,
)
from quality_runner.timeout_baseline_support import (
    numeric_float as _numeric_float,
)
from quality_runner.timeout_baseline_support import (
    positive_int as _positive_int,
)
from quality_runner.timeout_baseline_support import (
    string_or_none as _string_or_none,
)

TIMEOUT_BASELINE_SCHEMA = "quality-runner-refresh-timeout-baseline-v1"
TIMEOUT_BASELINE_RELATIVE_PATH = (
    Path(".quality-runner") / "cache" / "refresh-timeout-baseline-v1.json"
)
TIMEOUT_BASELINE_SAMPLE_LIMIT = 12
TIMEOUT_BASELINE_ACTIVATION_SAMPLES = 3
TIMEOUT_BASELINE_CANDIDATE_MARGIN = 2.0
TIMEOUT_BASELINE_ACTIVE_MARGIN = 1.5
TIMEOUT_BASELINE_TOTAL_MARGIN = 1.15
TIMEOUT_BASELINE_FLOORS = {
    "inspect": 30,
    "run": 30,
    "verify": 60,
}
TIMEOUT_BASELINE_MIN_TOTAL = 180
TIMEOUT_BASELINE_PHASES = ("inspect", "run", "verify")


def timeout_baseline_path(repo_root: Path) -> Path:
    return repo_root.expanduser().resolve() / TIMEOUT_BASELINE_RELATIVE_PATH


def load_gate_execution_plan(repo_root: Path, run_id: str) -> list[object] | None:
    return _load_gate_execution_plan(repo_root, run_id)


def resolve_timeout_context(
    repo_root: Path,
    *,
    profile: str | None,
    per_gate_timeout_seconds: int,
    scan_exclusion_overlay: object | None,
    gate_plan: object | None = None,
) -> dict[str, object]:
    root = repo_root.expanduser().resolve()
    identity = build_timeout_identity(root, profile=profile)
    baseline_path = timeout_baseline_path(root)
    context: dict[str, object] = {
        "status": "fallback",
        "source": "fixed-fallback",
        "reason": "no active timeout baseline matches the repository identity",
        "baseline_id": None,
        "baseline_path": str(baseline_path),
        "identity_sha256": identity["static_sha256"],
        "sample_count": 0,
        "expected_gate_plan_sha256": None,
        "timeouts": {},
    }
    if scan_exclusion_overlay is not None:
        context["reason"] = "run-only scan-exclusion overlays cannot seed or consume a baseline"
        return context

    preflight = _mapping(_mapping(identity.get("static")).get("exclusion_preflight"))
    if preflight.get("status") == "required-unvalidated":
        context["reason"] = "custom scan exclusions do not have a matching validated preflight"
        return context

    baseline = load_timeout_baseline(root)
    if baseline is None:
        context["reason"] = "timeout baseline is not present"
        return context
    if baseline.get("schema") != TIMEOUT_BASELINE_SCHEMA:
        context["reason"] = "timeout baseline schema is invalid"
        return context
    baseline_identity = _mapping(baseline.get("identity"))
    if baseline_identity.get("static_sha256") != identity["static_sha256"]:
        context["reason"] = "timeout baseline identity is stale"
        return context
    if baseline_identity.get("sha256") != canonical_sha256(
        {
            "static": baseline_identity.get("static"),
            "gate_plan_sha256": baseline_identity.get("gate_plan_sha256"),
        }
    ):
        context["reason"] = "timeout baseline identity is malformed"
        return context
    expected_gate_plan_sha256 = baseline_identity.get("gate_plan_sha256")
    if gate_plan is not None and canonical_sha256(gate_plan) != expected_gate_plan_sha256:
        context["reason"] = "timeout baseline discovered gate plan is stale"
        return context
    if baseline.get("state") != "active":
        context["reason"] = "timeout baseline has not reached three comparable runs"
        context["sample_count"] = _positive_int(baseline.get("sample_count"))
        return context
    sample_count = _positive_int(baseline.get("sample_count"))
    samples = [item for item in _list_value(baseline.get("samples")) if isinstance(item, dict)]
    if sample_count < TIMEOUT_BASELINE_ACTIVATION_SAMPLES or len(samples) < sample_count:
        context["reason"] = "active timeout baseline has insufficient comparable samples"
        context["sample_count"] = sample_count
        return context
    if not isinstance(baseline.get("baseline_id"), str) or not isinstance(
        expected_gate_plan_sha256, str
    ):
        context["reason"] = "active timeout baseline provenance is incomplete"
        return context
    timeouts = _timeout_budget(baseline.get("learned_timeouts"))
    if timeouts is None:
        context["reason"] = "timeout baseline has no valid learned budgets"
        return context
    context.update(
        {
            "status": "active",
            "source": "adaptive-baseline",
            "reason": "active timeout baseline matches the repository identity",
            "baseline_id": baseline.get("baseline_id"),
            "sample_count": sample_count,
            "expected_gate_plan_sha256": expected_gate_plan_sha256,
            "identity_sha256": baseline_identity.get("sha256", identity["static_sha256"]),
            "timeouts": _minimum_verify_timeout(timeouts, per_gate_timeout_seconds),
        }
    )
    return context


def record_timeout_sample(
    repo_root: Path,
    *,
    run_id_prefix: str,
    profile: str | None,
    per_gate_timeout_seconds: int,
    phase_timings: Mapping[str, object],
    summary: Mapping[str, object],
    execute_discovered_gates: bool,
    scan_exclusion_overlay: object | None,
    timed_out: bool,
    gate_plan: object | None = None,
    focus_paths: list[str] | None = None,
    cache_state: str = "not-configured",
) -> dict[str, object]:
    root = repo_root.expanduser().resolve()
    identity = build_timeout_identity(root, profile=profile, gate_plan=gate_plan)
    result: dict[str, object] = {
        "status": "skipped",
        "reason": "refresh sample is not eligible for timeout calibration",
        "baseline_path": str(timeout_baseline_path(root)),
        "baseline_id": None,
        "state": None,
        "sample_count": 0,
        "identity_sha256": identity["sha256"],
    }
    eligibility_reason = _sample_ineligibility_reason(
        phase_timings=phase_timings,
        summary=summary,
        execute_discovered_gates=execute_discovered_gates,
        scan_exclusion_overlay=scan_exclusion_overlay,
        timed_out=timed_out,
        focus_paths=focus_paths,
        cache_state=cache_state,
        gate_plan=gate_plan,
        identity=identity,
    )
    if eligibility_reason is not None:
        result["reason"] = eligibility_reason
        return result

    baseline = load_timeout_baseline(root)
    existing_identity = _mapping(baseline.get("identity")) if baseline else {}
    samples = (
        [item for item in _list_value(baseline.get("samples")) if isinstance(item, dict)]
        if baseline is not None and existing_identity.get("sha256") == identity["sha256"]
        else []
    )
    observed = _observed_phase_timings(phase_timings)
    sample = {
        "captured_at": datetime.now(UTC).isoformat(),
        "run_id_prefix": run_id_prefix,
        "phase_timings": observed,
        "total_elapsed_seconds": round(
            sum(_numeric_float(item.get("elapsed_seconds")) for item in observed.values()),
            3,
        ),
        "summary_status": summary.get("status"),
        "cache_state": cache_state,
    }
    samples = [*samples, sample][-TIMEOUT_BASELINE_SAMPLE_LIMIT:]
    candidate_timeouts = _candidate_timeouts(observed, per_gate_timeout_seconds)
    state = "active" if len(samples) >= TIMEOUT_BASELINE_ACTIVATION_SAMPLES else "candidate"
    learned_timeouts = (
        _active_timeouts(samples, per_gate_timeout_seconds)
        if state == "active"
        else candidate_timeouts
    )
    baseline_id = f"timeout-baseline-{str(identity['sha256'])[:12]}"
    baseline_payload: dict[str, object] = {
        "schema": TIMEOUT_BASELINE_SCHEMA,
        "baseline_id": baseline_id,
        "state": state,
        "sample_count": len(samples),
        "sample_limit": TIMEOUT_BASELINE_SAMPLE_LIMIT,
        "activation_samples": TIMEOUT_BASELINE_ACTIVATION_SAMPLES,
        "identity": identity,
        "cache_state": cache_state,
        "phase_timings": observed,
        "samples": samples,
        "candidate_timeouts": candidate_timeouts,
        "learned_timeouts": learned_timeouts,
        "provenance": {
            "quality_runner_version": __version__,
            "profile": profile or "default",
            "run_id_prefix": run_id_prefix,
            "per_gate_timeout_seconds": per_gate_timeout_seconds,
            "source": "complete-full-refresh",
            "candidate_margin": TIMEOUT_BASELINE_CANDIDATE_MARGIN,
            "active_margin": TIMEOUT_BASELINE_ACTIVE_MARGIN,
            "rolling_percentile": 0.95,
            "total_margin": TIMEOUT_BASELINE_TOTAL_MARGIN,
            "phase_floors": TIMEOUT_BASELINE_FLOORS,
            "minimum_total_seconds": TIMEOUT_BASELINE_MIN_TOTAL,
            "activation_samples": TIMEOUT_BASELINE_ACTIVATION_SAMPLES,
        },
        "updated_at": datetime.now(UTC).isoformat(),
    }
    path = timeout_baseline_path(root)
    try:
        write_json(path, baseline_payload)
    except (OSError, ValueError):
        result["reason"] = "timeout baseline cache path is unavailable"
        return result
    artifact_path = write_run_baseline_artifact(root, run_id_prefix, baseline_payload)
    result.update(
        {
            "status": "recorded",
            "reason": "eligible refresh sample recorded",
            "baseline_id": baseline_id,
            "state": state,
            "sample_count": len(samples),
            "baseline_path": str(path),
            "artifact_path": artifact_path,
        }
    )
    return result


def load_timeout_baseline(repo_root: Path) -> dict[str, object] | None:
    root = repo_root.expanduser().resolve()
    if any(
        (root / segment).is_symlink() for segment in (".quality-runner", ".quality-runner/cache")
    ):
        return None
    path = timeout_baseline_path(root)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _sample_ineligibility_reason(
    *,
    phase_timings: Mapping[str, object],
    summary: Mapping[str, object],
    execute_discovered_gates: bool,
    scan_exclusion_overlay: object | None,
    timed_out: bool,
    focus_paths: list[str] | None,
    cache_state: str,
    gate_plan: object | None,
    identity: Mapping[str, object],
) -> str | None:
    if timed_out:
        return "timed-out refreshes cannot update the timeout baseline"
    if not execute_discovered_gates:
        return "gate execution consent is required for a complete calibration run"
    if scan_exclusion_overlay is not None:
        return "run-only scan-exclusion overlays cannot update the timeout baseline"
    if focus_paths:
        return "focused or changed-only runs cannot update the timeout baseline"
    if cache_state in {"ambiguous", "unknown"}:
        return "cache state is ambiguous"
    if gate_plan is None or not identity.get("gate_plan_sha256"):
        return "discovered gate plan is unavailable"
    preflight = _mapping(_mapping(identity.get("static")).get("exclusion_preflight"))
    if preflight.get("status") == "required-unvalidated":
        return "custom scan exclusions do not have a matching validated preflight"
    summary_status = _string_or_none(summary.get("status"))
    if summary_status is None:
        return "refresh summary status is missing"
    if summary_status in {"blocked", "unknown", "failed"}:
        return "refresh did not complete successfully"
    for phase in TIMEOUT_BASELINE_PHASES:
        timing = _mapping(phase_timings.get(phase))
        if not isinstance(timing.get("elapsed_seconds"), (int, float)):
            return f"{phase} phase timing is missing"
        phase_status = timing.get("status")
        if not isinstance(phase_status, str) or phase_status in {
            "blocked",
            "not-started",
            "partial",
            "timeout",
            "unknown",
        }:
            return f"{phase} phase did not complete successfully"
    return None


def _candidate_timeouts(
    observed: Mapping[str, Mapping[str, object]],
    per_gate_timeout_seconds: int,
) -> dict[str, int]:
    values = {
        phase: max(
            _phase_floor(phase, per_gate_timeout_seconds),
            math.ceil(
                _numeric_float(observed[phase].get("elapsed_seconds"))
                * TIMEOUT_BASELINE_CANDIDATE_MARGIN
            ),
        )
        for phase in TIMEOUT_BASELINE_PHASES
    }
    return {**values, "total": _total_timeout(values)}


def _active_timeouts(
    samples: list[dict[str, object]],
    per_gate_timeout_seconds: int,
) -> dict[str, int]:
    values = {
        phase: max(
            _phase_floor(phase, per_gate_timeout_seconds),
            math.ceil(
                _p95(_sample_elapsed(sample, phase) for sample in samples)
                * TIMEOUT_BASELINE_ACTIVE_MARGIN
            ),
        )
        for phase in TIMEOUT_BASELINE_PHASES
    }
    return {**values, "total": _total_timeout(values)}


def _total_timeout(values: Mapping[str, int]) -> int:
    return max(
        TIMEOUT_BASELINE_MIN_TOTAL,
        math.ceil(
            sum(values[phase] for phase in TIMEOUT_BASELINE_PHASES) * TIMEOUT_BASELINE_TOTAL_MARGIN
        ),
    )


def _phase_floor(phase: str, per_gate_timeout_seconds: int) -> int:
    if phase == "verify":
        return max(TIMEOUT_BASELINE_FLOORS[phase], per_gate_timeout_seconds)
    return TIMEOUT_BASELINE_FLOORS[phase]


def _p95(values: Iterable[object]) -> float:
    numeric = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not numeric:
        return 0.1
    index = max(0, math.ceil(len(numeric) * 0.95) - 1)
    return numeric[index]


def _sample_elapsed(sample: Mapping[str, object], phase: str) -> float:
    timings = _mapping(sample.get("phase_timings"))
    value = _mapping(timings.get(phase)).get("elapsed_seconds")
    return float(value) if isinstance(value, (int, float)) else 0.1


def _observed_phase_timings(
    phase_timings: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    return {
        phase: {
            "status": _mapping(phase_timings.get(phase)).get("status"),
            "elapsed_seconds": round(
                _numeric_float(_mapping(phase_timings.get(phase)).get("elapsed_seconds", 0.0)),
                3,
            ),
        }
        for phase in TIMEOUT_BASELINE_PHASES
    }


def _minimum_verify_timeout(
    values: Mapping[str, int], per_gate_timeout_seconds: int
) -> dict[str, int]:
    return {
        "inspect": values["inspect"],
        "run": values["run"],
        "verify": max(values["verify"], per_gate_timeout_seconds),
        "total": max(values["total"], per_gate_timeout_seconds),
    }


def _timeout_budget(value: object) -> dict[str, int] | None:
    mapping = _mapping(value)
    values = {phase: mapping.get(phase) for phase in ("inspect", "run", "verify", "total")}
    if any(not isinstance(item, int) or item <= 0 for item in values.values()):
        return None
    return cast(dict[str, int], values)
