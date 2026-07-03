from __future__ import annotations

import json
import signal
import sys
from pathlib import Path

import pytest

from test_support.quality_runner_fixtures import write_complete_js_fixture


def test_run_payload_records_package_manager_mismatch_in_audit_and_plan(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_complete_js_fixture(tmp_path)
    package_json_path = tmp_path / "package.json"
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    package_json["packageManager"] = "npm@10.0.0"
    package_json_path.write_text(json.dumps(package_json), encoding="utf-8")

    payload = run_payload(repo_root=tmp_path, run_id="mismatch-run", profile="default")
    audit_report = json.loads(Path(payload["artifact_paths"]["quality_audit_json"]).read_text())
    remediation_plan = json.loads(
        Path(payload["artifact_paths"]["remediation_plan_json"]).read_text()
    )

    mismatch_finding = next(
        finding
        for finding in audit_report["findings"]
        if finding["id"] == "standard-package-manager-mismatch"
    )
    assert mismatch_finding["severity"] == "warning"
    assert mismatch_finding["evidence"] == [
        "Expected package manager: pnpm.",
        "Detected package manager: npm.",
        "Package manager source: package.json packageManager or lockfile discovery.",
    ]
    assert (
        mismatch_finding["recommended_fix"]
        == "Align JavaScript dependency management to the pnpm standard."
    )
    assert any(
        slice_item["findings"][0]["id"] == "standard-package-manager-mismatch"
        for slice_item in remediation_plan["slices"]
    )


def test_inspect_payload_writes_package_manager_preflight_artifact(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    write_complete_js_fixture(tmp_path)
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")

    payload = inspect_payload(repo_root=tmp_path, run_id="package-preflight-run", profile="default")
    preflight = json.loads(
        Path(payload["artifact_paths"]["package_manager_preflight_json"]).read_text()
    )

    assert preflight["schema"] == "quality-runner-package-manager-preflight-v0.1"
    assert preflight["status"] == "warning"
    assert preflight["package_manager"] == "pnpm"
    assert preflight["lockfiles"] == ["package-lock.json", "pnpm-lock.yaml"]
    assert preflight["warnings"] == [
        {
            "code": "multiple_lockfiles",
            "message": "Multiple JavaScript package-manager lockfiles are present.",
            "path": ".",
        }
    ]


def test_package_manager_preflight_reports_nested_lockfiles(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10.0.0", "scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    (dashboard / "package.json").write_text(
        json.dumps({"scripts": {"build": "next build"}}),
        encoding="utf-8",
    )
    (dashboard / "package-lock.json").write_text("{}\n", encoding="utf-8")

    payload = inspect_payload(repo_root=tmp_path, run_id="nested-lockfile-preflight")
    preflight = json.loads(
        Path(payload["artifact_paths"]["package_manager_preflight_json"]).read_text()
    )

    assert preflight["status"] == "warning"
    assert preflight["nested_lockfiles"] == [
        {"path": "dashboard/package-lock.json", "package_manager": "npm"}
    ]
    assert {
        "code": "nested_package_manager_lockfiles",
        "message": "Nested JavaScript package-manager lockfiles are present.",
        "path": ".",
    } in preflight["warnings"]


def test_verify_gates_payload_executes_discovered_gates_and_marks_capabilities(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "lint": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                    "test": f"{sys.executable} -c 'import sys; sys.exit(1)'",
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["lint", "tests"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="verify-gates-run", profile="default")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )
    capability_map = json.loads(
        Path(payload["artifact_paths"]["capability_matrix_json"]).read_text()
    )
    handoff = json.loads(Path(payload["artifact_paths"]["agent_handoff_json"]).read_text())
    handoff_markdown = Path(payload["artifact_paths"]["agent_handoff_md"]).read_text()

    assert payload["schema"] == "quality-runner-verify-gates-result-v0.1"
    assert payload["status"] == "failed"
    assert verification["schema"] == "quality-runner-gate-verification-v0.1"
    assert [
        (gate["id"], gate["status"], gate["exit_code"], gate["stderr_tail"])
        for gate in verification["gates"]
    ] == [
        ("lint", "passed", 0, ""),
        ("tests", "failed", 1, ""),
    ]
    assert [(gate["id"], gate["status"], gate["exit_code"]) for gate in verification["gates"]] == [
        ("lint", "passed", 0),
        ("tests", "failed", 1),
    ]
    states = {
        capability["id"]: capability["verification_state"]
        for capability in capability_map["available"]
    }
    assert states["lint"] == {
        "discovery": "command-discovered",
        "execution": "local-executed",
        "result": "passed",
    }
    assert states["tests"] == {
        "discovery": "command-discovered",
        "execution": "local-executed",
        "result": "failed",
    }
    assert handoff["status"] == "gates-failed"
    assert "gate_verification_json" in handoff["artifact_paths"]
    assert handoff["gate_verification"]["status"] == "failed"
    assert handoff["gate_verification"]["recommended_classification"] == (
        "failing-executable-gates"
    )
    assert handoff["gate_verification"]["primary_blocker_class"] == "command-failure"
    assert handoff["gate_verification"]["blocker_groups"] == [
        {"class": "command-failure", "gate_ids": ["tests"]}
    ]
    assert handoff["gate_verification"]["blockers"] == [
        {
            "id": "tests",
            "status": "failed",
            "failure_type": "command-failed",
            "command": f"{sys.executable} -c 'import sys; sys.exit(1)'",
            "blocker_class": "command-failure",
        }
    ]
    assert handoff["next_slice"]["id"] == "resolve-gate-verification-blockers"
    assert handoff["next_slice"]["title"] == "Resolve failing executable gates"
    assert handoff["next_slice"]["findings"][0]["id"] == "gate-tests"
    assert handoff["next_slice"]["actions"][0] == "Resolve command-failure blockers first: tests."
    assert "Run `" in handoff["next_slice"]["actions"][1]
    assert "## Gate Verification" in handoff_markdown
    assert "- Recommended classification: failing-executable-gates" in handoff_markdown
    assert "- tests: failed (command-failed)." in handoff_markdown


def test_verify_gates_runs_package_scripts_through_detected_package_manager(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import verify_gates_payload

    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    fake_lint = bin_dir / "fake-lint"
    fake_lint.write_text("#!/bin/sh\necho package-bin-ok\n", encoding="utf-8")
    fake_lint.chmod(0o755)
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {"lint": "fake-lint"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="package-manager-gates")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "passed"
    assert verification["gates"][0]["command"] == "pnpm run lint"
    assert "package-bin-ok\n" in verification["gates"][0]["stdout_tail"]


def test_verify_gates_read_only_mode_skips_mutating_formatter(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "format": "eslint --fix .",
                    "test": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["formatter", "tests"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="read-only-mutating",
        read_only_gates=True,
    )
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )
    plan = json.loads(Path(payload["artifact_paths"]["gate_execution_plan_json"]).read_text())

    assert payload["status"] == "blocked"
    assert verification["status"] == "blocked"
    assert verification["gates"][0]["status"] == "skipped"
    assert verification["gates"][0]["skip_type"] == "mutating-gate-not-run"
    assert verification["gates"][0]["mutating_risk"] == "mutating"
    assert verification["gates"][1]["status"] == "passed"
    assert plan[0]["local_execution_status"] == "mutating-skipped"


def test_verify_gates_classifies_dependency_setup_blockers(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "lint": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                    "test": (
                        f"{sys.executable} -c "
                        "\"import sys; "
                        "print('ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY', file=sys.stderr); "
                        "sys.exit(1)\""
                    ),
                    "build": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint", "tests", "build"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="dependency-setup")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "blocked"
    assert verification["gates"][0]["id"] == "lint"
    assert verification["gates"][0]["status"] == "passed"
    assert verification["gates"][1]["id"] == "tests"
    assert verification["gates"][1]["failure_type"] == "dependency-setup-blocker"
    setup = verification["gates"][1]["diagnostics"]["dependency_setup"]
    assert setup["package_manager"] == "pnpm"
    assert setup["setup_command"] == "pnpm install --frozen-lockfile"
    assert setup["cause"] == (
        "pnpm needs to remove and reinstall node_modules but cannot prompt "
        "in a non-interactive gate run"
    )
    assert "pnpm install --frozen-lockfile" in verification["gates"][1]["recommended_action"]
    assert "interactive shell" in verification["gates"][1]["recommended_action"]
    assert verification["gates"][2]["id"] == "build"
    assert verification["gates"][2]["status"] == "skipped"
    assert verification["gates"][2]["skip_type"] == "dependency-setup-blocked"
    assert verification["gates"][2]["failure_type"] == "dependency-setup-blocker"
    assert verification["gates"][2]["blocked_by"] == "tests"
    assert verification["gates"][2]["diagnostics"]["dependency_setup"]["package_manager"] == "pnpm"


def test_verify_gates_classifies_pnpm_ignored_builds_as_dependency_setup(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "lint": (
                        f"{sys.executable} -c "
                        "\"import sys; "
                        "print('[ERR_PNPM_IGNORED_BUILDS] Ignored build scripts: sharp'); "
                        "print('Run \\'pnpm approve-builds\\' to pick which dependencies should be allowed'); "
                        "sys.exit(1)\""
                    ),
                    "test": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint", "tests"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="pnpm-ignored-builds")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )
    handoff = json.loads(Path(payload["artifact_paths"]["agent_handoff_json"]).read_text())
    handoff_markdown = Path(payload["artifact_paths"]["agent_handoff_md"]).read_text()

    assert payload["status"] == "blocked"
    assert verification["gates"][0]["id"] == "lint"
    assert verification["gates"][0]["failure_type"] == "dependency-setup-blocker"
    setup = verification["gates"][0]["diagnostics"]["dependency_setup"]
    assert setup["package_manager"] == "pnpm"
    assert setup["setup_command"] == "pnpm approve-builds"
    assert "approve-builds" in verification["gates"][0]["recommended_action"]
    assert verification["gates"][1]["id"] == "tests"
    assert verification["gates"][1]["status"] == "skipped"
    assert verification["gates"][1]["skip_type"] == "dependency-setup-blocked"
    assert verification["gates"][1]["blocked_by"] == "lint"
    assert (
        verification["gates"][1]["diagnostics"]["dependency_setup"]["setup_command"]
        == "pnpm approve-builds"
    )
    assert handoff["gate_verification"]["recommended_classification"] == (
        "environment-or-dependency-blocker"
    )
    assert handoff["status"] == "gates-blocked"
    assert handoff["gate_verification"]["primary_blocker_class"] == "dependency-setup"
    assert handoff["gate_verification"]["blocker_groups"] == [
        {"class": "dependency-setup", "gate_ids": ["lint", "tests"]}
    ]
    assert handoff["gate_verification"]["blockers"][0]["dependency_setup"] == {
        "package_manager": "pnpm",
        "setup_command": "pnpm approve-builds",
    }
    assert handoff["gate_verification"]["blockers"][0]["blocker_class"] == "dependency-setup"
    assert handoff["gate_verification"]["blockers"][1]["skip_type"] == "dependency-setup-blocked"
    assert handoff["gate_verification"]["blockers"][1]["blocked_by"] == "lint"
    assert handoff["next_slice"]["id"] == "resolve-gate-verification-blockers"
    assert handoff["next_slice"]["title"] == "Resolve dependency setup gate blockers"
    assert handoff["next_slice"]["actions"][0] == (
        "Resolve dependency-setup blockers first: lint, tests."
    )
    assert handoff["next_slice"]["actions"][1] == (
        "Run dependency setup once for lint, tests: pnpm approve-builds."
    )
    assert handoff["next_slice"]["actions"] == [
        "Resolve dependency-setup blockers first: lint, tests.",
        "Run dependency setup once for lint, tests: pnpm approve-builds.",
    ]
    assert handoff["next_slice"]["action_groups"] == [
        {
            "class": "dependency-setup",
            "gate_ids": ["lint", "tests"],
            "actions": ["Run dependency setup once: pnpm approve-builds."],
        }
    ]
    assert "Setup: `pnpm approve-builds`" in handoff_markdown
    assert "- Recommended classification: environment-or-dependency-blocker" in handoff_markdown
    assert "- Primary blocker class: dependency-setup" in handoff_markdown


def test_verify_gates_classifies_next_font_fetch_as_environment_restricted(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "build": (
                        f"{sys.executable} -c "
                        "\"import sys; "
                        "print('next/font failed to fetch fonts.googleapis.com', file=sys.stderr); "
                        "sys.exit(1)\""
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["build"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="next-font-fetch")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "blocked"
    assert verification["gates"][0]["failure_type"] == "environment-restricted"


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
    assert gate_verification["gates"] == []
    assert json.loads((run_dir / "gate-execution-plan.json").read_text()) == []
    assert run_summary["recommended_classification"] == "workflow-timeout-blocker"


def test_refresh_payload_preserves_partial_verify_artifacts_when_timeout_finalizes(
    tmp_path: Path, monkeypatch: object
) -> None:
    from quality_runner import workflow

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": f"{sys.executable} -c 'import sys; sys.exit(0)'"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint", "tests"]\n',
        encoding="utf-8",
    )

    def timeout_verify(*, repo_root: Path, run_id: str, **_: object) -> dict[str, object]:
        run_dir = repo_root / ".quality-runner" / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "gate-execution-plan.json").write_text(
            json.dumps(
                [
                    {"id": "lint", "command": "pnpm lint"},
                    {"id": "tests", "command": "pnpm test"},
                ]
            ),
            encoding="utf-8",
        )
        (run_dir / "gate-verification.json").write_text(
            json.dumps(
                {
                    "schema": "quality-runner-gate-verification-v0.1",
                    "run_id": run_id,
                    "status": "blocked",
                    "timeout_seconds": 90,
                    "gates": [
                        {
                            "id": "lint",
                            "status": "passed",
                            "duration_seconds": 12.5,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        raise TimeoutError("workflow timeout while verifying gates")

    monkeypatch.setattr(workflow, "verify_gates_payload", timeout_verify)

    workflow.refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="refresh-timeout-preserve",
        workflow_timeout_seconds=30,
        workflow_timeout_reason="controller deadline exceeded while verifying gates",
    )
    run_dir = tmp_path / ".quality-runner" / "runs" / "refresh-timeout-preserve-verify"
    gate_plan = json.loads((run_dir / "gate-execution-plan.json").read_text())
    gate_verification = json.loads((run_dir / "gate-verification.json").read_text())
    run_summary = json.loads((run_dir / "run-summary.json").read_text())

    assert [gate["id"] for gate in gate_plan] == ["lint", "tests"]
    assert gate_verification["status"] == "blocked"
    assert gate_verification["failure_type"] == "workflow-timeout"
    assert gate_verification["reason"] == "controller deadline exceeded while verifying gates"
    assert gate_verification["timeout_scope"] == "verify-phase"
    assert gate_verification["gates"] == [
        {
            "duration_seconds": 12.5,
            "id": "lint",
            "status": "passed",
        }
    ]
    assert run_summary["recommended_classification"] == "workflow-timeout-blocker"
    assert run_summary["gate_results"] == [
        {
            "duration_seconds": 12.5,
            "id": "lint",
            "status": "passed",
        }
    ]


def test_refresh_payload_records_timeout_contract_and_phase_timings(
    tmp_path: Path, monkeypatch: object
) -> None:
    from quality_runner import workflow

    def inspect_stub(**_: object) -> dict[str, object]:
        return {"status": "inspected", "run_id": "refresh-contract-inspect"}

    def run_stub(**_: object) -> dict[str, object]:
        return {"status": "findings", "run_id": "refresh-contract-run"}

    def verify_stub(**_: object) -> dict[str, object]:
        return {"status": "passed", "run_id": "refresh-contract-verify"}

    def summary_stub(**_: object) -> dict[str, object]:
        return {"status": "clean", "run_id": "refresh-contract-verify"}

    monkeypatch.setattr(workflow, "inspect_payload", inspect_stub)
    monkeypatch.setattr(workflow, "run_payload", run_stub)
    monkeypatch.setattr(workflow, "verify_gates_payload", verify_stub)
    monkeypatch.setattr(workflow, "build_run_summary", summary_stub)

    payload = workflow.refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="refresh-contract",
        timeout_seconds=9,
        verify_timeout_seconds=17,
        total_timeout_seconds=45,
        total_timeout_reason="controller full refresh budget",
    )

    assert payload["timeout_contract"] == {
        "per_gate_timeout_seconds": 9,
        "verify_timeout_seconds": 17,
        "verify_timeout_source": "explicit",
        "total_timeout_seconds": 45,
        "total_timeout_reason": "controller full refresh budget",
    }
    assert payload["phase_timings"].keys() == {"inspect", "run", "verify"}
    assert all(timing["elapsed_seconds"] >= 0 for timing in payload["phase_timings"].values())


def test_refresh_payload_total_timeout_finalizes_when_run_phase_is_interrupted(
    tmp_path: Path, monkeypatch: object
) -> None:
    from quality_runner import workflow

    def inspect_stub(**_: object) -> dict[str, object]:
        return {"status": "inspected", "run_id": "refresh-total-timeout-inspect"}

    def run_timeout(**_: object) -> dict[str, object]:
        raise TimeoutError("controller full refresh budget")

    monkeypatch.setattr(workflow, "inspect_payload", inspect_stub)
    monkeypatch.setattr(workflow, "run_payload", run_timeout)

    payload = workflow.refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="refresh-total-timeout",
        workflow_timeout_seconds=60,
        total_timeout_seconds=30,
        total_timeout_reason="controller full refresh budget",
    )
    run_dir = tmp_path / ".quality-runner" / "runs" / "refresh-total-timeout-verify"
    gate_verification = json.loads((run_dir / "gate-verification.json").read_text())
    timeout_artifact = json.loads((run_dir / "workflow-timeout.json").read_text())

    assert payload["status"] == "blocked"
    assert payload["runs"]["run"]["status"] == "blocked"
    assert payload["runs"]["run"]["failure_type"] == "workflow-timeout"
    assert payload["runs"]["verify"]["timeout"]["phase"] == "run"
    assert payload["runs"]["verify"]["timeout"]["reason"] == "controller full refresh budget"
    assert payload["runs"]["verify"]["timeout"]["timeout_scope"] == "total-refresh"
    assert payload["timeout_contract"]["total_timeout_seconds"] == 30
    assert payload["phase_timings"]["run"]["status"] == "timeout"
    assert gate_verification["phase"] == "run"
    assert gate_verification["reason"] == "controller full refresh budget"
    assert gate_verification["timeout_scope"] == "total-refresh"
    assert timeout_artifact["phase"] == "run"
    assert timeout_artifact["timeout_scope"] == "total-refresh"


def test_refresh_payload_total_timeout_scope_is_distinct_from_verify_phase(
    tmp_path: Path, monkeypatch: object
) -> None:
    from quality_runner import workflow

    def inspect_stub(**_: object) -> dict[str, object]:
        return {"status": "inspected", "run_id": "refresh-total-scope-inspect"}

    def run_stub(**_: object) -> dict[str, object]:
        return {"status": "planned", "run_id": "refresh-total-scope-run"}

    def verify_timeout(**_: object) -> dict[str, object]:
        raise TimeoutError("controller full refresh budget")

    monkeypatch.setattr(workflow, "inspect_payload", inspect_stub)
    monkeypatch.setattr(workflow, "run_payload", run_stub)
    monkeypatch.setattr(workflow, "verify_gates_payload", verify_timeout)

    payload = workflow.refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="refresh-total-scope",
        workflow_timeout_seconds=60,
        total_timeout_seconds=30,
        total_timeout_reason="controller full refresh budget",
    )
    run_dir = tmp_path / ".quality-runner" / "runs" / "refresh-total-scope-verify"
    gate_verification = json.loads((run_dir / "gate-verification.json").read_text())
    timeout_artifact = json.loads((run_dir / "workflow-timeout.json").read_text())

    assert payload["runs"]["verify"]["timeout"]["phase"] == "verify-gates"
    assert payload["runs"]["verify"]["timeout"]["timeout_scope"] == "total-refresh"
    assert gate_verification["phase"] == "verify-gates"
    assert gate_verification["timeout_scope"] == "total-refresh"
    assert timeout_artifact["phase"] == "verify-gates"
    assert timeout_artifact["timeout_scope"] == "total-refresh"


def test_verify_gate_kills_process_group_when_workflow_timeout_interrupts(
    tmp_path: Path, monkeypatch: object
) -> None:
    from quality_runner import gate_verification

    killed_groups: list[tuple[int, int]] = []

    class FakeProcess:
        pid = 12345
        returncode = None

        def communicate(self, timeout: int) -> tuple[str, str]:
            assert timeout == 120
            raise TimeoutError("workflow deadline")

    def fake_popen(*_: object, **kwargs: object) -> FakeProcess:
        assert kwargs["start_new_session"] is True
        return FakeProcess()

    monkeypatch.setattr(gate_verification.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(gate_verification.os, "getpgid", lambda pid: pid + 1)
    monkeypatch.setattr(
        gate_verification.os,
        "killpg",
        lambda pgid, sig: killed_groups.append((pgid, sig)),
    )

    with pytest.raises(TimeoutError, match="workflow deadline"):
        gate_verification.verify_discovered_gates(
            repo_root=tmp_path,
            capability_map={
                "available": [
                    {
                        "id": "tests",
                        "type": "script",
                        "command": "pnpm test",
                        "source": "package.json",
                    }
                ]
            },
            run_id="workflow-interrupt",
        )

    assert killed_groups == [(12346, signal.SIGTERM)]


def test_verify_gates_skips_ci_only_pseudo_gates(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "on:\n  pull_request:\njobs:\n  quality:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["pre_pr"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="ci-only-gates")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "skipped-nonlocal"
    assert verification["gates"] == [
        {
            "id": "pre_pr",
            "status": "skipped",
            "capability_kind": "ci_only",
            "reason": "capability is CI-only and has no local executor",
            "source": ".github/workflows",
        }
    ]


def test_verify_gates_does_not_block_on_file_evidence_capabilities(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    tracker = tmp_path / ".tracker"
    tracker.mkdir()
    (tracker / "PROJECT_TRUTH.md").write_text("# Truth\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": f"{sys.executable} -c 'import sys; sys.exit(0)'"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["tests", "truth_file"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="file-evidence")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "passed"
    assert [(gate["id"], gate["status"]) for gate in verification["gates"]] == [
        ("tests", "passed"),
        ("truth_file", "skipped"),
    ]
    assert verification["gates"][1]["capability_kind"] == "evidence_file"
    assert verification["gates"][1]["reason"] == "capability is file evidence, not an executable gate"


def test_verify_gates_classifies_environment_restricted_failures(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": (
                        f"{sys.executable} -c "
                        "\"import sys; print('listen EPERM 127.0.0.1', file=sys.stderr); sys.exit(1)\""
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["tests"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="environment-restricted")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "blocked"
    assert verification["status"] == "blocked"
    assert verification["run_id"] == "environment-restricted"
    assert verification["gates"][0]["failure_type"] == "environment-restricted"
    assert "rerun outside sandbox" in verification["gates"][0]["recommended_action"]


def test_verify_gates_classifies_test_server_timeout_as_environment_restricted(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": (
                        f"{sys.executable} -c "
                        "\"import sys; "
                        "print('Error: Test timed out in 15000ms', file=sys.stderr); "
                        "print('Error: Server is not running.', file=sys.stderr); "
                        "sys.exit(1)\""
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["tests"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="test-server-timeout")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "blocked"
    assert verification["status"] == "blocked"
    assert verification["gates"][0]["failure_type"] == "environment-restricted"
    assert "rerun the exact command directly from the repo root" in verification["gates"][0][
        "recommended_action"
    ]


def test_verify_gates_keeps_plain_test_failures_as_command_failures(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": (
                        f"{sys.executable} -c "
                        "\"import sys; print('AssertionError: expected true', file=sys.stderr); "
                        "sys.exit(1)\""
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["tests"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="plain-test-failure")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "failed"
    assert verification["status"] == "failed"
    assert verification["gates"][0]["failure_type"] == "command-failed"
    assert "recommended_action" not in verification["gates"][0]


def test_verify_gates_uses_per_gate_timeout_config_and_skips_covered_aggregate(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "lint": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                    "pre-cr": "pnpm run lint",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["lint", "pre_cr"]',
                "",
                "[quality_runner.gate_timeouts]",
                "lint = 9",
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="aggregate-skip")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "passed"
    assert verification["timeout_seconds"] == 120
    assert verification["gate_timeouts"] == {"lint": 9}
    assert [(gate["id"], gate["status"]) for gate in verification["gates"]] == [
        ("lint", "passed"),
        ("pre_cr", "skipped"),
    ]
    assert verification["gates"][0]["timeout_seconds"] == 9
    assert verification["gates"][1]["reason"] == "aggregate gate covered by leaf gates"
    assert verification["gates"][1]["covered_by"] == ["lint"]


def test_verify_gates_runs_cheap_gates_before_expensive_gates(tmp_path: Path) -> None:
    from quality_runner.gate_verification import verify_discovered_gates

    capability_map = {
        "available": [
            {
                "id": "build",
                "type": "script",
                "command": f"{sys.executable} -c \"print('build')\"",
                "source": "package.json",
            },
            {
                "id": "lint",
                "type": "script",
                "command": f"{sys.executable} -c \"print('lint')\"",
                "source": "package.json",
            },
            {
                "id": "typecheck",
                "type": "script",
                "command": f"{sys.executable} -c \"print('typecheck')\"",
                "source": "package.json",
            },
        ]
    }

    verification = verify_discovered_gates(
        repo_root=tmp_path,
        capability_map=capability_map,
        run_id="ordered-gates",
    )

    assert [gate["id"] for gate in verification["gates"]] == [
        "lint",
        "typecheck",
        "build",
    ]
    assert [gate["id"] for gate in verification["execution_plan"]] == [
        "lint",
        "typecheck",
        "build",
    ]


def test_verify_gates_streams_partial_results_after_each_gate(tmp_path: Path) -> None:
    from quality_runner.gate_verification import verify_discovered_gates

    seen_counts: list[int] = []

    def record_partial(verification: dict[str, object]) -> None:
        gates = verification.get("gates")
        assert isinstance(gates, list)
        seen_counts.append(len(gates))

    capability_map = {
        "available": [
            {
                "id": "lint",
                "type": "script",
                "command": f"{sys.executable} -c \"print('lint')\"",
                "source": "package.json",
            },
            {
                "id": "typecheck",
                "type": "script",
                "command": f"{sys.executable} -c \"print('typecheck')\"",
                "source": "package.json",
            },
        ]
    }

    verify_discovered_gates(
        repo_root=tmp_path,
        capability_map=capability_map,
        run_id="partial-gates",
        on_partial_result=record_partial,
    )

    assert seen_counts == [1, 2]
