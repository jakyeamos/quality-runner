from __future__ import annotations

import json
from pathlib import Path

import pytest

from quality_runner.cli import main
from quality_runner.phase_automation import auto_plan
from quality_runner.phase_planning import (
    add_phase,
    close_phase,
    initialize_plan,
    next_plan,
    plan_phase,
    plan_status,
    record_batch,
    update_phase,
    verify_phase,
)
from quality_runner.schema_constants import PHASE_BATCH_RESULT_SCHEMA


def _slice(
    slice_id: str,
    *,
    priority: str,
    fingerprint: str,
    depends_on: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": slice_id,
        "title": f"Remediate {slice_id}",
        "priority": priority,
        "depends_on": depends_on or [],
        "findings": [{"id": f"finding-{slice_id}", "fingerprint": fingerprint}],
        "scope": {"in_scope": [f"src/{slice_id}.py"], "out_of_scope": ["unrelated work"]},
        "actions": [f"Update {slice_id}"],
        "verification_gates": [f"Run verification for {slice_id}"],
        "stop_conditions": [f"Stop if {slice_id} changes scope"],
    }


def _write_run(repo_root: Path, run_id: str, slices: list[dict[str, object]]) -> Path:
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    run_dir.mkdir(parents=True)
    plan_path = run_dir / "remediation-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema": "quality-runner-remediation-plan-v0.1",
                "run_id": run_id,
                "slices": slices,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "agent-handoff.json").write_text(
        json.dumps(
            {
                "schema": "quality-runner-agent-handoff-v0.2",
                "run_id": run_id,
                "artifact_paths": {"remediation_plan_json": str(plan_path)},
            }
        ),
        encoding="utf-8",
    )
    return plan_path


def _write_delta(repo_root: Path, run_id: str) -> None:
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    (run_dir / "remediation-delta.json").write_text(
        json.dumps(
            {
                "schema": "quality-runner-remediation-delta-v0.1",
                "findings": {
                    "new": [{"fingerprint": "fp-new", "summary": "New finding"}],
                    "persisted": [{"fingerprint": "fp-persisted", "summary": "Persisted finding"}],
                    "resolved": [{"fingerprint": "fp-resolved", "summary": "Resolved finding"}],
                },
                "verification": {"current": {"status": "passed", "blockers": []}},
            }
        ),
        encoding="utf-8",
    )


