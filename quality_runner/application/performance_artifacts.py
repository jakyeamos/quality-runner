from __future__ import annotations

import time
from pathlib import Path

from quality_runner.artifacts import write_json
from quality_runner.core.audit_contracts import AuditAnalysis, AuditArtifactPaths


def write_performance_artifact(
    analysis: AuditAnalysis,
    *,
    run_dir: Path,
    artifact_paths: AuditArtifactPaths,
) -> AuditArtifactPaths:
    started = time.monotonic()
    performance = analysis.performance
    if not isinstance(performance, dict):
        performance = {
            "schema": "quality-runner-performance-v0.1",
            "status": "complete",
            "analysis_mode": analysis.request.analysis_mode,
            "cache_mode": analysis.request.cache_mode or "repo",
            "elapsed_seconds": 0.0,
            "phase_timings": {},
            "counters": {},
            "deferred_checks": [],
            "timeout_reasons": [],
            "current_phase": None,
            "resume_command": None,
        }
    path = run_dir / "performance.json"
    artifact_paths["performance_json"] = str(write_json(path, performance))
    with_write_time = round(time.monotonic() - started, 6)
    write_json(path, {**performance, "artifact_write_seconds": with_write_time})
    return artifact_paths
