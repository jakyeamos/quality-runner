from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from quality_runner.behavior_receipts import record_edge_trace, verify_behavior_command
from quality_runner.fleet.behavior_assurance import assess_behavior_assurance
from quality_runner.fleet.contracts import digest

AS_OF = "2026-08-13T16:00:00+00:00"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _init(root: Path) -> None:
    root.mkdir()
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "qr-tests@example.com")
    _git(root, "config", "user.name", "Quality Runner Tests")
    (root / "src").mkdir()
    (root / "src/app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")


def _contract(
    *, applicability: str = "applicable", schema: str = "pronto-behavior-assurance/v1"
) -> dict[str, Any]:
    if applicability == "not_applicable":
        return {
            "schema": schema,
            "applicability": "not_applicable",
            "reason": "This repository contains static reference data only.",
        }
    behavior: dict[str, Any] = {
        "id": "save-state",
        "title": "Save state",
        "tier": 0,
        "automation": "on_demand",
        "change_triggers": ["src/**"],
        "scenarios": [
            {
                "id": "persists",
                "title": "State persists",
                "oracle": "Reload shows the saved value.",
                "verification_level": "automated",
            }
        ],
    }
    if schema == "pronto-behavior-assurance/v2":
        behavior["invariants"] = ["A successful save remains visible after reload."]
        behavior["scenarios"][0]["edge_profile"] = {
            "categories": ["state_and_ordering"],
            "risk": "routine",
            "side_effects": "reversible",
        }
    return {
        "schema": schema,
        "applicability": "applicable",
        "approved_producers": ["quality-runner"],
        "behaviors": [behavior],
    }


def _trace(
    *,
    status: str = "passed",
    sensitivity: str = "normal",
) -> dict[str, Any]:
    failed = status == "failed"
    return {
        "schema": "quality-runner-edge-trace/v1",
        "seed": 42,
        "categories": ["state_and_ordering"],
        "invariant": "A successful save remains visible after reload.",
        "environment": "local",
        "surface": "cli",
        "sensitivity": sensitivity,
        "classification": "confirmed" if failed else "passed",
        "determinism": "deterministic",
        "preconditions": ["Fresh local fixture."],
        "steps": [
            {"action": "save alpha", "observation": "accepted"},
            {"action": "reload", "observation": "alpha visible"},
        ],
        "replay_results": (
            [{"attempt": 1, "status": "reproduced", "observation": "same invariant failure"}]
            if failed
            else []
        ),
        "minimization": {
            "status": "complete" if failed else "not_needed",
            "original_step_count": 2,
            "minimized_step_count": 2,
        },
        "cleanup": {"status": "complete", "observation": "fixture removed"},
        "artifacts": [{"kind": "transcript", "sha256": "a" * 64}],
        "observation": "The declared state invariant held." if not failed else "State disappeared.",
    }


def _write_trace(root: Path, trace: dict[str, Any]) -> Path:
    path = root / "edge-trace.json"
    path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    return path


def _write_contract(root: Path, contract: dict[str, Any]) -> str:
    path = root / ".pronto/behavior-assurance.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    _git(root, "add", path.relative_to(root).as_posix())
    _git(root, "commit", "-m", "add behavior contract")
    return _git(root, "rev-parse", "HEAD")


def _write_receipt(
    root: Path,
    contract: dict[str, Any],
    commit: str,
    *,
    status: str = "passed",
) -> Path:
    unsigned: dict[str, Any] = {
        "schema": "quality-runner-behavior-receipt/v1",
        "contract_digest": digest(contract),
        "producer": {"id": "quality-runner", "version": "1.0.0"},
        "generated_at": "2026-08-13T15:00:00+00:00",
        "target": {"branch": "dev", "commit": commit},
        "results": [
            {
                "behavior_id": "save-state",
                "scenario_id": "persists",
                "status": status,
                "verification_level": "automated",
                "evidence": (
                    [
                        {
                            "kind": "bounded_command",
                            "argv": ["pytest", "-q"],
                            "exit_code": 0,
                            "stdout_sha256": "0" * 64,
                            "stderr_sha256": "0" * 64,
                        }
                    ]
                    if status == "passed"
                    else []
                ),
                "defect": {"state": "clear"},
            }
        ],
    }
    receipt_id = f"receipt-{digest(unsigned)[:24]}"
    receipt = {"receipt_id": receipt_id, **unsigned}
    directory = root / ".quality-runner/behavior-assurance/receipts"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{receipt_id}.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return path


