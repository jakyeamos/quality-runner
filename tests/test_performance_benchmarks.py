from __future__ import annotations

import time
from pathlib import Path

from quality_runner.code_quality import create_code_quality_scan
from quality_runner.performance import PerformanceRecorder

TENURE_FILE_COUNT = 886
TENURE_LINES_PER_FILE = 162


def _write_tenure_fixture(root: Path) -> None:
    for index in range(TENURE_FILE_COUNT):
        directory = root / "src" / f"domain-{index % 32:02d}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"module-{index:04d}.ts"
        path.write_text(
            "export const value = 1;\n" * TENURE_LINES_PER_FILE,
            encoding="utf-8",
        )


def test_balanced_tenure_sized_fixture_is_incremental(tmp_path: Path) -> None:
    repo = tmp_path / "tenure-fixture"
    cache = tmp_path / "external-cache"
    repo.mkdir()
    _write_tenure_fixture(repo)

    started = time.perf_counter()
    cold = create_code_quality_scan(
        repo,
        scan={"run_id": "cold"},
        config={},
        analysis_mode="balanced",
        cache_mode="external",
        cache_root=cache,
    )
    cold_seconds = time.perf_counter() - started

    started = time.perf_counter()
    warm = create_code_quality_scan(
        repo,
        scan={"run_id": "warm"},
        config={},
        analysis_mode="balanced",
        cache_mode="external",
        cache_root=cache,
    )
    warm_seconds = time.perf_counter() - started

    changed = repo / "src" / "domain-00" / "module-0000.ts"
    changed.write_text("export const value = 2;\n" * TENURE_LINES_PER_FILE, encoding="utf-8")
    one_file = create_code_quality_scan(
        repo,
        scan={"run_id": "one-file"},
        config={},
        analysis_mode="balanced",
        cache_mode="external",
        cache_root=cache,
    )

    assert cold_seconds < 120
    assert warm_seconds < 30
    assert cold["findings"] == warm["findings"]
    assert warm["analysis_cache"]["cache_hits"] == TENURE_FILE_COUNT  # type: ignore[index]
    assert warm["analysis_cache"]["recomputed_files"] == 0  # type: ignore[index]
    assert warm["analysis_cache"]["source_bytes_read"] == 0  # type: ignore[index]
    assert one_file["analysis_cache"]["recomputed_files"] == 1  # type: ignore[index]
    assert one_file["analysis_cache"]["cache_hits"] == TENURE_FILE_COUNT - 1  # type: ignore[index]
    assert not (repo / ".quality-runner" / "cache").exists()


def test_performance_receipt_is_bounded_and_resumable() -> None:
    recorder = PerformanceRecorder(analysis_mode="balanced", cache_mode="external", budget_seconds=0)
    with recorder.stage("discovery"):
        pass

    receipt = recorder.receipt(resume_command="quality-runner refresh /repo --analysis-mode balanced")

    assert receipt["status"] == "partial"
    assert receipt["budget_exceeded"] is True
    assert receipt["current_phase"] == "discovery"
    assert receipt["timeout_reasons"][0]["phase"] == "discovery"  # type: ignore[index]
    assert receipt["resume_command"].startswith("quality-runner refresh")
