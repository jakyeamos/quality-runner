from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.contracts import digest
from quality_runner.gate_verification import verification_status
from quality_runner.invariants import (
    apply_invariant_status,
    build_invariant_report,
)
from quality_runner.workflow import verify_gates_payload


def test_configured_invariant_is_discovered_with_an_arbitrary_stable_id(
    tmp_path: Path,
) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.config import load_repo_config
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "queue-ui.mjs").write_text("export const queue = [];\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/queue-ui.test.mjs").write_text("// proof\n", encoding="utf-8")
    _write_config(tmp_path, enforcement="required")

    config = load_repo_config(tmp_path)
    scan = inspect_repo(tmp_path, run_id="invariant-discovery")
    packet = compile_standards(
        repo_root=tmp_path,
        scan=scan,
        profile="default",
        config=config,
    )
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)
    invariant = next(
        item
        for item in _objects(capability_map["available"])
        if item["id"] == "human-only-review-not-reusable"
    )

    assert config["invariants"] == [
        {
            "id": "human-only-review-not-reusable",
            "description": "Handoff-only prompts never enter the reusable answer queue.",
            "owner": "application-review-classifier",
            "surfaces": ["queue-ui.mjs", "tests/queue-ui.test.mjs"],
            "command": f'{sys.executable} -c "raise SystemExit(0)"',
            "enforcement": "required",
            "ecosystem": "javascript",
            "mutating_risk": "safe",
            "freshness_days": 30,
        }
    ]
    assert invariant["capability_kind"] == "semantic_invariant"
    assert invariant["enforcement"] == "required"
    assert invariant["required_by"] == "repository-invariant"


def test_required_invariant_with_missing_proof_surface_is_reported_missing(
    tmp_path: Path,
) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    _write_config(tmp_path, enforcement="required")
    scan = inspect_repo(tmp_path, run_id="invariant-missing-proof")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)
    missing = {item["id"]: item for item in _objects(capability_map["missing"])}

    assert missing["human-only-review-not-reusable"]["type"] == "invariant"
    assert "queue-ui.mjs" in str(missing["human-only-review-not-reusable"]["reason"])


def test_invalid_and_duplicate_invariants_fail_closed_with_config_warnings(
    tmp_path: Path,
) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "",
                "[[quality_runner.invariants]]",
                'id = "valid-invariant"',
                'description = "A valid invariant."',
                'owner = "quality"',
                'surfaces = ["tests/proof.test"]',
                'command = "run proof"',
                "",
                "[[quality_runner.invariants]]",
                'id = "valid-invariant"',
                'description = "Duplicate invariant."',
                'owner = "quality"',
                'surfaces = ["tests/other.test"]',
                'command = "run other proof"',
                "",
                "[[quality_runner.invariants]]",
                'id = "Invalid ID"',
                'description = "Unsafe invariant."',
                'owner = "quality"',
                'surfaces = ["../outside"]',
                'command = "run unsafe proof"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert [item["id"] for item in _objects(config["invariants"])] == ["valid-invariant"]
    warning_messages = [str(item["message"]) for item in _objects(config["warnings"])]
    assert any("duplicates 'valid-invariant'" in message for message in warning_messages)
    assert any("kebab-case id" in message for message in warning_messages)


def test_invariant_report_distinguishes_pass_fail_block_unknown_and_stale(
    tmp_path: Path,
) -> None:
    surface = tmp_path / "surface.txt"
    surface.write_text("proof surface\n", encoding="utf-8")
    base = {
        "id": "durable-behavior",
        "description": "Behavior stays durable.",
        "owner": "quality",
        "surfaces": ["surface.txt"],
        "command": "check behavior",
        "enforcement": "required",
        "ecosystem": "repository",
        "mutating_risk": "safe",
        "freshness_days": 7,
    }
    config = {"invariants": [base]}
    now = datetime(2026, 7, 29, tzinfo=UTC)

    assert _status(tmp_path, config, {"status": "passed"}, now) == "passed"
    assert (
        _status(
            tmp_path,
            config,
            {"status": "failed", "failure_type": "command-failed"},
            now,
        )
        == "failed"
    )
    assert (
        _status(
            tmp_path,
            config,
            {"status": "failed", "failure_type": "environment-restricted"},
            now,
        )
        == "blocked"
    )
    assert _status(tmp_path, config, None, now) == "unknown"

    evidence = tmp_path / "invariant-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "quality-runner-invariant-evidence-v0.1",
                "id": "durable-behavior",
                "status": "passed",
                "checked_at": "2026-07-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    config["invariants"] = [{**base, "evidence_file": "invariant-evidence.json"}]
    assert _status(tmp_path, config, None, now) == "stale"


def test_advisory_invariant_results_do_not_block_repository_gate_status() -> None:
    advisory_failure = {
        "id": "advisory-behavior",
        "status": "failed",
        "enforcement": "advisory",
    }
    assert verification_status([advisory_failure]) == "passed"

    required_report = {
        "schema": "quality-runner-invariant-verification-v0.1",
        "status": "unknown",
        "summary": {},
        "invariants": [
            {
                "id": "required-behavior",
                "enforcement": "required",
                "status": "unknown",
            }
        ],
    }
    applied = apply_invariant_status({"status": "passed"}, required_report)
    assert applied["status"] == "blocked"


