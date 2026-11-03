from __future__ import annotations

import json
import statistics
import subprocess
from pathlib import Path
from typing import Any, cast

from quality_runner.web_performance_contract import (
    nonnegative_number,
    performance_evidence_error,
    timestamp,
)
from quality_runner.web_readiness_deployment import readiness_check


def performance_checks(
    root: Path,
    config: dict[str, Any],
    evidence_path: Path | None,
    *,
    head_sha: str | None,
    observed_at: str,
) -> list[dict[str, Any]]:
    errors = config.get("performance_budget_errors", [])
    if errors:
        return [_check("performance_policy", "block", "blocked", "; ".join(errors))]
    budgets = cast(list[dict[str, Any]], config.get("performance_budgets", []))
    if not budgets:
        if evidence_path is None:
            return []
        return [
            _check(
                "performance_policy",
                "warn",
                "unknown",
                "Performance evidence was supplied without repository-owned budgets; no thresholds inferred.",
            )
        ]
    payload, error = _load_evidence(root, evidence_path, head_sha)
    checks: list[dict[str, Any]] = []
    for budget in budgets:
        identifier = f"performance:{budget['id']}"
        policy = str(budget["policy"])
        if evidence_path is None:
            checks.append(
                _check(identifier, policy, "unknown", "No lab performance evidence supplied.")
            )
        elif error or payload is None:
            checks.append(_check(identifier, policy, "blocked", error or "Evidence unavailable."))
        else:
            checks.append(_evaluate(budget, payload, observed_at))
    return checks


def _load_evidence(
    root: Path,
    path: Path | None,
    head_sha: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    try:
        with path.expanduser().open("rb") as stream:
            data = stream.read(1_048_577)
        if len(data) > 1_048_576:
            return None, "Performance evidence exceeds the 1 MiB import limit."
        raw: object = json.loads(data)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        return None, f"Performance evidence could not be read: {error}"
    error = performance_evidence_error(raw)
    if error:
        return None, error
    payload = cast(dict[str, Any], raw)
    if not head_sha or payload["target"]["commit"] != head_sha:
        return None, "Performance evidence commit does not match the repository HEAD."
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "Clean tracked source identity could not be verified."
    if result.returncode or result.stdout.strip():
        return None, "Performance evidence requires a clean tracked source at the measured commit."
    return payload, None


def _evaluate(
    budget: dict[str, Any],
    payload: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    identifier = f"performance:{budget['id']}"
    policy = str(budget["policy"])
    measurement = next(
        (item for item in payload["measurements"] if item["budget_id"] == budget["id"]),
        None,
    )
    if measurement is None:
        return _check(identifier, policy, "unknown", "No measurement for this declared budget.")
    measured_at = timestamp(payload["observed_at"])
    current = timestamp(now)
    if measured_at is None or current is None:
        return _check(identifier, policy, "blocked", "Measurement freshness could not be verified.")
    age_hours = (current - measured_at).total_seconds() / 3600
    if age_hours < 0 or age_hours > budget["max_age_hours"]:
        return _check(
            identifier, policy, "blocked", "Measurement is future-dated or exceeds max_age_hours."
        )
    if any(measurement[field] != budget[field] for field in ("metric", "method", "scenario")):
        return _check(
            identifier,
            policy,
            "blocked",
            "Metric, method or scenario differs from repository policy.",
        )
    samples = cast(list[float], measurement["samples"])
    if len(samples) < budget["min_samples"]:
        return _check(identifier, policy, "blocked", "Fewer samples than the declared minimum.")
    value = max(samples) if budget["statistic"] == "max" else statistics.median(samples)
    if not nonnegative_number(value):
        return _check(identifier, policy, "blocked", "Aggregate exceeds the finite numeric range.")
    evidence = {
        "metric": budget["metric"],
        "value": value,
        "budget": budget["maximum"],
        "statistic": budget["statistic"],
        "sample_count": len(samples),
        "minimum": min(samples),
        "maximum": max(samples),
        "samples": samples,
        "method": measurement["method"],
        "scenario": measurement["scenario"],
        "owner": budget["owner"],
        "rationale": budget["rationale"],
        "target": payload["target"],
        "observed_at": payload["observed_at"],
        "tool": payload["tool"],
        "command": payload["command"],
        "evidence_kind": "lab",
    }
    return _check(
        identifier,
        policy,
        "passed" if value <= budget["maximum"] else "failed",
        f"Lab {budget['metric']} {budget['statistic']}: {value}; maximum {budget['maximum']}. "
        "Controlled observations do not establish field Core Web Vitals compliance.",
        evidence=[evidence],
    )


def _check(
    identifier: str,
    policy: str,
    status: str,
    detail: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return readiness_check(
        identifier,
        "Lab performance budget",
        "baseline",
        policy,
        status,
        "browser_rendered",
        detail,
        evidence=evidence,
    )
