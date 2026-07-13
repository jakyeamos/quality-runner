from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

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


def _write_qr_artifacts(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "quality-audit.json").write_text(
        json.dumps(
            {
                "schema": "quality-runner-audit-report-v0.1",
                "status": "findings",
                "findings": [
                    {
                        "id": "missing-runtime-smoke",
                        "severity": "warning",
                        "category": "capability",
                        "summary": "Required quality capability is missing: runtime_smoke.",
                        "evidence": ["capability matrix: runtime_smoke absent"],
                        "recommended_fix": "Add a runtime smoke gate.",
                        "verification": ["Run the runtime smoke gate."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "capability-matrix.json").write_text(
        json.dumps(
            {
                "schema": "quality-runner-capability-map-v0.1",
                "available": [],
                "missing": [{"id": "runtime_smoke"}],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "remediation-plan.json").write_text(
        json.dumps(
            {
                "schema": "quality-runner-remediation-plan-v0.1",
                "slices": [
                    {
                        "id": "add-runtime-smoke",
                        "title": "Add runtime smoke coverage",
                        "priority": "medium",
                        "score": 20,
                        "findings": [
                            {
                                "id": "missing-runtime-smoke",
                                "severity": "warning",
                                "category": "capability",
                                "summary": "Required quality capability is missing: runtime_smoke.",
                            }
                        ],
                        "actions": ["Add a smoke command and document it."],
                        "verification_gates": ["Run the smoke command."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "agent-handoff.md").write_text("# Handoff\n", encoding="utf-8")
    (run_dir / "resolution-ledger.md").write_text("# Ledger\n", encoding="utf-8")
    (run_dir / "code-quality-scan.json").write_text(
        json.dumps({"schema": "quality-runner-code-quality-scan-v0.1"}),
        encoding="utf-8",
    )
    (run_dir / "run-manifest.json").write_text(
        json.dumps({"schema": "quality-runner-run-manifest-v0.1"}),
        encoding="utf-8",
    )


def test_rollout_runs_repo_list_and_writes_controller_report(tmp_path: Path) -> None:
    repo_root = tmp_path / "target-repo"
    _init_repo(repo_root)
    repo_list = tmp_path / "repos.txt"
    repo_list.write_text(f"{repo_root} baseline-001 target-repo\n", encoding="utf-8")
    output_dir = tmp_path / "rollout-artifacts"
    expected_run_dir = repo_root / ".quality-runner" / "runs" / "stress-pass-target-repo-verify"
    calls: list[dict[str, Any]] = []

    def refresh_stub(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        run_id_prefix = kwargs["run_id_prefix"]
        run_dir = repo_root / ".quality-runner" / "runs" / f"{run_id_prefix}-verify"
        _write_qr_artifacts(run_dir)
        return {
            "status": "blocked",
            "summary": {
                "run_id": f"{run_id_prefix}-verify",
                "status": "blocked",
                "recommended_classification": "broad-repo-debt",
                "path": str(run_dir),
                "finding_counts": {"total": 1, "by_category": {"capability": 1}},
                "missing_capabilities": ["runtime_smoke"],
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
        execute_discovered_gates=True,
        worktree_mode="disposable",
        allow_dirty_worktree_verify=True,
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
    assert calls[0]["execute_discovered_gates"] is True
    assert calls[0]["worktree_mode"] == "disposable"
    assert calls[0]["allow_dirty_worktree_verify"] is True

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
    generation_command = report["verification"][0]["command"]
    assert "--execute-gates --worktree-mode disposable" in generation_command
    assert "--allow-dirty-worktree-verify" in generation_command
    assert validation["status"] == "accepted"

    fleet_documents = payload["fleet_documents"]
    index_path = Path(fleet_documents["index_md"])
    phase_path = Path(fleet_documents["phase_md"])
    repo_doc_path = output_dir / "per-repo-summaries" / "001-target-repo.md"
    ledger_documents = ledger["fleet_documents"]

    assert ledger_documents == fleet_documents
    assert index_path.exists()
    assert phase_path.exists()
    assert repo_doc_path.exists()
    assert "target-repo" in index_path.read_text(encoding="utf-8")
    assert "Phase 1 - Quick Closers" in phase_path.read_text(encoding="utf-8")
    repo_doc = repo_doc_path.read_text(encoding="utf-8")
    assert "# target-repo" in repo_doc
    assert "Required quality capability is missing: runtime_smoke." in repo_doc
    assert "Add runtime smoke coverage" in repo_doc
    assert str(expected_run_dir / "quality-audit.json") in repo_doc


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


def test_rollout_rejects_gate_execution_without_disposable_worktrees(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires --worktree-mode disposable"):
        rollout_payload(
            repo_list_path=None,
            repos=[str(tmp_path)],
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
            execute_discovered_gates=True,
            worktree_mode="in-place",
        )


def test_rollout_rejects_symlinked_output_directory(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    output_dir = tmp_path / "output-link"
    output_dir.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        rollout_payload(
            repo_list_path=None,
            repos=[str(tmp_path / "missing")],
            run_id_prefix="rollout",
            output_dir=output_dir,
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
        )

    assert not list(external.iterdir())


def test_rollout_does_not_overwrite_a_symlinked_ledger(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    external = tmp_path / "external-ledger.json"
    external.write_text("sentinel\n", encoding="utf-8")
    (output_dir / "rollout-ledger.json").symlink_to(external)

    with pytest.raises(ValueError, match="symlink"):
        rollout_payload(
            repo_list_path=None,
            repos=[str(tmp_path / "missing")],
            run_id_prefix="rollout",
            output_dir=output_dir,
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
        )

    assert external.read_text(encoding="utf-8") == "sentinel\n"


def test_rollout_human_summary_names_ledger_and_report_counts() -> None:
    summary = human_summary(
        {
            "schema": "quality-runner-rollout-result-v0.1",
            "status": "completed",
            "ledger_path": "/tmp/rollout-ledger.json",
            "repo_count": 2,
            "accepted_reports": 2,
            "rejected_reports": 0,
            "fleet_documents": {
                "index_md": "/tmp/per-repo-summaries/INDEX.md",
                "phase_md": "/tmp/fleet-remediation-phases.md",
            },
        }
    )

    assert "status: completed" in summary
    assert "ledger: /tmp/rollout-ledger.json" in summary
    assert "repos: 2" in summary
    assert "controller reports: 2 accepted, 0 rejected" in summary
    assert "repo docs: /tmp/per-repo-summaries/INDEX.md" in summary
    assert "phase draft: /tmp/fleet-remediation-phases.md" in summary
