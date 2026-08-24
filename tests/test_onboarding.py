from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.cli import main
from quality_runner.onboarding import (
    ONBOARDING_CHECK_SCHEMA,
    ONBOARDING_EVIDENCE_SCHEMA,
    onboarding_check_payload,
)

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Onboarding Tests")
    _git(repo, "config", "user.email", "onboarding-tests@example.invalid")
    (repo / ".gitignore").write_text(".quality-runner/\n", encoding="utf-8")
    (repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
    (repo / "package.json").write_text(
        json.dumps({"scripts": {"verify": "pnpm lint && pnpm test"}}) + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".gitignore", "README.md", "package.json")
    _git(repo, "commit", "-m", "fixture")
    _git(repo, "branch", "dev")
    return repo, _git(repo, "rev-parse", "HEAD")


def _matrix(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "change-surface-matrix/v1",
        "subject": {"kind": "repository-fleet", "id": "test-fleet"},
        "baseline": {
            "required_on_add": ["repository-identity", "executable-quality-evidence"],
            "conditional": ["remote-provenance"],
        },
        "surfaces": [
            {"id": "repository-identity", "status": "required"},
            {"id": "executable-quality-evidence", "status": "required"},
            {"id": "remote-provenance", "status": "conditional"},
        ],
        "onboarding_validator": {
            "command": "qr onboarding check REPOSITORY --matrix MATRIX --evidence EVIDENCE --json",
            "evidence_schema": "quality-runner-onboarding-evidence/v1",
            "receipt_schema": "quality-runner-onboarding-check/v1",
            "surface_producers": {
                "repository-identity": ["quality-runner"],
                "executable-quality-evidence": ["quality-runner"],
                "remote-provenance": ["provider-evidence"],
            },
            "executable_quality": {
                "required_gates": [
                    "lint",
                    "typecheck",
                    "tests-coverage",
                    "dead-code",
                    "domain-validation",
                    "security",
                    "build",
                ],
                "required_negative_controls": [
                    "clean-fixture",
                    "seeded-violation",
                    "missing-tool",
                    "skipped-required-adapter",
                ],
            },
        },
    }
    _write_json(path, payload)
    return payload


def _gate_receipt(repo: Path, *, branch: str, head_sha: str) -> tuple[str, str]:
    relative = ".quality-runner/runs/onboarding/gate-verification.json"
    path = repo / relative
    _write_json(
        path,
        {
            "schema": "quality-runner-gate-verification-v0.2",
            "status": "passed",
            "timeout_seconds": 600,
            "execute_discovered_gates": True,
            "read_only_gates": True,
            "allow_mutating_gates": False,
            "provenance": {
                "head_sha": head_sha,
                "branch": branch,
                "ref": f"refs/heads/{branch}",
                "quality_runner_version": "0.0.test",
                "captured_at": "2026-08-24T12:00:00+00:00",
                "worktree_mode": "disposable",
                "workflow_run_id": "onboarding",
            },
            "verification_context": {
                "worktree_mode": "disposable",
                "base_head": head_sha,
                "execution_root": str(repo),
                "mutations_isolated": True,
                "dirty_source_worktree": False,
                "execution_authorized": True,
            },
            "gates": [
                {
                    "id": "canonical-verify",
                    "status": "passed",
                    "enforcement": "required",
                    "command": "pnpm verify",
                }
            ],
        },
    )
    return relative, _sha256(path)


def _quality_details(repo: Path, *, branch: str, head_sha: str) -> dict[str, Any]:
    receipt_path, receipt_sha = _gate_receipt(repo, branch=branch, head_sha=head_sha)
    return {
        "canonical_verify_command": "pnpm verify",
        "ci": {
            "status": "passed",
            "verify_command": "pnpm verify",
            "locked_dependencies": True,
            "branch": branch,
            "head_sha": head_sha,
        },
        "result": {"warnings": 0, "errors": 0},
        "gates": [
            {"id": gate_id, "status": "passed", "applicability": "applicable"}
            for gate_id in (
                "lint",
                "typecheck",
                "tests-coverage",
                "dead-code",
                "domain-validation",
                "security",
                "build",
            )
        ],
        "negative_controls": [
            {"id": "clean-fixture", "status": "passed"},
            {"id": "seeded-violation", "status": "blocked"},
            {"id": "missing-tool", "status": "blocked"},
            {"id": "skipped-required-adapter", "status": "blocked"},
        ],
        "baselines": [],
        "quality_runner_receipt": {
            "path": receipt_path,
            "sha256": receipt_sha,
            "schema": "quality-runner-gate-verification-v0.2",
        },
    }


def _surface(
    surface_id: str,
    producer: str,
    *,
    branch: str,
    head_sha: str,
    status: str = "passed",
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "surface_id": surface_id,
        "status": status,
        "producer": {"id": producer, "version": "0.0.test"},
        "observed_at": "2026-08-24T12:00:00+00:00",
        "target": {"branch": branch, "head_sha": head_sha},
        "evidence": [f"receipt:{surface_id}"],
    }
    if reason is not None:
        result["reason"] = reason
    if details is not None:
        result["details"] = details
    return result


def _evidence(
    path: Path,
    *,
    repo: Path,
    matrix_path: Path,
    branch: str,
    head_sha: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "quality-runner-onboarding-evidence/v1",
        "matrix_sha256": _sha256(matrix_path),
        "repository": {"id": repo.name, "branch": branch, "head_sha": head_sha},
        "surfaces": [
            _surface(
                "repository-identity",
                "quality-runner",
                branch=branch,
                head_sha=head_sha,
            ),
            _surface(
                "executable-quality-evidence",
                "quality-runner",
                branch=branch,
                head_sha=head_sha,
                details=_quality_details(repo, branch=branch, head_sha=head_sha),
            ),
            _surface(
                "remote-provenance",
                "provider-evidence",
                branch=branch,
                head_sha=head_sha,
                status="not_applicable",
                reason="The fixture intentionally has no remote.",
            ),
        ],
    }
    _write_json(path, payload)
    return payload


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    repo, head_sha = _repository(tmp_path)
    matrix_path = tmp_path / "matrix.json"
    _matrix(matrix_path)
    evidence_path = repo / ".quality-runner" / "onboarding-evidence.json"
    _evidence(
        evidence_path,
        repo=repo,
        matrix_path=matrix_path,
        branch="main",
        head_sha=head_sha,
    )
    return repo, matrix_path, evidence_path, head_sha


def test_onboarding_check_passes_only_complete_exact_ref_evidence(tmp_path: Path) -> None:
    repo, matrix_path, evidence_path, head_sha = _fixture(tmp_path)

    result = onboarding_check_payload(
        repo_root=repo,
        matrix_path=matrix_path,
        evidence_path=evidence_path,
        generated_at="2026-08-24T12:00:01+00:00",
    )

    assert result["status"] == "passed"
    assert result["readiness"] == "ready"
    assert result["repository"]["head_sha"] == head_sha
    assert result["blocking_check_ids"] == []
    assert result["blocking_surface_ids"] == []


def test_distributed_onboarding_schemas_match_runtime_contracts() -> None:
    check_schema = json.loads(
        (ROOT / "quality_runner/schemas/onboarding-check.schema.json").read_text(encoding="utf-8")
    )
    evidence_schema = json.loads(
        (ROOT / "quality_runner/schemas/onboarding-evidence.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert check_schema["properties"]["schema"]["const"] == ONBOARDING_CHECK_SCHEMA
    assert evidence_schema["properties"]["schema"]["const"] == ONBOARDING_EVIDENCE_SCHEMA


def test_missing_unknown_and_unexplained_conditional_surfaces_block(tmp_path: Path) -> None:
    repo, matrix_path, evidence_path, _ = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["surfaces"] = [
        surface
        for surface in evidence["surfaces"]
        if surface["surface_id"] != "repository-identity"
    ]
    conditional = next(
        surface for surface in evidence["surfaces"] if surface["surface_id"] == "remote-provenance"
    )
    conditional["status"] = "not_applicable"
    conditional.pop("reason")
    _write_json(evidence_path, evidence)

    result = onboarding_check_payload(
        repo_root=repo,
        matrix_path=matrix_path,
        evidence_path=evidence_path,
    )

    assert result["status"] == "blocked"
    assert result["readiness"] == "not_ready"
    assert set(result["blocking_surface_ids"]) == {
        "remote-provenance",
        "repository-identity",
    }


def test_stale_head_and_matrix_digest_block_even_when_surfaces_say_passed(
    tmp_path: Path,
) -> None:
    repo, matrix_path, evidence_path, _ = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["matrix_sha256"] = "0" * 64
    evidence["repository"]["head_sha"] = "1" * 40
    _write_json(evidence_path, evidence)

    result = onboarding_check_payload(
        repo_root=repo,
        matrix_path=matrix_path,
        evidence_path=evidence_path,
    )

    assert result["status"] == "blocked"
    assert {"evidence_matrix", "evidence_provenance"}.issubset(set(result["blocking_check_ids"]))


def test_quality_surface_rejects_warnings_or_missing_negative_controls(tmp_path: Path) -> None:
    repo, matrix_path, evidence_path, _ = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    quality = next(
        surface
        for surface in evidence["surfaces"]
        if surface["surface_id"] == "executable-quality-evidence"
    )
    quality["details"]["result"]["warnings"] = 1
    quality["details"]["negative_controls"] = [
        control
        for control in quality["details"]["negative_controls"]
        if control["id"] != "seeded-violation"
    ]
    _write_json(evidence_path, evidence)

    result = onboarding_check_payload(
        repo_root=repo,
        matrix_path=matrix_path,
        evidence_path=evidence_path,
    )

    assert result["status"] == "blocked"
    quality_surface = next(
        surface for surface in result["surfaces"] if surface["id"] == "executable-quality-evidence"
    )
    assert quality_surface["status"] == "blocked"
    assert {violation["rule"] for violation in quality_surface["violations"]} >= {
        "nonzero-quality-findings",
        "missing-negative-control",
    }


def test_quality_surface_rejects_tampered_gate_receipt(tmp_path: Path) -> None:
    repo, matrix_path, evidence_path, _ = _fixture(tmp_path)
    receipt = repo / ".quality-runner/runs/onboarding/gate-verification.json"
    receipt.write_text(receipt.read_text(encoding="utf-8") + " ", encoding="utf-8")

    result = onboarding_check_payload(
        repo_root=repo,
        matrix_path=matrix_path,
        evidence_path=evidence_path,
    )

    quality_surface = next(
        surface for surface in result["surfaces"] if surface["id"] == "executable-quality-evidence"
    )
    assert quality_surface["status"] == "blocked"
    assert "receipt-digest-mismatch" in {
        violation["rule"] for violation in quality_surface["violations"]
    }


def test_onboarding_cli_is_read_only_unless_output_is_explicit(tmp_path: Path) -> None:
    repo, matrix_path, evidence_path, _ = _fixture(tmp_path)
    before = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")

    assert (
        main(
            [
                "onboarding",
                "check",
                str(repo),
                "--matrix",
                str(matrix_path),
                "--evidence",
                str(evidence_path),
                "--json",
            ]
        )
        == 0
    )
    assert _git(repo, "status", "--porcelain=v1", "--untracked-files=all") == before

    output_path = tmp_path / "onboarding-check.json"
    assert (
        main(
            [
                "onboarding",
                "check",
                str(repo),
                "--matrix",
                str(matrix_path),
                "--evidence",
                str(evidence_path),
                "--output",
                str(output_path),
                "--json",
            ]
        )
        == 0
    )
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["schema"] == "quality-runner-onboarding-check/v1"
    assert persisted["output_path"] == str(output_path.resolve())


def test_onboarding_cli_returns_nonzero_for_non_ready_repository(tmp_path: Path) -> None:
    repo, matrix_path, evidence_path, _ = _fixture(tmp_path)
    evidence_path.unlink()

    assert (
        main(
            [
                "onboarding",
                "check",
                str(repo),
                "--matrix",
                str(matrix_path),
                "--evidence",
                str(evidence_path),
                "--json",
            ]
        )
        == 1
    )
