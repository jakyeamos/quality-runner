from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.cli_human_summary import human_summary
from quality_runner.rollout import rollout_payload


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True)
    (repo_root / "README.md").write_text("# Fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=quality-runner@example.com",
            "-c",
            "user.name=Quality Runner",
            "commit",
            "-m",
            "initial",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_rollout_runs_repo_list_and_writes_controller_report(tmp_path: Path) -> None:
    repo_root = tmp_path / "target-repo"
    _init_repo(repo_root)
    repo_list = tmp_path / "repos.txt"
    repo_list.write_text(f"{repo_root} baseline-001 target-repo\n", encoding="utf-8")
    output_dir = tmp_path / "rollout-artifacts"
    calls: list[dict[str, Any]] = []

    def refresh_stub(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        run_id_prefix = kwargs["run_id_prefix"]
        run_dir = repo_root / ".quality-runner" / "runs" / f"{run_id_prefix}-verify"
        run_dir.mkdir(parents=True)
        return {
            "status": "blocked",
            "summary": {
                "run_id": f"{run_id_prefix}-verify",
                "status": "blocked",
                "recommended_classification": "broad-repo-debt",
                "path": str(run_dir),
                "finding_counts": {"total": 7},
                "missing_capabilities": [],
            },
        }

    payload = rollout_payload(
        repo_list_path=repo_list,
        repos=[],
        run_id_prefix="stress-pass",
        output_dir=output_dir,
        profile=None,
        ci_status_json=None,
        timeout_seconds=90,
        workflow_timeout_seconds=None,
        verify_timeout_seconds=180,
        workflow_timeout_reason="controller stress verify deadline",
        total_timeout_seconds=300,
        total_timeout_reason="controller stress total deadline",
        checkout_most_advanced_branch=False,
        allow_mutating_gates=False,
        refresh_callback=refresh_stub,
    )

    assert payload["schema"] == "quality-runner-rollout-result-v0.1"
    assert payload["status"] == "completed"
    assert payload["accepted_reports"] == 1
    assert calls[0]["repo_root"] == repo_root.resolve()
    assert calls[0]["run_id_prefix"] == "stress-pass-target-repo"
    assert calls[0]["baseline_run_id"] == "baseline-001"
    assert calls[0]["verify_timeout_seconds"] == 180
    assert calls[0]["total_timeout_seconds"] == 300
    assert calls[0]["allow_mutating_gates"] is False

    ledger = json.loads(Path(payload["ledger_path"]).read_text(encoding="utf-8"))
    report_path = Path(ledger["results"][0]["report_path"])
    validation_path = Path(ledger["results"][0]["validation_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    assert report["schema"] == "quality-runner-controller-report-v0.1"
    assert report["repo_path"] == str(repo_root.resolve())
    assert report["status"] == "blocked"
    assert report["baseline_artifact_path"].endswith("/.quality-runner/runs/baseline-001")
    assert report["final_qr"]["run_id"] == "stress-pass-target-repo-verify"
    assert validation["status"] == "accepted"


def test_rollout_records_invalid_repo_without_stopping(tmp_path: Path) -> None:
    valid_repo = tmp_path / "valid"
    _init_repo(valid_repo)
    missing_repo = tmp_path / "missing"

    def refresh_stub(**kwargs: Any) -> dict[str, Any]:
        repo_root = kwargs["repo_root"]
        run_id_prefix = kwargs["run_id_prefix"]
        run_dir = repo_root / ".quality-runner" / "runs" / f"{run_id_prefix}-verify"
        run_dir.mkdir(parents=True)
        return {
            "status": "clean",
            "summary": {
                "run_id": f"{run_id_prefix}-verify",
                "status": "clean",
                "recommended_classification": "clean",
                "path": str(run_dir),
                "finding_counts": {"total": 0},
                "missing_capabilities": [],
            },
        }

    payload = rollout_payload(
        repo_list_path=None,
        repos=[str(missing_repo), str(valid_repo)],
        run_id_prefix="rollout",
        output_dir=tmp_path / "artifacts",
        profile=None,
        ci_status_json=None,
        timeout_seconds=120,
        workflow_timeout_seconds=None,
        verify_timeout_seconds=None,
        workflow_timeout_reason=None,
        total_timeout_seconds=None,
        total_timeout_reason=None,
        checkout_most_advanced_branch=False,
        allow_mutating_gates=False,
        refresh_callback=refresh_stub,
    )

    assert payload["status"] == "completed-with-errors"
    assert payload["repo_count"] == 2
    assert payload["results"][0]["status"] == "invalid-repo"
    assert payload["results"][0]["report_status"] == "rejected"
    assert payload["results"][1]["report_status"] == "accepted"
    assert payload["failed_repos"] == [str(missing_repo.resolve())]


def test_rollout_human_summary_names_ledger_and_report_counts() -> None:
    summary = human_summary(
        {
            "schema": "quality-runner-rollout-result-v0.1",
            "status": "completed",
            "ledger_path": "/tmp/rollout-ledger.json",
            "repo_count": 2,
            "accepted_reports": 2,
            "rejected_reports": 0,
        }
    )

    assert "status: completed" in summary
    assert "ledger: /tmp/rollout-ledger.json" in summary
    assert "repos: 2" in summary
    assert "controller reports: 2 accepted, 0 rejected" in summary