def _batch_result(path: Path, *, status: str = "complete") -> None:
    path.write_text(
        json.dumps(
            {
                "schema": PHASE_BATCH_RESULT_SCHEMA,
                "status": status,
                "summary": "External batch completed.",
                "verification": [{"command": "focused-check", "status": "passed"}],
                "qr_run_id": "run-final",
                "commit": "abc123",
                "remaining_findings": [],
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )


def test_plan_init_is_idempotent_and_does_not_touch_root_gsd_files(tmp_path: Path) -> None:
    root_planning = tmp_path / ".planning"
    root_planning.mkdir()
    roadmap = root_planning / "ROADMAP.md"
    state = root_planning / "STATE.md"
    roadmap.write_text("existing gsd roadmap\n", encoding="utf-8")
    state.write_text("existing gsd state\n", encoding="utf-8")

    first = initialize_plan(tmp_path)
    second = initialize_plan(tmp_path)

    native = root_planning / "quality-runner"
    assert first["status"] == "initialized"
    assert second["created"] == []
    assert (native / "config.json").exists()
    assert (native / "ROADMAP.md").exists()
    assert (native / "STATE.md").exists()
    assert (native / "phases").is_dir()
    assert roadmap.read_text(encoding="utf-8") == "existing gsd roadmap\n"
    assert state.read_text(encoding="utf-8") == "existing gsd state\n"


def test_phase_add_and_plan_use_deterministic_files_and_preserve_existing_plan(
    tmp_path: Path,
) -> None:
    initialize_plan(tmp_path)
    phase = add_phase(tmp_path, "Capability baseline")
    slices = [
        _slice("cluster-high", priority="high", fingerprint="fp-resolved"),
        _slice(
            "cluster-low",
            priority="low",
            fingerprint="fp-persisted",
            depends_on=["cluster-high"],
        ),
    ]
    _write_run(tmp_path, "run-plan", slices)

    planned = plan_phase(tmp_path, phase_number=phase["phase"]["number"], run_id="run-plan")
    phase_dir = tmp_path / ".planning" / "quality-runner" / "phases" / "01-capability-baseline"
    first_plan = phase_dir / "01-01-PLAN.md"
    original = first_plan.read_text(encoding="utf-8")
    first_plan.write_text(original + "\nHuman context.\n", encoding="utf-8")
    second = plan_phase(tmp_path, phase_number=1, run_id="run-plan")

    assert planned["status"] == "planned"
    assert [item["id"] for item in planned["plans"]] == ["01-01", "01-02"]
    assert planned["plans"][0]["wave"] == 1
    assert planned["plans"][1]["wave"] == 3
    assert planned["plans"][1]["depends_on"] == ["01-01"]
    assert second["status"] == "already-planned"
    assert "Human context." in first_plan.read_text(encoding="utf-8")


def test_phase_plan_accepts_handoff_json(tmp_path: Path) -> None:
    initialize_plan(tmp_path)
    phase = add_phase(tmp_path, "Handoff planning")
    plan_path = _write_run(
        tmp_path, "run-handoff", [_slice("cluster", priority="medium", fingerprint="fp")]
    )

    planned = plan_phase(
        tmp_path,
        phase_number=phase["phase"]["number"],
        handoff_json=plan_path.parent / "agent-handoff.json",
    )

    assert planned["source"]["remediation_plan_json"] == str(plan_path)
    assert planned["plans"][0]["source"]["handoff_json"].endswith("agent-handoff.json")


def test_auto_plan_creates_security_first_domain_phases_and_is_idempotent(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / ".quality-runner" / "runs" / "domain-run"
    run_dir.mkdir(parents=True)
    plan_path = run_dir / "remediation-plan.json"
    candidates = [
        {
            "id": "phase-ui-quality",
            "domain": "ui-quality",
            "title": "UI quality",
            "priority": "low",
            "slice_ids": ["leaf-ui"],
            "finding_ids": ["finding-ui"],
            "finding_fingerprints": ["fingerprint-ui"],
            "actions": ["Review the UI leaf."],
            "verification_gates": ["Run the UI check."],
            "stop_conditions": ["Stop if the UI scope changes."],
        },
        {
            "id": "phase-security",
            "domain": "security",
            "title": "Security and trust boundaries",
            "priority": "medium",
            "slice_ids": ["leaf-security"],
            "finding_ids": ["finding-security"],
            "finding_fingerprints": ["fingerprint-security"],
            "actions": ["Review the security leaf."],
            "verification_gates": ["Run the security check."],
            "stop_conditions": ["Stop if the security scope changes."],
        },
    ]
    plan_path.write_text(
        json.dumps(
            {
                "schema": "quality-runner-remediation-plan-v0.1",
                "run_id": "domain-run",
                "phase_candidates": candidates,
                "slices": [],
            }
        ),
        encoding="utf-8",
    )

    first = auto_plan(tmp_path, run_id="domain-run")
    second = auto_plan(tmp_path, run_id="domain-run")

    assert first["status"] == "auto-planned"
    assert first["ordering"] == "security-first"
    assert [item["candidate_id"] for item in first["phases"]] == [
        "phase-security",
        "phase-ui-quality",
    ]
    assert [item["number"] for item in first["phases"]] == [1, 2]
    assert [item["status"] for item in second["phases"]] == [
        "already-planned",
        "already-planned",
    ]
    security_plan = tmp_path / (
        ".planning/quality-runner/phases/01-security-and-trust-boundaries/01-01-PLAN.md"
    )
    assert security_plan.exists()
    security_plan_text = security_plan.read_text(encoding="utf-8")
    assert '"source_slice_ids"' in security_plan_text
    assert '"leaf-security"' in security_plan_text


def test_next_record_update_verify_and_close_follow_phase_lifecycle(tmp_path: Path) -> None:
    initialize_plan(tmp_path)
    add_phase(tmp_path, "Lifecycle")
    _write_run(
        tmp_path,
        "run-plan",
        [
            _slice("resolved", priority="high", fingerprint="fp-resolved"),
            _slice("persisted", priority="medium", fingerprint="fp-persisted"),
        ],
    )
    plan_phase(tmp_path, phase_number=1, run_id="run-plan")

    ready = next_plan(tmp_path)
    assert ready["status"] == "ready"
    assert ready["plan"]["id"] == "01-01"

    _write_run(tmp_path, "run-final", [])
    _write_delta(tmp_path, "run-final")
    updated = update_phase(
        tmp_path,
        phase_number=1,
        baseline_run_id="run-plan",
        run_id="run-final",
    )
    assert updated["plans"][0]["status"] == "verified"
    assert updated["plans"][1]["status"] == "in_progress"
    assert plan_status(tmp_path)["phases"][0]["plan_count"] == 2

    failed = verify_phase(tmp_path, phase_number=1, run_id="run-final")
    assert failed["status"] == "failed"
    assert failed["unresolved_plan_ids"] == ["01-02"]

    result_path = tmp_path / "batch-result.json"
    _batch_result(result_path)
    recorded = record_batch(tmp_path, phase_number=1, plan_number=2, result_file=result_path)
    assert recorded["plan"]["status"] == "complete"
    assert (tmp_path / ".planning/quality-runner/phases/01-lifecycle/01-02-SUMMARY.md").exists()

    passed = verify_phase(tmp_path, phase_number=1, run_id="run-final")
    assert passed["status"] == "passed"
    closed = close_phase(tmp_path, phase_number=1, run_id="run-final")
    assert closed["status"] == "closed"


def test_invalid_batch_result_does_not_modify_plan(tmp_path: Path) -> None:
    initialize_plan(tmp_path)
    add_phase(tmp_path, "Validation")
    _write_run(tmp_path, "run-plan", [_slice("cluster", priority="high", fingerprint="fp")])
    plan_phase(tmp_path, phase_number=1, run_id="run-plan")
    plan_path = tmp_path / ".planning/quality-runner/phases/01-validation/01-01-PLAN.md"
    before = plan_path.read_text(encoding="utf-8")
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"status": "complete"}), encoding="utf-8")

    with pytest.raises(ValueError, match="missing fields"):
        record_batch(tmp_path, phase_number=1, plan_number=1, result_file=invalid)

    assert plan_path.read_text(encoding="utf-8") == before


