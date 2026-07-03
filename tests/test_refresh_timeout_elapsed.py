from __future__ import annotations

import json
from pathlib import Path


def test_total_refresh_timeout_artifact_uses_total_elapsed_seconds(
    tmp_path: Path, monkeypatch: object
) -> None:
    from quality_runner import refresh_workflow, workflow

    times = iter([100.0, 100.0, 100.0, 125.0, 125.0, 125.0, 130.0, 130.0, 130.0])

    def monotonic_stub() -> float:
        return next(times, 130.0)

    def inspect_stub(**_: object) -> dict[str, object]:
        return {"status": "inspected", "run_id": "refresh-total-elapsed-inspect"}

    def run_timeout(**_: object) -> dict[str, object]:
        raise TimeoutError("controller full refresh budget")

    monkeypatch.setattr(refresh_workflow.time, "monotonic", monotonic_stub)
    monkeypatch.setattr(workflow, "inspect_payload", inspect_stub)
    monkeypatch.setattr(workflow, "run_payload", run_timeout)

    workflow.refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="refresh-total-elapsed",
        workflow_timeout_seconds=60,
        total_timeout_seconds=30,
        total_timeout_reason="controller full refresh budget",
    )
    run_dir = tmp_path / ".quality-runner" / "runs" / "refresh-total-elapsed-verify"
    timeout_artifact = json.loads((run_dir / "workflow-timeout.json").read_text())
    gate_verification = json.loads((run_dir / "gate-verification.json").read_text())

    assert timeout_artifact["timeout_scope"] == "total-refresh"
    assert timeout_artifact["elapsed_seconds"] == 30.0
    assert timeout_artifact["phase_elapsed_seconds"] == 5.0
    assert gate_verification["elapsed_seconds"] == 30.0
    assert gate_verification["phase_elapsed_seconds"] == 5.0
