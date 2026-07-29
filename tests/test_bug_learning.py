from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from quality_runner.bug_learning import (
    CANDIDATE_FLEET_SCHEMA,
    PROMOTION_DECISION_SCHEMA,
    aggregate_candidate_fleet,
    check_candidate_promotion,
    validate_candidate_registry,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/bug-learning/shared-workflow-classification"
CANDIDATE_ID = "shared-workflow-classification-single-source"


def test_candidate_registry_requires_disposition_for_every_confirmed_bug(
    tmp_path: Path,
) -> None:
    _write_registry(tmp_path, observations=[], regression_id="confirmed-drift")
    registry = _json(tmp_path / "quality-runner-candidates.json")
    registry["candidates"] = []
    (tmp_path / "quality-runner-candidates.json").write_text(
        json.dumps(registry),
        encoding="utf-8",
    )

    validation = validate_candidate_registry(tmp_path)

    assert validation["status"] == "rejected"
    assert "missing candidate coverage: confirmed-drift" in " ".join(
        cast(list[str], validation["errors"])
    )


def test_candidate_registry_rejects_silent_or_unsupported_transition(
    tmp_path: Path,
) -> None:
    _write_registry(tmp_path, observations=[])
    registry = _json(tmp_path / "quality-runner-candidates.json")
    candidate = _objects(registry["candidates"])[0]
    candidate["status"] = "required-gate"
    candidate["transitions"] = [
        _transition(None, "repository-regression", "regression"),
        _transition("repository-regression", "required-gate", "silent promotion"),
    ]
    (tmp_path / "quality-runner-candidates.json").write_text(
        json.dumps(registry),
        encoding="utf-8",
    )

    validation = validate_candidate_registry(tmp_path)

    assert validation["status"] == "rejected"
    assert "not an allowed lifecycle transition" in " ".join(cast(list[str], validation["errors"]))


def test_candidate_registry_rejects_malformed_history_and_provenance(
    tmp_path: Path,
) -> None:
    _write_registry(tmp_path, observations=[])
    registry = _json(tmp_path / "quality-runner-candidates.json")
    regression = _objects(registry["regressions"])[0]
    candidate = _objects(registry["candidates"])[0]
    regression["confirmed_at"] = "not-a-timestamp"
    candidate["observations"] = "not-an-array"
    candidate["provenance"] = [{}]
    (tmp_path / "quality-runner-candidates.json").write_text(
        json.dumps(registry),
        encoding="utf-8",
    )

    validation = validate_candidate_registry(tmp_path)
    errors = " ".join(cast(list[str], validation["errors"]))

    assert validation["status"] == "rejected"
    assert "confirmed_at must be timezone-aware" in errors
    assert "observations must be an array" in errors
    assert "provenance must contain only non-empty objects" in errors


def test_candidate_registry_has_machine_readable_cli_validation(tmp_path: Path) -> None:
    _write_registry(tmp_path, observations=[])

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "candidates",
            "validate",
            str(tmp_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["status"] == "passed"
    assert payload["regression_count"] == 1
    assert payload["covered_regression_count"] == 1


def test_fleet_aggregation_preserves_history_and_supports_evidence_thresholds(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    alpha = projects / "alpha"
    beta = projects / "beta"
    _init_repo(alpha)
    _init_repo(beta)
    old_observation = _observation("alpha-old-clean", "true-negative", "not-detected", 75)
    old_observation["observed_at"] = "2025-01-01T11:00:00Z"
    _write_registry(
        alpha,
        observations=[
            old_observation,
            _observation("alpha-defect", "true-positive", "detected", 120),
            _observation("alpha-clean-one", "true-negative", "not-detected", 90),
            _observation("alpha-clean-two", "true-negative", "not-detected", 85),
        ],
        status="fleet-observation",
    )
    _write_registry(
        beta,
        observations=[
            _observation("beta-defect", "true-positive", "detected", 110),
            _observation("beta-clean", "true-negative", "not-detected", 80),
        ],
        status="fleet-observation",
    )
    output = tmp_path / "candidate-fleet.json"

    first = aggregate_candidate_fleet(
        projects_root=projects,
        output_path=output,
        as_of="2026-07-29T12:00:00Z",
    )
    group = _objects(first["candidates"])[0]

    assert first["schema"] == CANDIDATE_FLEET_SCHEMA
    assert first["status"] == "completed"
    assert group["fresh_observation_count"] == 5
    assert group["fresh_classified_observation_count"] == 5
    assert len(_objects(group["observations"])) == 6
    assert group["precision"] == 1.0
    assert group["promotion_supported_by_evidence"] is True
    assert len(cast(list[str], group["independent_occurrence_repositories"])) == 2

    beta_registry = _json(beta / "quality-runner-candidates.json")
    _objects(beta_registry["candidates"])[0]["observations"] = []
    (beta / "quality-runner-candidates.json").write_text(
        json.dumps(beta_registry),
        encoding="utf-8",
    )
    second = aggregate_candidate_fleet(
        projects_root=projects,
        output_path=output,
        as_of="2026-07-29T12:00:00Z",
    )

    assert _objects(second["candidates"])[0]["fresh_observation_count"] == 5


def test_required_promotion_needs_passing_fleet_evidence_and_human_decision(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    alpha = projects / "alpha"
    beta = projects / "beta"
    _init_repo(alpha)
    _init_repo(beta)
    _write_registry(
        alpha,
        observations=[
            _observation("alpha-defect", "true-positive", "detected", 120),
            _observation("alpha-clean-one", "true-negative", "not-detected", 90),
            _observation("alpha-clean-two", "true-negative", "not-detected", 85),
        ],
        status="fleet-observation",
    )
    _write_registry(
        beta,
        observations=[
            _observation("beta-defect", "true-positive", "detected", 110),
            _observation("beta-clean", "true-negative", "not-detected", 80),
        ],
        status="fleet-observation",
    )
    fleet_path = tmp_path / "candidate-fleet.json"
    fleet = aggregate_candidate_fleet(
        projects_root=projects,
        output_path=fleet_path,
        as_of="2026-07-29T12:00:00Z",
    )
    decision_path = alpha / "promotion-decision.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema": PROMOTION_DECISION_SCHEMA,
                "candidate_id": CANDIDATE_ID,
                "decision": "approved",
                "decided_by": "quality-owner",
                "decided_at": "2026-07-29T12:05:00Z",
                "reason": "Independent occurrences are precise, cheap, and remediable.",
                "fleet_provenance_hash": fleet["provenance_hash"],
            }
        ),
        encoding="utf-8",
    )

    receipt_path = alpha / "promotion-receipt.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "candidates",
            "promotion-check",
            str(alpha),
            "--candidate-id",
            CANDIDATE_ID,
            "--fleet-evidence",
            str(fleet_path),
            "--decision",
            str(decision_path),
            "--output",
            str(receipt_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(result.stdout)

    assert receipt["status"] == "supported"
    assert receipt["decision"] == "approved"
    assert receipt["errors"] == []
    assert receipt["artifact_path"] == str(receipt_path)

    registry = _json(alpha / "quality-runner-candidates.json")
    candidate = _objects(registry["candidates"])[0]
    candidate["status"] = "required-gate"
    candidate["promotion_receipt"] = "promotion-receipt.json"
    candidate["transitions"].append(
        {
            **_transition(
                "fleet-observation",
                "required-gate",
                "human approved supported promotion",
            ),
            "at": "2026-07-29T12:06:00Z",
            "evidence": ["promotion-receipt.json"],
        }
    )
    (alpha / "quality-runner-candidates.json").write_text(
        json.dumps(registry),
        encoding="utf-8",
    )
    assert validate_candidate_registry(alpha)["status"] == "passed"

    tampered_registry = _json(alpha / "quality-runner-candidates.json")
    _objects(tampered_registry["candidates"])[0]["cause"] = "A different candidate contract."
    (alpha / "quality-runner-candidates.json").write_text(
        json.dumps(tampered_registry),
        encoding="utf-8",
    )
    tampered = validate_candidate_registry(alpha)
    assert tampered["status"] == "rejected"
    assert "candidate contract does not match" in " ".join(cast(list[str], tampered["errors"]))
    (alpha / "quality-runner-candidates.json").write_text(
        json.dumps(registry),
        encoding="utf-8",
    )

    decision = _json(decision_path)
    decision["decision"] = "deferred"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    blocked = check_candidate_promotion(
        repo_root=alpha,
        candidate_id=CANDIDATE_ID,
        fleet_evidence_path=fleet_path,
        decision_path=decision_path,
    )
    assert blocked["status"] == "blocked"


def test_synthetic_fixture_detects_independent_semantic_reconstruction_only() -> None:
    positive = subprocess.run(
        [sys.executable, str(FIXTURE_ROOT / "detector.py"), str(FIXTURE_ROOT / "positive")],
        check=False,
        capture_output=True,
        text=True,
    )
    negative = subprocess.run(
        [sys.executable, str(FIXTURE_ROOT / "detector.py"), str(FIXTURE_ROOT / "negative")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert positive.returncode == 1
    assert "reconstructed independently" in positive.stdout
    assert negative.returncode == 0
    assert "consume the shared workflow classification" in negative.stdout


def _write_registry(
    root: Path,
    *,
    observations: list[dict[str, object]],
    regression_id: str = "confirmed-classification-drift",
    status: str = "fleet-observation",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests/regression.test").write_text("regression\n", encoding="utf-8")
    (root / "producer.json").write_text("{}\n", encoding="utf-8")
    (root / "consumer.json").write_text("{}\n", encoding="utf-8")
    (root / "fixtures/positive").mkdir(parents=True, exist_ok=True)
    (root / "fixtures/negative").mkdir(parents=True, exist_ok=True)
    (root / "fixtures/positive/case.json").write_text("{}\n", encoding="utf-8")
    (root / "fixtures/negative/case.json").write_text("{}\n", encoding="utf-8")
    transitions = [
        _transition(None, "repository-regression", "regression confirmed"),
        _transition(
            "repository-regression",
            "reusable-candidate",
            "broader pattern identified",
        ),
        _transition(
            "reusable-candidate",
            "quality-runner-advisory",
            "deterministic signal registered",
        ),
        _transition(
            "quality-runner-advisory",
            "fleet-observation",
            "fleet observation started",
        ),
    ]
    if status == "required-gate":
        transitions.append(
            _transition(
                "fleet-observation",
                "required-gate",
                "human approved supported promotion",
            )
        )
    payload = {
        "schema": "quality-runner-candidate-registry-v0.1",
        "repository": root.name,
        "regressions": [
            {
                "id": regression_id,
                "summary": "Projection semantics drifted from the shared workflow record.",
                "regression_test": "tests/regression.test",
                "command": "python tests/regression.test",
                "confirmed_at": "2026-07-29T10:00:00Z",
                "provenance": {"commit": "abc123"},
            }
        ],
        "candidates": [
            {
                "id": CANDIDATE_ID,
                "originating_regressions": [regression_id],
                "failure_pattern": (
                    "A shared workflow record feeds multiple projections whose semantic "
                    "classification is reconstructed independently."
                ),
                "cause": "Consumers infer business meaning instead of consuming canonical state.",
                "producer_surfaces": ["producer.json"],
                "consumer_surfaces": ["consumer.json"],
                "detection_signal": {
                    "kind": "repository-owned-regression",
                    "description": "The regression command exercises canonical projection semantics.",
                    "command": "python tests/regression.test",
                },
                "likely_false_positives": [
                    "A projection intentionally owns a different documented classification."
                ],
                "remediation": (
                    "Persist classification on the shared workflow record and make all projections "
                    "consume it directly."
                ),
                "owner": "workflow-platform",
                "provenance": [{"regression": regression_id}],
                "status": status,
                "fixtures": {
                    "positive": ["fixtures/positive/case.json"],
                    "negative": ["fixtures/negative/case.json"],
                },
                "observations": observations,
                "transitions": transitions,
            }
        ],
    }
    (root / "quality-runner-candidates.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _observation(
    observation_id: str,
    classification: str,
    result: str,
    duration_ms: int,
) -> dict[str, object]:
    return {
        "id": observation_id,
        "observed_at": "2026-07-29T11:00:00Z",
        "result": result,
        "classification": classification,
        "duration_ms": duration_ms,
        "evidence": {"reference": f"fixture:{observation_id}"},
    }


def _transition(source: str | None, target: str, reason: str) -> dict[str, object]:
    return {
        "from": source,
        "to": target,
        "at": "2026-07-29T10:00:00Z",
        "actor": "quality-owner",
        "reason": reason,
        "evidence": ["tests/regression.test"],
    }


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _objects(value: object) -> list[dict[str, Any]]:
    assert isinstance(value, list)
    return [cast(dict[str, Any], item) for item in value]