def test_candidate_linked_required_invariant_fails_closed_without_supported_receipt(
    tmp_path: Path,
) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "surface.txt").write_text("proof\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "required_capabilities = []",
                "",
                "[[quality_runner.invariants]]",
                'id = "shared-workflow-classification"',
                'description = "Projections consume canonical workflow classification."',
                'owner = "workflow-platform"',
                'surfaces = ["surface.txt"]',
                'command = "python proof.py"',
                'enforcement = "required"',
                'candidate_id = "shared-workflow-classification-single-source"',
                'promotion_receipt = "promotion-receipt.json"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    scan = inspect_repo(tmp_path, run_id="candidate-promotion-blocked")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    missing = {str(item["id"]): item for item in _objects(capability_map["missing"])}
    assert missing["shared-workflow-classification"]["required_by"] == (
        "candidate-promotion-contract"
    )
    assert "candidate registry is missing" in str(
        missing["shared-workflow-classification"]["reason"]
    )


def test_candidate_linked_required_invariant_accepts_supported_human_receipt(
    tmp_path: Path,
) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.config import load_repo_config
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "surface.txt").write_text("proof\n", encoding="utf-8")
    _write_supported_candidate_contract(tmp_path)
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "required_capabilities = []",
                "",
                "[[quality_runner.invariants]]",
                'id = "shared-workflow-classification"',
                'description = "Projections consume canonical workflow classification."',
                'owner = "workflow-platform"',
                'surfaces = ["surface.txt"]',
                'command = "python proof.py"',
                'enforcement = "required"',
                'candidate_id = "shared-workflow-classification-single-source"',
                'promotion_receipt = "promotion-receipt.json"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    config = load_repo_config(tmp_path)
    scan = inspect_repo(tmp_path, run_id="candidate-promotion-supported")
    packet = compile_standards(
        repo_root=tmp_path,
        scan=scan,
        profile="default",
        config=config,
    )
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    invariant = next(
        item
        for item in _objects(capability_map["available"])
        if item["id"] == "shared-workflow-classification"
    )
    assert invariant["candidate_id"] == "shared-workflow-classification-single-source"
    assert invariant["promotion_receipt"] == "promotion-receipt.json"


def test_candidate_linked_required_invariant_rejects_unauditable_receipt(
    tmp_path: Path,
) -> None:
    from quality_runner.bug_learning import required_promotion_blocker

    (tmp_path / "surface.txt").write_text("proof\n", encoding="utf-8")
    _write_supported_candidate_contract(tmp_path)
    receipt_path = tmp_path / "promotion-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["decided_by"] = ""
    receipt["provenance_hash"] = digest(
        {key: value for key, value in receipt.items() if key != "provenance_hash"}
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    blocker = required_promotion_blocker(
        tmp_path,
        {
            "enforcement": "required",
            "candidate_id": "shared-workflow-classification-single-source",
            "promotion_receipt": "promotion-receipt.json",
        },
    )

    assert blocker == (
        "candidate-linked required invariant has an invalid candidate registry: "
        "candidates[0].promotion receipt decided_by must be a non-empty string"
    )


def test_verify_executes_required_invariant_and_writes_dedicated_artifact(
    tmp_path: Path,
) -> None:
    (tmp_path / "queue-ui.mjs").write_text("export const queue = [];\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/queue-ui.test.mjs").write_text("// proof\n", encoding="utf-8")
    _write_config(tmp_path, enforcement="required")
    _init_git_repo(tmp_path)

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="semantic-invariant-execution",
        execute_discovered_gates=True,
        worktree_mode="disposable",
        only_gate_ids=("human-only-review-not-reusable",),
    )
    artifact_paths = _object(payload["artifact_paths"])
    report = _json(Path(str(artifact_paths["invariant_verification_json"])))
    verification = _json(Path(str(artifact_paths["gate_verification_json"])))

    assert report["status"] == "passed"
    assert _objects(report["invariants"])[0]["status"] == "passed"
    assert verification["status"] == "passed"
    assert _object(verification["invariant_verification"])["status"] == "passed"


