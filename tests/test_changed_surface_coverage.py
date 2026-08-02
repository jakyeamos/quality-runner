from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from quality_runner import (
    cli_payload,
    code_quality_architecture,
    code_quality_bundles,
    fleet_documents,
    gate_execution_policy,
    gate_verification,
    performance,
    phase_planning,
    read_only_git,
    repo_hygiene_package,
    review_execution_artifacts,
)
from quality_runner.application import audit_v1_artifacts, journey_outcomes
from quality_runner.schema_constants import PERFORMANCE_SCHEMA, REVIEW_EXECUTION_SCHEMA
from quality_runner.fleet.legibility import _maintained_legibility_control


def test_changed_surface_helpers_cover_projection_and_policy_branches(
    tmp_path: Path, monkeypatch
) -> None:
    assert audit_v1_artifacts._intent_docs({"intent_docs": [{"id": "doc"}]}) == [{"id": "doc"}]

    gate_path = tmp_path / "gate-verification.json"
    gate_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    monkeypatch.setattr(journey_outcomes, "artifact_text_file", lambda *args: gate_path)
    assert journey_outcomes._gate_verification(tmp_path, {"run_id": "run"}) == {"status": "passed"}

    monkeypatch.setattr(cli_payload, "_validated_repo_path", lambda value: tmp_path)
    monkeypatch.setattr(cli_payload, "review_command_payload", lambda *args, **kwargs: {"run": "r"})
    monkeypatch.setattr(cli_payload, "review_journey_outcome", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(cli_payload, "_result_payload", lambda value: {"wrapped": value})
    args = SimpleNamespace(command="review", repo_path=str(tmp_path), legacy_output=False)
    assert cli_payload.payload_for_args(args) == {"wrapped": {"ok": True}}


def test_changed_surface_helpers_cover_quality_and_gate_branches(tmp_path: Path) -> None:
    scanned = [{"path": "src/a.ts", "lines": ["import x from 'internal'", "secret = 1"]}]
    import_rule = {
        "id": "boundary",
        "sources": ["src/**"],
        "disallowed_imports": ["internal"],
        "allowed_imports": [],
    }
    assert code_quality_architecture._import_boundary_findings(scanned, import_rule)
    pattern_rule = {
        "id": "pattern",
        "paths": ["src/**"],
        "disallowed_patterns": ["secret"],
    }
    assert code_quality_architecture._pattern_boundary_findings(scanned, pattern_rule)

    bundle = tmp_path / "dist/assets/app.js"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(os.urandom(300_000))
    assert code_quality_bundles.bundle_budget_findings(tmp_path)

    assert fleet_documents._missing_capabilities({"missing": [{"id": "pytest"}]}, {}) == ["pytest"]
    assert gate_execution_policy._available_capabilities(
        {"available": [{"id": "pytest", "capability_kind": "command"}]}
    )
    updated = gate_verification.apply_gate_verification(
        {"available": [{"id": "pytest", "capability_kind": "command"}]},
        {"gates": [{"id": "pytest", "status": "passed"}]},
    )
    assert updated["available"][0]["verification_state"]["result"] == "passed"
    assert performance.performance_from_payload({"schema": PERFORMANCE_SCHEMA}) == {
        "schema": PERFORMANCE_SCHEMA
    }


def test_changed_surface_helpers_cover_state_and_artifact_validation(
    tmp_path: Path, monkeypatch
) -> None:
    plan_path = tmp_path / "plan.json"
    plan = {"path": str(plan_path), "finding_fingerprints": []}
    monkeypatch.setattr(phase_planning, "load_phase_plans", lambda *args: [plan])
    monkeypatch.setattr(
        phase_planning,
        "load_or_build_delta",
        lambda *args, **kwargs: {
            "findings": {"resolved": [], "persisted": [], "new": []},
            "verification": {"current": {}},
        },
    )
    monkeypatch.setattr(phase_planning, "update_plan_file", lambda *args: None)
    monkeypatch.setattr(
        phase_planning, "load_state", lambda *args: {"unplanned_findings": [{"id": "old"}]}
    )
    monkeypatch.setattr(phase_planning, "save_state", lambda *args: None)
    monkeypatch.setattr(phase_planning, "update_phase_tracking", lambda *args: None)
    assert (
        phase_planning.update_phase(tmp_path, phase_number=1, baseline_run_id="b", run_id="r")[
            "status"
        ]
        == "updated"
    )

    snapshots = [
        read_only_git.TrackedSnapshot(True, "after", ("a",)),
        read_only_git.TrackedSnapshot(True, "before", ("a",)),
    ]
    monkeypatch.setattr(read_only_git, "tracked_snapshot", lambda *args, **kwargs: snapshots.pop(0))
    monkeypatch.setattr(read_only_git, "_restore_snapshot", lambda **kwargs: None)
    before = read_only_git.TrackedSnapshot(True, "before", ("a",))
    assert read_only_git.restore_if_changed(tmp_path, before)

    package = tmp_path / "packages/app/package.json"
    package.parent.mkdir(parents=True)
    package.write_text(json.dumps({"packageManager": "pnpm@10.0.0"}), encoding="utf-8")
    assert (
        repo_hygiene_package._nested_package_root_state(tmp_path, package)["package_manager"]
        == "pnpm@10.0.0"
    )

    context = {"run_id": "run", "mode": "review", "input_hashes": {"input": "hash"}}
    payload = {
        "schema": REVIEW_EXECUTION_SCHEMA,
        "state": "packet-ready",
        "run_id": "run",
        "mode": "review",
        "input_hashes": {"input": "hash"},
    }
    review_execution_artifacts._validate_prepared_execution(payload, context)


def test_changed_surface_legibility_contract_is_maintained() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = _maintained_legibility_control(
        root=root,
        dimension="architecture_boundaries",
        as_of="2026-08-02T05:00:00+00:00",
    )

    assert evidence is not None
    assert any(item["path"] == "environment-legibility.json" for item in evidence)
