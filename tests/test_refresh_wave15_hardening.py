from __future__ import annotations

import json
import sys
from pathlib import Path


def test_package_manager_preflight_warns_when_workspace_lockfile_disappears(
    tmp_path: Path,
) -> None:
    from quality_runner.package_preflight import build_package_manager_preflight

    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10.0.0"}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "web").mkdir()
    scan = {
        "package_manager": "pnpm",
        "workspaces": [
            {
                "path": "web",
                "kind": "javascript",
                "manifest": "web/package.json",
                "lockfile": "web/package-lock.json",
                "package_manager": "npm",
            }
        ],
    }

    preflight = build_package_manager_preflight(tmp_path, scan)

    assert preflight["status"] == "warning"
    assert preflight["nested_lockfiles"] == []
    assert {
        "code": "missing_nested_package_manager_lockfile",
        "message": (
            "Nested JavaScript package-manager lockfile was discovered earlier "
            "but is no longer present."
        ),
        "path": "web/package-lock.json",
    } in preflight["warnings"]


def test_verify_gates_read_only_mode_skips_pre_cr_workspace_command(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / ".pre-cr.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["pre_cr"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="read-only-pre-cr",
        read_only_gates=True,
    )
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )
    plan = json.loads(Path(payload["artifact_paths"]["gate_execution_plan_json"]).read_text())

    assert payload["status"] == "blocked"
    assert verification["gates"][0]["id"] == "pre_cr"
    assert verification["gates"][0]["status"] == "skipped"
    assert verification["gates"][0]["skip_type"] == "mutating-gate-not-run"
    assert verification["gates"][0]["mutating_risk"] == "unknown"
    assert plan[0]["local_execution_status"] == "mutating-skipped"


def test_refresh_payload_finalizes_partial_verify_artifacts_when_verify_times_out(
    tmp_path: Path, monkeypatch: object
) -> None:
    from quality_runner import workflow

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": f"{sys.executable} -c 'import sys; sys.exit(0)'"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["tests"]\n',
        encoding="utf-8",
    )

    def timeout_verify(**_: object) -> dict[str, object]:
        raise TimeoutError("workflow timeout while verifying gates")

    monkeypatch.setattr(workflow, "verify_gates_payload", timeout_verify)

    payload = workflow.refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="refresh-timeout",
        workflow_timeout_seconds=30,
        workflow_timeout_reason="controller deadline exceeded while verifying gates",
    )
    run_dir = tmp_path / ".quality-runner" / "runs" / "refresh-timeout-verify"
    gate_verification = json.loads((run_dir / "gate-verification.json").read_text())
    run_summary = json.loads((run_dir / "run-summary.json").read_text())

    assert payload["status"] == "blocked"
    assert payload["runs"]["verify"]["status"] == "blocked"
    assert payload["runs"]["verify"]["timeout"]["reason"] == (
        "controller deadline exceeded while verifying gates"
    )
    assert payload["runs"]["verify"]["timeout"]["timeout_scope"] == "verify-phase"
    assert payload["summary"]["recommended_classification"] == "workflow-timeout-blocker"
    assert gate_verification["status"] == "blocked"
    assert gate_verification["failure_type"] == "workflow-timeout"
    assert gate_verification["reason"] == "controller deadline exceeded while verifying gates"
    assert gate_verification["timeout_scope"] == "verify-phase"
    assert gate_verification["gates"] == [
        {
            "failure_type": "workflow-timeout",
            "id": "workflow-timeout",
            "phase": "verify-gates",
            "reason": "controller deadline exceeded while verifying gates",
            "recommended_action": (
                "Inspect workflow-timeout.json and rerun refresh with tighter scan exclusions "
                "or a larger total timeout"
            ),
            "status": "failed",
        }
    ]
    assert json.loads((run_dir / "gate-execution-plan.json").read_text()) == []
    assert run_summary["recommended_classification"] == "workflow-timeout-blocker"


def test_refresh_payload_total_timeout_writes_agent_handoff_when_inspect_times_out(
    tmp_path: Path, monkeypatch: object
) -> None:
    from quality_runner import workflow

    def inspect_timeout(**_: object) -> dict[str, object]:
        raise TimeoutError("controller full refresh budget")

    monkeypatch.setattr(workflow, "inspect_payload", inspect_timeout)

    payload = workflow.refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="refresh-inspect-timeout",
        workflow_timeout_seconds=60,
        total_timeout_seconds=30,
        total_timeout_reason="controller full refresh budget",
    )
    run_dir = tmp_path / ".quality-runner" / "runs" / "refresh-inspect-timeout-verify"
    handoff = json.loads((run_dir / "agent-handoff.json").read_text())
    handoff_markdown = (run_dir / "agent-handoff.md").read_text()
    timeout_artifact = json.loads((run_dir / "workflow-timeout.json").read_text())

    assert payload["status"] == "blocked"
    assert handoff["schema"] == "quality-runner-agent-handoff-v0.2"
    assert handoff["status"] == "gates-blocked"
    assert handoff["gate_verification"]["primary_blocker_class"] == "workflow-timeout"
    assert handoff["gate_verification"]["blocker_groups"] == [
        {"class": "workflow-timeout", "gate_ids": ["workflow-timeout"]}
    ]
    assert handoff["next_slice"]["action_groups"] == [
        {
            "class": "workflow-timeout",
            "gate_ids": ["workflow-timeout"],
            "actions": [
                "Inspect workflow-timeout.json and rerun refresh with tighter scan exclusions "
                "or a larger total timeout."
            ],
        }
    ]
    assert "workflow-timeout" in handoff_markdown
    assert timeout_artifact["phase"] == "inspect"
    assert timeout_artifact["diagnostics"]["scan_progress"]["last_directory"] is None
    assert timeout_artifact["diagnostics"]["scan_progress"]["last_paths"] == []