def _write_supported_candidate_contract(repo: Path) -> None:
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests/regression.test").write_text("proof\n", encoding="utf-8")
    (repo / "fixtures/positive").mkdir(parents=True)
    (repo / "fixtures/negative").mkdir(parents=True)
    (repo / "fixtures/positive/case.json").write_text("{}\n", encoding="utf-8")
    (repo / "fixtures/negative/case.json").write_text("{}\n", encoding="utf-8")
    candidate: dict[str, Any] = {
        "id": "shared-workflow-classification-single-source",
        "originating_regressions": ["classification-drift"],
        "failure_pattern": "Consumers independently reconstruct shared workflow classification.",
        "cause": "Canonical classification is not consumed directly.",
        "producer_surfaces": ["surface.txt"],
        "consumer_surfaces": ["surface.txt"],
        "detection_signal": {
            "kind": "repository-owned-regression",
            "description": "The regression exercises canonical classification consumption.",
        },
        "likely_false_positives": [
            "A documented projection intentionally owns its classification."
        ],
        "remediation": "Consume classification from the shared workflow record.",
        "owner": "workflow-platform",
        "provenance": [{"reference": "tests/regression.test"}],
        "status": "required-gate",
        "fixtures": {
            "positive": ["fixtures/positive/case.json"],
            "negative": ["fixtures/negative/case.json"],
        },
        "observations": [],
        "transitions": [
            _candidate_transition(None, "repository-regression"),
            _candidate_transition("repository-regression", "reusable-candidate"),
            _candidate_transition("reusable-candidate", "quality-runner-advisory"),
            _candidate_transition("quality-runner-advisory", "fleet-observation"),
            {
                **_candidate_transition("fleet-observation", "required-gate"),
                "evidence": ["promotion-receipt.json"],
            },
        ],
        "promotion_receipt": "promotion-receipt.json",
    }
    contract_hash = digest(
        {
            "id": candidate["id"],
            "failure_pattern": candidate["failure_pattern"],
            "cause": candidate["cause"],
            "detection_signal": candidate["detection_signal"],
            "remediation": candidate["remediation"],
        }
    )
    criteria = {
        "independent_repository_occurrences": _passed_criterion(2, 2),
        "classified_observation_history": _passed_criterion(5, 5),
        "precision": _passed_criterion(1.0, 0.95),
        "evaluation_cost": _passed_criterion(100, 30000),
        "freshness": _passed_criterion(5, "classified evidence within 90 days"),
        "deterministic_fixtures": _passed_criterion(
            {"positive": 1, "negative": 1},
            {"positive": 1, "negative": 1},
        ),
        "clear_remediation": _passed_criterion(1, 1),
        "candidate_contract_consistency": _passed_criterion(1, 1),
    }
    receipt: dict[str, Any] = {
        "schema": "quality-runner-candidate-promotion-receipt-v0.1",
        "status": "supported",
        "candidate_id": candidate["id"],
        "decision": "approved",
        "decided_by": "quality-owner",
        "decided_at": "2026-07-29T12:00:00Z",
        "decision_reason": "Fleet evidence supports promotion.",
        "registry_provenance_hash": "registry-hash-at-decision",
        "candidate_contract_hash": contract_hash,
        "fleet_provenance_hash": "fleet-hash",
        "promotion_criteria": criteria,
        "errors": [],
    }
    receipt["provenance_hash"] = digest(receipt)
    (repo / "promotion-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    registry = {
        "schema": "quality-runner-candidate-registry-v0.1",
        "repository": repo.name,
        "regressions": [
            {
                "id": "classification-drift",
                "summary": "A projection drifted from canonical classification.",
                "regression_test": "tests/regression.test",
                "command": "run regression",
                "confirmed_at": "2026-07-29T10:00:00Z",
                "provenance": {"reference": "tests/regression.test"},
            }
        ],
        "candidates": [candidate],
    }
    (repo / "quality-runner-candidates.json").write_text(
        json.dumps(registry),
        encoding="utf-8",
    )


def _candidate_transition(source: str | None, target: str) -> dict[str, object]:
    return {
        "from": source,
        "to": target,
        "at": "2026-07-29T10:00:00Z",
        "actor": "quality-owner",
        "reason": f"Advance to {target}.",
        "evidence": ["tests/regression.test"],
    }


def _passed_criterion(actual: object, required: object) -> dict[str, object]:
    return {"passed": True, "actual": actual, "required": required}


def _write_config(repo: Path, *, enforcement: str) -> None:
    command = f'{sys.executable} -c "raise SystemExit(0)"'
    (repo / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "required_capabilities = []",
                "",
                "[[quality_runner.invariants]]",
                'id = "human-only-review-not-reusable"',
                'description = "Handoff-only prompts never enter the reusable answer queue."',
                'owner = "application-review-classifier"',
                'surfaces = ["queue-ui.mjs", "tests/queue-ui.test.mjs"]',
                f"command = {json.dumps(command)}",
                f'enforcement = "{enforcement}"',
                'ecosystem = "javascript"',
                'mutating_risk = "safe"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _status(
    repo: Path,
    config: dict[str, object],
    gate: dict[str, object] | None,
    now: datetime,
) -> str:
    verification = (
        {
            "gates": [
                {
                    "id": "durable-behavior",
                    **gate,
                }
            ]
        }
        if gate is not None
        else None
    )
    report = build_invariant_report(
        repo_root=repo,
        config=config,
        gate_verification=verification,
        now=now,
    )
    return str(_objects(report["invariants"])[0]["status"])


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=quality-runner@example.com",
            "-c",
            "user.name=Quality Runner",
            "commit",
            "-m",
            "Add invariant fixture",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _json(path: Path) -> dict[str, object]:
    return _object(json.loads(path.read_text(encoding="utf-8")))


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _objects(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [_object(item) for item in value]
