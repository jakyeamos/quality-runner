from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from quality_runner.schema_constants import PERFORMANCE_SCHEMA


@dataclass
class PerformanceRecorder:
    """Collect bounded, machine-readable timing and work evidence for one QR run."""

    analysis_mode: str = "full"
    cache_mode: str = "repo"
    budget_seconds: float | None = None
    _started: float = field(default_factory=time.monotonic, init=False)
    _stages: dict[str, float] = field(default_factory=dict, init=False)
    _counters: Counter[str] = field(default_factory=Counter, init=False)
    _deferred_checks: list[dict[str, str]] = field(default_factory=list, init=False)
    _timeouts: list[dict[str, object]] = field(default_factory=list, init=False)
    _current_phase: str | None = field(default=None, init=False)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.monotonic()
        self._current_phase = name
        try:
            yield
        finally:
            self._stages[name] = self._stages.get(name, 0.0) + (time.monotonic() - started)

    def counter(self, name: str, value: int = 1) -> None:
        if value:
            self._counters[name] += value

    def counters(self, values: dict[str, int]) -> None:
        for name, value in values.items():
            self.counter(name, value)

    def defer(self, check: str, *, reason: str, severity: str = "advisory") -> None:
        entry = {"check": check, "reason": reason, "severity": severity}
        if entry not in self._deferred_checks:
            self._deferred_checks.append(entry)

    def timeout(self, *, reason: str, phase: str | None = None) -> None:
        self._timeouts.append(
            {
                "reason": reason,
                "phase": phase or self._current_phase,
            }
        )

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._started

    @property
    def budget_exceeded(self) -> bool:
        return self.budget_seconds is not None and self.elapsed_seconds > self.budget_seconds

    def receipt(
        self,
        *,
        status: str = "complete",
        current_phase: str | None = None,
        resume_command: str | None = None,
        extra_counters: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        counters = dict(sorted(self._counters.items()))
        for name, value in (extra_counters or {}).items():
            counters[name] = counters.get(name, 0) + value
        elapsed = self.elapsed_seconds
        exceeded = self.budget_seconds is not None and elapsed > self.budget_seconds
        if exceeded and not self._timeouts:
            self.timeout(
                reason=(
                    f"performance budget of {self.budget_seconds} seconds exceeded"
                    if self.budget_seconds is not None
                    else "performance budget exceeded"
                ),
                phase=current_phase,
            )
        if exceeded and status == "complete":
            status = "partial"
        payload: dict[str, Any] = {
            "schema": PERFORMANCE_SCHEMA,
            "status": status,
            "analysis_mode": self.analysis_mode,
            "cache_mode": self.cache_mode,
            "elapsed_seconds": round(elapsed, 6),
            "budget_seconds": self.budget_seconds,
            "budget_exceeded": exceeded,
            "phase_timings": {
                name: round(duration, 6) for name, duration in sorted(self._stages.items())
            },
            "counters": counters,
            "deferred_checks": sorted(
                self._deferred_checks,
                key=lambda item: (item["severity"], item["check"], item["reason"]),
            ),
            "timeout_reasons": list(self._timeouts),
            "current_phase": current_phase or self._current_phase,
            "resume_command": resume_command,
        }
        return payload


def performance_from_payload(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("schema") != PERFORMANCE_SCHEMA:
        return None
    return dict(payload)
