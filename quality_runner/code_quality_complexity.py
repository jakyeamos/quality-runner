from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from quality_runner.code_quality_complexity_parsers import (
    javascript_complexity_metrics,
    python_complexity_metrics,
)
from quality_runner.code_quality_findings import finding
from quality_runner.code_quality_paths import (
    is_javascript_source_file,
    is_source_file,
    is_test_file,
    verification_for_path,
)

DEFAULT_COMPLEXITY_THRESHOLDS = {"python": 15, "javascript": 20}
COMPLEXITY_REDUCTION_DELTA = 5


def complexity_findings(
    relative_path: str,
    text: str,
    lines: list[str],
    thresholds: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    if not is_source_file(relative_path):
        return []
    metrics = complexity_metrics(relative_path, text, lines, thresholds)
    result: list[dict[str, Any]] = []
    for metric in metrics:
        value = int(metric["value"])
        threshold = int(metric["threshold"])
        if value <= threshold:
            continue
        symbol = str(metric["symbol"])
        decisions = _decision_summary(metric.get("decision_counts"))
        result.append(
            finding(
                category="simplify",
                severity="warning",
                confidence="medium",
                file=relative_path,
                line=int(metric["line"]),
                rule_id="high-cyclomatic-complexity",
                evidence=(
                    f"{symbol} has cyclomatic complexity {value} "
                    f"(threshold {threshold}; decision counts: {decisions})"
                ),
                expected_improvement=(
                    "Split independent decisions, extract cohesive helpers, or make the branch "
                    "policy explicit while preserving behavior and edge-case coverage."
                ),
                risk=(
                    "High decision density makes behavior changes harder to review and can leave "
                    "branches untested; the metric does not prove that a refactor is safe."
                ),
                verification=verification_for_path(relative_path),
                remediation_bucket="simplification and shrink pass",
                symbol=symbol,
                metric="cyclomatic-complexity",
                value=value,
                threshold=threshold,
                language=str(metric["language"]),
            )
        )
    return result


def complexity_metrics(
    relative_path: str,
    text: str,
    lines: list[str],
    thresholds: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    if not is_source_file(relative_path):
        return []
    resolved_thresholds = {**DEFAULT_COMPLEXITY_THRESHOLDS, **_valid_thresholds(thresholds)}
    if relative_path.endswith(".py"):
        return [
            {
                "file": relative_path,
                "line": line,
                "symbol": symbol,
                "language": "python",
                "metric": "cyclomatic-complexity",
                "value": value,
                "threshold": resolved_thresholds["python"],
                "decision_counts": dict(decisions),
            }
            for line, symbol, value, decisions in python_complexity_metrics(text)
        ]
    if is_javascript_source_file(relative_path):
        return [
            {
                "file": relative_path,
                "line": line,
                "symbol": symbol,
                "language": "javascript",
                "metric": "cyclomatic-complexity",
                "value": value,
                "threshold": resolved_thresholds["javascript"],
                "decision_counts": dict(decisions),
            }
            for line, symbol, value, decisions in javascript_complexity_metrics(text)
        ]
    return []


def complexity_regression_findings(
    *,
    baseline_metrics: object,
    current_metrics: object,
    changed_paths: Iterable[str],
    report_unverified_reductions: bool = False,
) -> list[dict[str, Any]]:
    changed = set(changed_paths)
    if not changed:
        return []
    baseline = _metrics_by_symbol(baseline_metrics)
    current = _metrics_by_symbol(current_metrics)
    result: list[dict[str, Any]] = []
    for key in sorted(set(baseline) & set(current)):
        path, symbol = key
        if path not in changed:
            continue
        before = baseline[key]
        after = current[key]
        if after["value"] > before["value"]:
            result.append(
                _regression_finding(
                    path=path,
                    line=after["line"],
                    symbol=symbol,
                    before=before["value"],
                    after=after["value"],
                )
            )
        elif (
            report_unverified_reductions
            and before["value"] - after["value"] >= COMPLEXITY_REDUCTION_DELTA
            and not any(is_test_file(changed_path) for changed_path in changed)
        ):
            result.append(
                _reduction_finding(
                    path=path,
                    line=after["line"],
                    symbol=symbol,
                    before=before["value"],
                    after=after["value"],
                )
            )
    return result


def _regression_finding(
    *, path: str, line: int, symbol: str, before: int, after: int
) -> dict[str, Any]:
    return finding(
        category="simplify",
        severity="observation",
        confidence="medium",
        file=path,
        line=line,
        rule_id="complexity-regression",
        evidence=(
            f"{symbol} cyclomatic complexity increased from {before} to {after} "
            "in the changed surface"
        ),
        expected_improvement=(
            "Review the added decision paths and either simplify the change or document why the "
            "higher complexity is required."
        ),
        risk=(
            "Complexity growth can make future changes and branch verification less reliable even "
            "when the function remains below its advisory threshold."
        ),
        verification=verification_for_path(path),
        remediation_bucket="simplification and shrink pass",
        subtype="increase",
        symbol=symbol,
        metric="cyclomatic-complexity",
        baseline_value=before,
        current_value=after,
    )


def _reduction_finding(
    *, path: str, line: int, symbol: str, before: int, after: int
) -> dict[str, Any]:
    return finding(
        category="simplify",
        severity="observation",
        confidence="low",
        file=path,
        line=line,
        rule_id="complexity-reduction-without-test-change",
        evidence=(
            f"{symbol} cyclomatic complexity decreased from {before} to {after}, but no changed "
            "test file was observed"
        ),
        expected_improvement=(
            "Confirm that the simplified paths retain behavior and add or update edge-case tests "
            "when the refactor changes decision boundaries."
        ),
        risk=(
            "A large metric reduction can come from removed branches, hidden behavior, or an "
            "incomplete refactor; path-level evidence cannot distinguish those cases."
        ),
        verification=verification_for_path(path),
        remediation_bucket="simplification and shrink pass",
        subtype="unverified-reduction",
        symbol=symbol,
        metric="cyclomatic-complexity",
        baseline_value=before,
        current_value=after,
    )


def _metrics_by_symbol(value: object) -> dict[tuple[str, str], dict[str, int]]:
    if not isinstance(value, list):
        return {}
    result: dict[tuple[str, str], dict[str, int]] = {}
    ambiguous: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        path = item.get("file")
        symbol = item.get("symbol")
        metric = item.get("metric")
        line = item.get("line")
        metric_value = item.get("value")
        if (
            not isinstance(path, str)
            or not isinstance(symbol, str)
            or metric != "cyclomatic-complexity"
            or not isinstance(line, int)
            or isinstance(line, bool)
            or not isinstance(metric_value, int)
            or isinstance(metric_value, bool)
        ):
            continue
        key = (path, symbol)
        if key in result:
            ambiguous.add(key)
            continue
        result[key] = {"line": line, "value": metric_value}
    for key in ambiguous:
        result.pop(key, None)
    return result


def _valid_thresholds(value: dict[str, int] | None) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        language: threshold
        for language, threshold in value.items()
        if language in DEFAULT_COMPLEXITY_THRESHOLDS
        and isinstance(threshold, int)
        and not isinstance(threshold, bool)
        and threshold > 0
    }


def _decision_summary(value: object) -> str:
    if not isinstance(value, dict):
        return "decisions unavailable"
    entries = [
        f"{key}={value[key]}"
        for key in sorted(value)
        if isinstance(key, str) and isinstance(value[key], int) and value[key] > 0
    ]
    return ", ".join(entries) if entries else "no counted decisions"