def test_blocked_delta_marks_required_plans_blocked_and_verification_failed(tmp_path: Path) -> None:
    initialize_plan(tmp_path)
    add_phase(tmp_path, "Blocked evidence")
    _write_run(tmp_path, "run-plan", [_slice("cluster", priority="high", fingerprint="fp")])
    plan_phase(tmp_path, phase_number=1, run_id="run-plan")
    _write_run(tmp_path, "run-blocked", [])
    (tmp_path / ".quality-runner/runs/run-blocked/remediation-delta.json").write_text(
        json.dumps(
            {
                "schema": "quality-runner-remediation-delta-v0.1",
                "findings": {"new": [], "persisted": [{"fingerprint": "fp"}], "resolved": []},
                "verification": {"current": {"status": "blocked", "blockers": ["missing deps"]}},
            }
        ),
        encoding="utf-8",
    )

    updated = update_phase(
        tmp_path,
        phase_number=1,
        baseline_run_id="run-plan",
        run_id="run-blocked",
    )
    verification = verify_phase(tmp_path, phase_number=1, run_id="run-blocked")

    assert updated["status"] == "blocked"
    assert updated["plans"][0]["status"] == "blocked"
    assert verification["status"] == "failed"
    assert "remediation-delta-verification" in verification["failed_checks"]


def test_native_plan_cli_surface_emits_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["plan", "init", str(tmp_path), "--json"]) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["status"] == "initialized"

    run_dir = tmp_path / ".quality-runner" / "runs" / "cli-domain-run"
    run_dir.mkdir(parents=True)
    (run_dir / "remediation-plan.json").write_text(
        json.dumps(
            {
                "phase_candidates": [
                    {
                        "id": "phase-security",
                        "domain": "security",
                        "title": "Security",
                        "priority": "high",
                        "slice_ids": [],
                        "finding_ids": [],
                        "finding_fingerprints": [],
                        "actions": ["Review security."],
                        "verification_gates": ["Run security checks."],
                        "stop_conditions": ["Stop on scope drift."],
                    }
                ],
                "slices": [],
            }
        ),
        encoding="utf-8",
    )
    assert main(["plan", "auto", str(tmp_path), "--run-id", "cli-domain-run", "--json"]) == 0
    auto_payload = json.loads(capsys.readouterr().out)
    assert auto_payload["status"] == "auto-planned"
    assert auto_payload["ordering"] == "security-first"

    assert main(["plan", "status", str(tmp_path), "--json"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["status"] == "ready"