def _repository(root: Path) -> dict[str, Any]:
    return {
        "repo_id": "repo-fixture",
        "primary_path": str(root),
        "target_branch": {
            "branch": "dev",
            "status": "ready",
            "head": _git(root, "rev-parse", "HEAD"),
        },
    }


def test_missing_contract_is_visible_and_never_green(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["contract_status"] == "missing"
    assert result["state"] == "missing_contract"
    assert result["release_ready"] is False
    assert result["gaps"][0]["kind"] == "contract_missing"


def test_exact_commit_receipt_verifies_tier_zero_behavior(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    commit = _write_contract(root, contract)
    _write_receipt(root, contract, commit)

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["release_ready"] is True
    assert result["state"] == "current"
    assert result["result_status"] == "passed"
    assert result["freshness"] == "current"
    assert result["verified"][0]["carried_forward"] is False


def test_receipt_carries_forward_only_across_unrelated_changes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract()
    receipt_commit = _write_contract(root, contract)
    _write_receipt(root, contract, receipt_commit)
    (root / "README.md").write_text("Unrelated docs.\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "docs")

    carried = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert carried["release_ready"] is True
    assert carried["verified"][0]["carried_forward"] is True

    (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(root, "add", "src/app.py")
    _git(root, "commit", "-m", "change behavior")

    stale = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert stale["release_ready"] is False
    assert stale["freshness"] == "stale"
    assert any(gap["kind"] == "receipt_stale" for gap in stale["gaps"])


def test_malformed_receipt_blocks_a_trust_claim(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract()
    _write_contract(root, contract)
    directory = root / ".quality-runner/behavior-assurance/receipts"
    directory.mkdir(parents=True)
    (directory / "claimed.json").write_text('{"schema":"wrong"}\n', encoding="utf-8")

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["release_ready"] is False
    assert result["result_status"] == "blocked"
    assert any(gap["kind"] == "receipt_invalid" for gap in result["gaps"])


def test_quality_runner_label_without_producer_evidence_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract()
    commit = _write_contract(root, contract)
    original = _write_receipt(root, contract, commit)
    receipt = json.loads(original.read_text(encoding="utf-8"))
    receipt["results"][0]["evidence"] = [{"kind": "command", "reference": "pytest -q"}]
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_id"}
    receipt["receipt_id"] = f"receipt-{digest(unsigned)[:24]}"
    replacement = original.with_name(f"{receipt['receipt_id']}.json")
    original.unlink()
    replacement.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["release_ready"] is False
    assert any("bounded command evidence" in gap["message"] for gap in result["gaps"])


def test_failed_receipt_remains_failed_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract()
    commit = _write_contract(root, contract)
    _write_receipt(root, contract, commit, status="failed")

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["release_ready"] is False
    assert result["result_status"] == "failed"
    assert any(gap["kind"] == "result_failed" for gap in result["gaps"])


def test_bounded_not_applicable_contract_is_explicit(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(applicability="not_applicable")
    _write_contract(root, contract)

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["applicability"] == "not_applicable"
    assert result["state"] == "not_applicable"
    assert result["release_ready"] is True
    assert result["score"] is None


def test_bounded_validator_produces_a_canonical_receipt(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    _write_contract(root, _contract())

    produced = verify_behavior_command(
        repo_root=root,
        behavior_id="save-state",
        scenario_ids=["persists"],
        command=[sys.executable, "-c", "print('validated')"],
        timeout_seconds=10,
    )
    assessed = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert produced["status"] == "passed"
    assert produced["receipt_path"].endswith(f"{produced['receipt_id']}.json")
    assert assessed["release_ready"] is True
    assert assessed["verified"][0]["receipt_id"] == produced["receipt_id"]


def test_receipt_producer_refuses_dirty_trigger_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    _write_contract(root, _contract())
    (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="commit the behavior's changed trigger paths"):
        verify_behavior_command(
            repo_root=root,
            behavior_id="save-state",
            scenario_ids=[],
            command=[sys.executable, "-c", "raise SystemExit(0)"],
            timeout_seconds=10,
        )


def test_failing_validator_records_failed_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    _write_contract(root, _contract())

    produced = verify_behavior_command(
        repo_root=root,
        behavior_id="save-state",
        scenario_ids=[],
        command=[sys.executable, "-c", "raise SystemExit(9)"],
        timeout_seconds=10,
    )
    assessed = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert produced["status"] == "failed"
    assert produced["exit_code"] == 9
    assert assessed["release_ready"] is False
    assert assessed["result_status"] == "failed"


def test_command_receipt_cannot_claim_direct_surface_proof(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract()
    contract["behaviors"][0]["scenarios"][0]["verification_level"] = "direct_surface"
    _write_contract(root, contract)

    with pytest.raises(ValueError, match="cannot satisfy direct_surface"):
        verify_behavior_command(
            repo_root=root,
            behavior_id="save-state",
            scenario_ids=[],
            command=[sys.executable, "-c", "raise SystemExit(0)"],
            timeout_seconds=10,
        )


def test_v1_contract_remains_valid_but_edge_unprofiled(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract()
    commit = _write_contract(root, contract)
    _write_receipt(root, contract, commit)

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["release_ready"] is True
    assert result["contract_schema"] == "pronto-behavior-assurance/v1"
    assert result["state"] == "legacy_v1"
    assert result["edge_profile_status"] == "legacy"
    assert result["coverage"]["profiled"] == 0


def test_v2_requires_invariants_and_valid_edge_profiles(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    contract["behaviors"][0]["invariants"] = []
    contract["behaviors"][0]["scenarios"][0]["edge_profile"]["categories"] = ["surprise"]
    _write_contract(root, contract)

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["contract_status"] == "invalid"
    messages = [gap["message"] for gap in result["gaps"]]
    assert any("invariants" in message for message in messages)
    assert any("canonical categories" in message for message in messages)


def test_v2_unprofiled_contract_is_distinct_from_unknown_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    del contract["behaviors"][0]["scenarios"][0]["edge_profile"]
    _write_contract(root, contract)

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["contract_status"] == "current"
    assert result["edge_profile_status"] == "unprofiled"
    assert result["state"] == "unprofiled"
    assert result["result_status"] == "unknown"


def test_partial_tier_zero_verification_is_distinct_from_unknown(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    second = json.loads(json.dumps(contract["behaviors"][0]["scenarios"][0]))
    second["id"] = "persists-again"
    contract["behaviors"][0]["scenarios"].append(second)
    commit = _write_contract(root, contract)
    _write_receipt(root, contract, commit)

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["state"] == "partially_verified"
    assert result["result_status"] == "unknown"
    assert result["passed_scenario_count"] == 1


def test_all_tiers_project_without_changing_tier_zero_release_semantics(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    secondary = json.loads(json.dumps(contract["behaviors"][0]))
    secondary["id"] = "export-state"
    secondary["title"] = "Export state"
    secondary["tier"] = 2
    secondary["scenarios"][0]["id"] = "exports"
    secondary["scenarios"][0]["title"] = "State exports"
    contract["behaviors"].append(secondary)
    commit = _write_contract(root, contract)
    _write_receipt(root, contract, commit)

    result = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert result["release_ready"] is True
    assert result["required_scenario_count"] == 1
    assert result["coverage"]["total"] == 2
    assert result["coverage"]["verified"] == 1
    assert result["coverage"]["unknown"] == 1
    assert result["coverage"]["per_tier"]["2"]["unknown"] == 1


def test_record_edge_mints_only_direct_surface_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    contract["behaviors"][0]["scenarios"][0]["verification_level"] = "direct_surface"
    _write_contract(root, contract)
    trace_path = _write_trace(root, _trace())

    produced = record_edge_trace(
        repo_root=root,
        behavior_id="save-state",
        scenario_id="persists",
        environment="local",
        surface="cli",
        status="passed",
        trace_path=trace_path,
    )
    receipt = json.loads((root / produced["receipt_path"]).read_text(encoding="utf-8"))
    assessed = assess_behavior_assurance(root, _repository(root), AS_OF)

    assert receipt["results"][0]["verification_level"] == "direct_surface"
    assert assessed["release_ready"] is True
    assert assessed["coverage"]["verified"] == 1


def test_record_edge_rejects_unknown_or_destructive_or_independent_claims(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    _write_contract(root, contract)
    trace_path = _write_trace(root, _trace())

    with pytest.raises(ValueError, match="allowed only"):
        record_edge_trace(
            repo_root=root,
            behavior_id="save-state",
            scenario_id="persists",
            environment="production",
            surface="cli",
            status="passed",
            trace_path=trace_path,
        )

    contract = _contract(schema="pronto-behavior-assurance/v2")
    contract["behaviors"][0]["scenarios"][0]["edge_profile"]["side_effects"] = "destructive"
    _write_contract(root, contract)
    with pytest.raises(ValueError, match="separately authorized"):
        record_edge_trace(
            repo_root=root,
            behavior_id="save-state",
            scenario_id="persists",
            environment="local",
            surface="cli",
            status="passed",
            trace_path=trace_path,
        )

    contract = _contract(schema="pronto-behavior-assurance/v2")
    contract["behaviors"][0]["scenarios"][0]["verification_level"] = "independent"
    _write_contract(root, contract)
    with pytest.raises(ValueError, match="cannot satisfy independent"):
        record_edge_trace(
            repo_root=root,
            behavior_id="save-state",
            scenario_id="persists",
            environment="local",
            surface="cli",
            status="passed",
            trace_path=trace_path,
        )


def test_sensitive_trace_is_private_and_repository_receipt_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    contract["behaviors"][0]["scenarios"][0]["verification_level"] = "direct_surface"
    _write_contract(root, contract)
    trace = _trace(sensitivity="security_sensitive")
    trace["steps"][0]["action"] = "submit password=hunter2"
    trace_path = _write_trace(root, trace)
    private_root = tmp_path / "private"
    monkeypatch.setenv("QUALITY_RUNNER_PRIVATE_EVIDENCE_ROOT", str(private_root))

    produced = record_edge_trace(
        repo_root=root,
        behavior_id="save-state",
        scenario_id="persists",
        environment="local",
        surface="cli",
        status="passed",
        trace_path=trace_path,
    )
    receipt_text = (root / produced["receipt_path"]).read_text(encoding="utf-8")
    private_text = next(private_root.rglob("*.json")).read_text(encoding="utf-8")

    assert "hunter2" not in receipt_text
    assert "hunter2" in private_text
    assert produced["private_trace_id"].startswith("edge-trace-")


def test_failed_edge_trace_requires_replay_and_complete_minimization(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _init(root)
    contract = _contract(schema="pronto-behavior-assurance/v2")
    _write_contract(root, contract)
    trace = _trace(status="failed")
    trace["replay_results"] = []
    trace["minimization"]["status"] = "partial"
    trace_path = _write_trace(root, trace)

    with pytest.raises(ValueError, match="must reproduce once"):
        record_edge_trace(
            repo_root=root,
            behavior_id="save-state",
            scenario_id="persists",
            environment="local",
            surface="cli",
            status="failed",
            trace_path=trace_path,
        )
