from __future__ import annotations

from pathlib import Path

from quality_runner.controller_report_defaults import workflow_timeout_blockers
from quality_runner.scan_exclusions import (
    record_scan_activity,
    reset_scan_progress,
    scan_progress_snapshot,
)
from quality_runner.timeout_diagnostics import (
    concise_timeout_diagnostics,
    timeout_diagnostics_markdown,
    timeout_diagnostics_payload,
)


def test_timeout_diagnostics_distinguish_excluded_estimation_from_actual_scan(
    tmp_path: Path,
) -> None:
    reset_scan_progress()
    record_scan_activity(
        tmp_path,
        tmp_path / ".quality-runner",
        kind="excluded-directory-estimation",
    )
    progress = scan_progress_snapshot()
    payload = {
        "timeout_scope": "total-refresh",
        "reason": "controller deadline exceeded",
        "timeout_seconds": 300,
        "elapsed_seconds": 300.1,
        "diagnostics": timeout_diagnostics_payload(progress),
    }

    assert payload["diagnostics"]["scan_activity"] == {  # type: ignore[index]
        "kind": "excluded-directory-estimation",
        "path": ".quality-runner",
    }
    concise = concise_timeout_diagnostics(payload)
    assert concise["scan_activity"] == {  # type: ignore[index]
        "kind": "excluded-directory-estimation",
        "path": ".quality-runner",
    }
    assert "excluded-directory estimation (not actual scan work)" in "\n".join(
        timeout_diagnostics_markdown(concise)
    )
    blockers = workflow_timeout_blockers(
        {
            **concise,
            "timeout_scope": "total-refresh",
        }
    )
    assert blockers[0] == (
        "Workflow timeout: total-refresh timed out while estimating excluded directory "
        ".quality-runner (not actual scan work) after 0 visited paths."
    )
    reset_scan_progress()


def test_timeout_diagnostics_label_actual_text_scan(tmp_path: Path) -> None:
    reset_scan_progress()
    record_scan_activity(tmp_path, tmp_path / "src", kind="text-scan")

    diagnostics = timeout_diagnostics_payload(scan_progress_snapshot())

    assert diagnostics["scan_activity"] == {  # type: ignore[index]
        "kind": "text-scan",
        "path": "src",
    }
    assert "actual text scan" in "\n".join(
        timeout_diagnostics_markdown(diagnostics["scan_activity"])  # type: ignore[index]
    )
    reset_scan_progress()
