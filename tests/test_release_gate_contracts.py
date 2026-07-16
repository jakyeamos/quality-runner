from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quality_runner.aggregate_coverage import analyze_aggregate_coverage
from quality_runner.ci_status import load_ci_status
from quality_runner.lifecycle_status import compute_lifecycle_status
from quality_runner.readiness import (
    READINESS_GATE_IDS,
    _manifest_gate,
    _migration_evidence_gate,
    _provenance_gate,
    validate_release_evidence,
)
from quality_runner.security.agent_gates import build_agent_review_gates
from quality_runner.security.scan import detect_security_surfaces


def _valid_release_evidence(*, head: str = "head", version: str = "1.2.3") -> dict[str, object]:
    return {
        "schema": "quality-runner-release-evidence-v0.1",
        "target": {"head_sha": head, "ref": "main"},
        "release_version": version,
        "owner": {"name": "Release Owner", "role": "maintainer"},
        "acceptance": [{"id": "release", "status": "accepted", "evidence": ["ticket-1"]}],
        "artifact": {
            "version": version,
            "digest": "sha256:" + "a" * 64,
            "source_head": head,
        },
    }


def test_ci_status_normalizes_top_level_and_per_check_provenance(tmp_path: Path) -> None:
    path = tmp_path / "ci.json"
    path.write_text(
        json.dumps(
            {
                "head_sha": "top-head",
                "ref": "refs/heads/main",
                "workflow_run_id": "workflow-1",
                "captured_at": datetime.now(UTC).isoformat(),
                "checks": [
                    {
                        "name": "Quality / Tests",
                        "status": "completed",
                        "conclusion": "success",
                        "provenance": {"head_sha": "check-head"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    checks, warnings = load_ci_status(tmp_path, path)

    assert warnings == []
    assert checks[0]["head_sha"] == "check-head"
    assert checks[0]["ref"] == "refs/heads/main"
    assert checks[0]["workflow_run_id"] == "workflow-1"


def test_provenance_gate_rejects_head_ref_and_stale_evidence() -> None:
    current = {
        "head_sha": "current-head",
        "branch": "main",
    }
    evidence = _valid_release_evidence(head="current-head")
    fresh = datetime.now(UTC).isoformat()
    base_check = {
        "name": "Quality / Tests",
        "conclusion": "success",
        "head_sha": "current-head",
        "ref": "refs/heads/main",
        "workflow_run_id": "workflow-1",
        "captured_at": fresh,
    }

    assert (
        _provenance_gate(
            scan={"ci_checks": [base_check]},
            current_git=current,
            evidence=evidence,
            evidence_error=None,
        )["status"]
        == "passed"
    )
    mismatched = {**base_check, "head_sha": "old-head"}
    assert (
        _provenance_gate(
            scan={"ci_checks": [mismatched]},
            current_git=current,
            evidence=evidence,
            evidence_error=None,
        )["blocker_class"]
        == "provenance"
    )
    wrong_ref = {**base_check, "ref": "refs/heads/other"}
    assert (
        "ref"
        in _provenance_gate(
            scan={"ci_checks": [wrong_ref]},
            current_git=current,
            evidence=evidence,
            evidence_error=None,
        )["reason"]
    )
    assert (
        _provenance_gate(
            scan={"ci_checks": [base_check]},
            current_git={"head_sha": "current-head"},
            evidence=evidence,
            evidence_error=None,
        )["blocker_class"]
        == "provenance"
    )
    stale = {**base_check, "captured_at": (datetime.now(UTC) - timedelta(days=2)).isoformat()}
    assert (
        "stale"
        in _provenance_gate(
            scan={"ci_checks": [stale]},
            current_git=current,
            evidence=evidence,
            evidence_error=None,
        )["reason"]
    )


def test_release_evidence_validation_requires_decisions_and_external_proof() -> None:
    valid = _valid_release_evidence()
    assert validate_release_evidence(valid) == []

    empty_acceptance = {**valid, "acceptance": []}
    assert any(
        "at least one decision" in error for error in validate_release_evidence(empty_acceptance)
    )
    invalid_external = {
        **valid,
        "external_checks": [{"id": "staging", "status": "passed", "evidence": []}],
    }
    assert any(
        "external_checks[0].evidence" in error
        for error in validate_release_evidence(invalid_external)
    )
    invalid_migration = {**valid, "migration": {"forward": "passed"}}
    assert any(
        "migration.rollback" in error for error in validate_release_evidence(invalid_migration)
    )


def test_manifest_gate_rejects_version_and_artifact_digest_mismatch(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    artifact = tmp_path / "fixture.whl"
    artifact.write_bytes(b"artifact")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    evidence = _valid_release_evidence(head="current-head")
    evidence["artifact"] = {
        "version": "1.2.3",
        "digest": f"sha256:{digest}",
        "source_head": "current-head",
        "path": artifact.name,
    }
    assert (
        _manifest_gate(
            repo_root=tmp_path,
            current_git={"head_sha": "current-head"},
            evidence=evidence,
            evidence_error=None,
        )["status"]
        == "passed"
    )
    mismatched = {**evidence, "release_version": "9.9.9"}
    assert (
        _manifest_gate(
            repo_root=tmp_path,
            current_git={"head_sha": "current-head"},
            evidence=mismatched,
            evidence_error=None,
        )["blocker_class"]
        == "provenance"
    )
    bad_digest = {**evidence, "artifact": {**evidence["artifact"], "digest": "sha256:" + "b" * 64}}
    assert (
        "digest"
        in _manifest_gate(
            repo_root=tmp_path,
            current_git={"head_sha": "current-head"},
            evidence=bad_digest,
            evidence_error=None,
        )["reason"]
    )


def test_migration_evidence_requires_rollback_failure_injection_and_reconciliation() -> None:
    incomplete = _valid_release_evidence()
    incomplete["migration"] = {
        "forward": "passed",
        "rollback": "blocked",
        "failure_injection": "passed",
        "reconciliation": "passed",
    }
    gate = _migration_evidence_gate(
        evidence=incomplete,
        evidence_error=None,
        existing={},
    )
    assert gate["status"] == "blocked"
    complete = {
        **incomplete,
        "migration": {
            key: "passed" for key in ("forward", "rollback", "failure_injection", "reconciliation")
        },
    }
    assert (
        _migration_evidence_gate(evidence=complete, evidence_error=None, existing={})["status"]
        == "passed"
    )


def test_aggregate_coverage_expands_cycles_and_marks_opaque_commands() -> None:
    scripts = {
        "ci": "pnpm run verify && pnpm run lint",
        "verify": "pnpm run ci && pnpm run tests",
        "lint": "pnpm run lint:impl",
        "lint:impl": "eslint .",
        "tests": "pytest -q",
        "opaque": "custom-runner --all",
    }
    coverage = analyze_aggregate_coverage(
        scripts=scripts,
        quality_commands=[
            {"id": "lint", "command": "eslint ."},
            {"id": "tests", "command": "pytest -q"},
        ],
    )
    ci = next(item for item in coverage if item["script"] == "ci")
    assert ci["opaque"] is True
    assert {"lint", "tests"}.issubset(set(ci["covered_gate_ids"]))


def test_publication_security_surface_triggers_review_gate(tmp_path: Path) -> None:
    source = tmp_path / "src" / "public_private_boundary.ts"
    source.parent.mkdir(parents=True)
    source.write_text("export const content = '<p>raw</p>'\n", encoding="utf-8")
    surfaces = detect_security_surfaces(tmp_path, scan={"languages": ["javascript"]})
    assert surfaces["publication_visibility"] is True
    gates = build_agent_review_gates(
        surfaces=surfaces,
        candidates=[],
        settings={"agent_review_gates": True, "minimum_agent_review": "medium"},
    )
    gate = next(item for item in gates if item["id"] == "security_publication_visibility_review")
    assert "authorization" in " ".join(gate["completion_criteria"])
    assert "sanitization" in " ".join(gate["completion_criteria"])


def test_raw_content_sink_triggers_publication_security_surface(tmp_path: Path) -> None:
    source = tmp_path / "src" / "page.tsx"
    source.parent.mkdir(parents=True)
    source.write_text(
        "return <div dangerouslySetInnerHTML={{__html: value}} />\n", encoding="utf-8"
    )

    surfaces = detect_security_surfaces(tmp_path, scan={"languages": ["javascript"]})

    assert surfaces["publication_visibility"] is True


def test_merge_ready_rejects_unresolved_release_readiness() -> None:
    status = compute_lifecycle_status(
        summary_status="passed",
        handoff_status="gates-clean",
        gate_verification={
            "status": "passed",
            "readiness": {
                "status": "blocked",
                "required_gate_ids": list(READINESS_GATE_IDS),
                "unresolved_gate_ids": ["release_acceptance_evidence"],
            },
        },
        audit={"status": "clean"},
        repo_scan={
            "ci_checks": [],
            "provenance": {"head_sha": "current", "branch": "main"},
        },
    )
    assert status == "blocked"
