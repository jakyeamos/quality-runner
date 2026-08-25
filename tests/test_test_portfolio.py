from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from quality_runner.cli import main
from quality_runner.test_portfolio import (
    PORTFOLIO_AUDIT_SCHEMA,
    PORTFOLIO_INPUT_SCHEMA,
    REMOVAL_INPUT_SCHEMA,
    REMOVAL_PROOF_SCHEMA,
    audit_test_portfolio,
    build_test_removal_proof,
)


def _portfolio_manifest() -> dict[str, Any]:
    return {
        "schema": PORTFOLIO_INPUT_SCHEMA,
        "repository": {"id": "example"},
        "revision": {"head": "base123", "worktree_clean": True},
        "tests": [
            {
                "id": "tests/test_api.py::test_rejects_missing_token",
                "path": "tests/test_api.py",
                "behaviors": ["missing tokens are rejected"],
                "critical_contract": True,
                "unique_signals": ["kills auth-bypass-mutant"],
                "reviewers": [
                    {
                        "reviewer": "review-a",
                        "recommendation": "keep",
                        "rationale": "protects an authorization boundary",
                    }
                ],
            },
            {
                "id": "tests/test_api.py::test_lists_items_copy",
                "path": "tests/test_api.py",
                "behaviors": ["items are listed"],
                "reviewers": [
                    {
                        "reviewer": "review-a",
                        "recommendation": "delete_candidate",
                        "rationale": "duplicates the contract test",
                    },
                    {
                        "reviewer": "review-b",
                        "recommendation": "delete_candidate",
                        "rationale": "adds no distinct assertion",
                    },
                ],
            },
            {
                "id": "tests/test_api.py::test_lists_items",
                "path": "tests/test_api.py",
                "behaviors": ["items are listed"],
                "reviewers": [
                    {
                        "reviewer": "review-a",
                        "recommendation": "keep",
                        "rationale": "owns the behavior contract",
                    }
                ],
            },
        ],
    }


def _removal_manifest(audit: dict[str, Any]) -> dict[str, Any]:
    removed = "tests/test_api.py::test_lists_items_copy"
    return {
        "schema": REMOVAL_INPUT_SCHEMA,
        "repository": {"id": "example"},
        "revision": {"base": "base123", "head": "head456", "worktree_clean": True},
        "portfolio_audit": audit,
        "removed_test_ids": [removed],
        "suite": {
            "baseline": {"revision": "base123", "status": "passed", "test_count": 3},
            "current": {"revision": "head456", "status": "passed", "test_count": 2},
        },
        "mutation": {
            "status": "complete",
            "target_set_hash": "mutants-v1",
            "baseline": {
                "revision": "base123",
                "target_set_hash": "mutants-v1",
                "killed": 12,
                "survived": 1,
                "no_coverage": 0,
            },
            "current": {
                "revision": "head456",
                "target_set_hash": "mutants-v1",
                "killed": 12,
                "survived": 1,
                "no_coverage": 0,
            },
        },
    }


def test_portfolio_audit_keeps_unique_signal_and_nominates_only_redundant_test() -> None:
    audit = audit_test_portfolio(_portfolio_manifest())
    candidates = {candidate["test_id"]: candidate for candidate in audit["candidates"]}

    assert audit["schema"] == PORTFOLIO_AUDIT_SCHEMA
    assert audit["implementation_allowed"] is False
    assert audit["summary"]["removal_candidates"] == 1
    assert candidates["tests/test_api.py::test_rejects_missing_token"]["disposition"] == "keep"
    assert candidates["tests/test_api.py::test_lists_items_copy"]["disposition"] == (
        "delete_candidate"
    )
    assert candidates["tests/test_api.py::test_lists_items"]["disposition"] == (
        "insufficient_evidence"
    )
    assert audit["authority"]["reviewer_recommendations_authorize_removal"] is False


def test_portfolio_audit_preserves_reviewer_disagreement_as_unknown() -> None:
    manifest = _portfolio_manifest()
    duplicate = manifest["tests"][1]
    duplicate["reviewers"][1] = {
        "reviewer": "review-b",
        "recommendation": "keep",
        "rationale": "may protect a separate call path",
    }

    audit = audit_test_portfolio(manifest)
    candidate = next(
        item
        for item in audit["candidates"]
        if item["test_id"] == "tests/test_api.py::test_lists_items_copy"
    )
    assert candidate["disposition"] == "insufficient_evidence"
    assert candidate["confidence"] == "low"


def test_removal_proof_passes_only_with_exact_dynamic_preservation() -> None:
    audit = audit_test_portfolio(_portfolio_manifest())
    proof = build_test_removal_proof(_removal_manifest(audit))

    assert proof["schema"] == REMOVAL_PROOF_SCHEMA
    assert proof["status"] == "passed"
    assert proof["blockers"] == []
    assert proof["implementation_allowed"] is False
    assert proof["authority"]["proof_executes_removal"] is False


@pytest.mark.parametrize(
    ("edit", "blocker"),
    [
        (lambda manifest: manifest.pop("mutation"), "dynamic-removal-evidence"),
        (
            lambda manifest: manifest["mutation"]["current"].update({"survived": 2}),
            "mutation-preservation",
        ),
        (
            lambda manifest: manifest["revision"].update({"worktree_clean": False}),
            "clean-exact-revisions",
        ),
    ],
)
def test_removal_proof_fails_closed_on_missing_or_regressed_evidence(edit, blocker: str) -> None:
    audit = audit_test_portfolio(_portfolio_manifest())
    manifest = _removal_manifest(audit)
    edit(manifest)

    proof = build_test_removal_proof(manifest)
    assert proof["status"] == "blocked"
    assert blocker in proof["blockers"]


def test_removal_proof_rejects_tampered_portfolio_audit() -> None:
    audit = audit_test_portfolio(_portfolio_manifest())
    audit["candidates"][1]["disposition"] = "keep"

    with pytest.raises(ValueError, match="hash does not match"):
        build_test_removal_proof(_removal_manifest(audit))


def test_tests_cli_writes_explicit_artifacts_and_returns_nonzero_when_blocked(
    tmp_path: Path, capsys
) -> None:
    portfolio_path = tmp_path / "portfolio.json"
    audit_path = tmp_path / "audit.json"
    removal_path = tmp_path / "removal.json"
    proof_path = tmp_path / "proof.json"
    portfolio_path.write_text(json.dumps(_portfolio_manifest()), encoding="utf-8")

    assert (
        main(
            [
                "tests",
                "portfolio-audit",
                str(portfolio_path),
                "--output",
                str(audit_path),
                "--json",
            ]
        )
        == 0
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    removal = _removal_manifest(audit)
    removal.pop("mutation")
    removal_path.write_text(json.dumps(removal), encoding="utf-8")

    assert (
        main(
            [
                "tests",
                "removal-proof",
                str(removal_path),
                "--output",
                str(proof_path),
                "--json",
            ]
        )
        == 1
    )
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert proof["status"] == "blocked"
    assert '"status": "blocked"' in capsys.readouterr().out
