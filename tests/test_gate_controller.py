from __future__ import annotations

import json
from pathlib import Path

import pytest

from quality_runner.gate_controller import (
    create_gate_run,
    gate_status_payload,
    load_gate_responses,
    record_gate_response,
)
from quality_runner.workflow import run_payload, verify_gates_payload


def _minimal_repo(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )


def test_create_gate_run_from_run_artifacts(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    run_payload(repo_root=tmp_path, run_id="gate-source")

    payload = create_gate_run(repo_root=tmp_path, run_id="gate-source", gate_run_id="gate-test-001")
    gate_run = payload["gate_run"]

    assert payload["schema"] == "quality-runner-gate-run-result-v0.1"
    assert gate_run["gate_run_id"] == "gate-test-001"
    assert gate_run["run_id"] == "gate-source"
    assert gate_run["phase"] == "post-run"
    assert gate_run["implementation_allowed"] is False
    assert gate_run["status"] in {"awaiting-response", "ready-to-proceed"}
    assert (tmp_path / ".quality-runner" / "gate-runs" / "gate-test-001" / "gate-run.json").exists()


def test_create_gate_run_post_verify_phase(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    run_payload(repo_root=tmp_path, run_id="verify-source")
    verify_gates_payload(repo_root=tmp_path, run_id="verify-source", read_only_gates=True)

    payload = create_gate_run(repo_root=tmp_path, run_id="verify-source")
    assert payload["gate_run"]["phase"] == "post-verify"


def test_create_gate_run_requires_handoff(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    run_dir = tmp_path / ".quality-runner" / "runs" / "missing-handoff"
    run_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="agent handoff"):
        create_gate_run(repo_root=tmp_path, run_id="missing-handoff")


def test_gate_status_and_respond_append_history(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    run_payload(repo_root=tmp_path, run_id="respond-source")
    created = create_gate_run(
        repo_root=tmp_path, run_id="respond-source", gate_run_id="gate-respond-001"
    )
    gate_run_id = created["gate_run"]["gate_run_id"]

    status = gate_status_payload(repo_root=tmp_path, gate_run_id=gate_run_id)
    assert status["schema"] == "quality-runner-gate-status-result-v0.1"
    assert status["responses"] == []

    responded = record_gate_response(
        repo_root=tmp_path,
        gate_run_id=gate_run_id,
        action="route-next-slice",
        actor="controller-agent",
        finding_ids=["missing-tests"],
        notes="Run dependency setup before re-verify.",
    )
    assert responded["response"]["action"] == "route-next-slice"
    assert responded["gate_run"]["last_response_at"] is not None
    assert responded["gate_run"]["status"] == "awaiting-response"

    responses = load_gate_responses(repo_root=tmp_path, gate_run_id=gate_run_id)
    assert len(responses) == 1
    assert responses[0]["finding_ids"] == ["missing-tests"]

    approved = record_gate_response(
        repo_root=tmp_path,
        gate_run_id=gate_run_id,
        action="approve",
        actor="user",
    )
    assert approved["gate_run"]["status"] == "completed"

    with pytest.raises(ValueError, match="terminal"):
        record_gate_response(
            repo_root=tmp_path,
            gate_run_id=gate_run_id,
            action="abort",
        )


def test_create_gate_run_rejects_second_active_run_for_same_run_id(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    run_payload(repo_root=tmp_path, run_id="duplicate-gate")

    create_gate_run(repo_root=tmp_path, run_id="duplicate-gate", gate_run_id="gate-active-001")
    with pytest.raises(ValueError, match="active gate run already exists"):
        create_gate_run(repo_root=tmp_path, run_id="duplicate-gate", gate_run_id="gate-active-002")


def test_record_disposition_updates_resolution_ledger(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    run_payload(repo_root=tmp_path, run_id="disposition-source")
    created = create_gate_run(
        repo_root=tmp_path,
        run_id="disposition-source",
        gate_run_id="gate-disposition-001",
    )

    record_gate_response(
        repo_root=tmp_path,
        gate_run_id=created["gate_run"]["gate_run_id"],
        action="record-disposition",
        finding_ids=["missing-tests"],
        notes="Adopt tests in next milestone.",
        disposition="accepted-intentional",
        owner="maintainer",
    )

    ledger_path = (
        tmp_path / ".quality-runner" / "runs" / "disposition-source" / "resolution-ledger.json"
    )
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    dispositions = ledger.get("finding_dispositions")
    assert isinstance(dispositions, list)
    assert dispositions[0]["finding_id"] == "missing-tests"
    assert dispositions[0]["status"] == "accepted-intentional"
    assert dispositions[0]["owner"] == "maintainer"


def test_create_gate_run_attaches_intent_when_missing(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    run_payload(repo_root=tmp_path, run_id="intent-source")

    payload = create_gate_run(
        repo_root=tmp_path,
        run_id="intent-source",
        gate_run_id="gate-intent-001",
        goal="Ship gate controller",
    )
    gate_run = payload["gate_run"]
    assert isinstance(gate_run.get("intent_ref"), str)
    intent_path = tmp_path / gate_run["intent_ref"]
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    assert intent["goal"] == "Ship gate controller"
    assert intent["source"] == "gate"
