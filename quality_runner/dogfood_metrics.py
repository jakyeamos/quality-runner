from __future__ import annotations

from typing import Any


def duration_series(checks: list[dict[str, Any]], dimension: str) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    for check in checks:
        values = check["dimensions"].get(dimension)
        if not isinstance(values, dict):
            continue
        for identifier, value in values.items():
            if isinstance(identifier, str) and isinstance(value, (int, float)):
                series.setdefault(identifier, []).append(float(value))
    return series


def duration_summary(
    series: dict[str, list[float]],
) -> dict[str, dict[str, float | int | None]]:
    return {
        identifier: {
            "runs": len(values),
            "p50": percentile(values, 0.5),
            "p95": percentile(values, 0.95),
        }
        for identifier, values in sorted(series.items())
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return round(ordered[index], 6)
