from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from quality_runner.model_audit.reporting import fleet_report, report
from quality_runner.model_audit.workflow import prepare, record, verify


def write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value))
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "app.py").write_text("def divide(a, b):\n    return a / b\n")
    subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    return root


def prepare_run(
    repo: Path,
    run_id: str,
    *,
    baseline: str | None = None,
    reuse: str | None = None,
    model: str = "model-a",
    harness: str = "fixture/1",
) -> dict:
    profile = {
        "schema": "quality-runner-model-audit-profile/v1",
        "id": "service",
        "revision": "1",
        "purpose": "Arithmetic service",
        "constraints": ["Preserve the public API"],
        "criteria": [{"id": "correctness", "prompt": "Check boundary inputs and failures"}],
        "include_paths": ["app.py"],
        "exclude_paths": [],
    }
    reviewer = {
        "reviewer_id": f"{model}-{run_id}",
        "model": model,
        "provider": "fixture",
        "effort": "high",
        "harness": harness,
        "tools": ["read"],
        "budget": {"seconds": 60, "max_findings": 4},
    }
    return prepare(
        repo,
        run_id,
        profile=profile,
        reviewer=reviewer,
        baseline_run_id=baseline,
        reuse_inputs_from=reuse,
    )


def complete(repo: Path, run_id: str, fingerprints: tuple[str, ...] = ("divide-zero",)) -> dict:
    directory = repo / ".quality-runner" / "runs" / run_id
    response = json.loads((directory / "review-adapter-response.template.json").read_text())
    manifest = json.loads((directory / "model-audit-manifest.json").read_text())
    response["adapter"]["name"] = manifest["reviewer"]["reviewer_id"]
    response["completed_at"] = "2026-11-01T21:00:00Z"
    response["findings"] = [
        {
            "id": key,
            "fingerprint": key,
            "severity": "high",
            "classification": "confirmed",
            "confidence": "high",
            "summary": "Zero divisor fails",
            "why_it_matters": "Requests fail",
            "location": ["app.py:2"],
            "evidence": ["return a / b"],
            "recommended_fix": "Specify zero behavior",
            "agent_prompt": "Review zero behavior",
            "human_confirmation_required": False,
            "status": "open",
        }
        for key in fingerprints
    ]
    return record(repo, run_id, write(directory / "response.json", response))


def adjudicate(
    repo: Path,
    run_id: str,
    fingerprint: str = "divide-zero",
    *,
    key: str = "arithmetic/zero",
    verdict: str = "verified",
    verifier: str = "independent-test",
) -> dict:
    directory = repo / ".quality-runner" / "runs" / run_id
    result = json.loads((directory / "model-audit-result.json").read_text())
    evidence = directory / f"proof-{fingerprint}-{verdict}.txt"
    evidence.write_text("divide(1, 0) raises ZeroDivisionError; expected documented rejection")
    receipt = {
        "schema": "quality-runner-model-audit-verification/v1",
        "run_id": run_id,
        "manifest_digest": result["manifest_digest"],
        "response_digest": result["response_digest"],
        "verifier_id": verifier,
        "independent": True,
        "findings": [
            {
                "fingerprint": fingerprint,
                "canonical_key": key,
                "criterion_id": "correctness",
                "verdict": verdict,
                "method": "Reproduce boundary input in a separate process",
                "evidence": [
                    {
                        "path": evidence.name,
                        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                    }
                ],
            }
        ],
    }
    return verify(repo, run_id, write(directory / f"verify-{fingerprint}-{verdict}.json", receipt))


def test_model_claim_requires_verification_and_omissions_survive_multiple_runs(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first")
    assert report(repo, "first")["counts"]["unverified"] == 1
    adjudicate(repo, "first")
    assert report(repo, "first")["counts"]["newly_verified"] == 1
    for current, previous in [("second", "first"), ("third", "second")]:
        prepare_run(repo, current, baseline=previous, reuse="first", model="model-b")
        complete(repo, current, ())
    result = report(repo, "third")
    assert result["comparison"]["kind"] == "fixed-snapshot"
    assert result["counts"]["not_reobserved"] == 1
    assert result["findings"][0]["last_verified_run_id"] == "first"
    assert result["findings"][0]["resolved"] is False


def test_canonical_identity_matches_different_model_wording(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first")
    adjudicate(repo, "first")
    prepare_run(repo, "second", baseline="first", reuse="first", model="model-b")
    complete(repo, "second", ("different-wording", "unproven"))
    adjudicate(repo, "second", "different-wording")
    result = report(repo, "second")
    assert result["counts"]["known"] == 1
    assert result["counts"]["unverified"] == 1
    assert result["comparison"]["controlled_model_comparison"] is True


def test_changed_code_is_rolling_and_changed_harness_is_confounded(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first", ())
    (repo / "app.py").write_text("def divide(a, b):\n    return None if b == 0 else a / b\n")
    prepare_run(repo, "second", baseline="first")
    complete(repo, "second", ())
    result = report(repo, "second")
    assert result["comparison"]["kind"] == "rolling-code"
    assert result["comparison"]["controlled_model_comparison"] is False
    prepare_run(repo, "third", baseline="first", reuse="first", harness="fixture/2")
    complete(repo, "third", ())
    comparison = report(repo, "third")["comparison"]
    assert comparison["kind"] == "fixed-snapshot"
    assert comparison["confounders"] == ["harness changed"]
    assert comparison["controlled_model_comparison"] is False


def test_self_verification_and_tampered_evidence_are_rejected(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first")
    with pytest.raises(ValueError, match="independent"):
        adjudicate(repo, "first", verifier="model-a-first")
    adjudicate(repo, "first")
    (repo / ".quality-runner/runs/first/proof-divide-zero-verified.txt").write_text("changed")
    with pytest.raises(ValueError, match="evidence digest"):
        report(repo, "first")


def test_snapshot_tampering_and_replay_are_rejected(repo: Path) -> None:
    prepare_run(repo, "first")
    (repo / ".quality-runner/runs/first/source/app.py").write_text("changed")
    with pytest.raises(ValueError, match="snapshot"):
        complete(repo, "first")
    with pytest.raises(ValueError, match="exists"):
        prepare_run(repo, "first")


def test_unexpected_special_file_invalidates_retained_snapshot(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first", ())
    os.mkfifo(repo / ".quality-runner/runs/first/source/unexpected-pipe")
    with pytest.raises(ValueError, match="unexpected or missing files"):
        report(repo, "first")


def test_conflicting_verification_is_disputed_not_silently_replaced(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first")
    adjudicate(repo, "first")
    adjudicate(repo, "first", verdict="disputed", verifier="another-reviewer")
    result = report(repo, "first")
    assert result["counts"]["disputed"] == 1
    assert result["counts"]["newly_verified"] == 0


def test_fleet_reports_missing_runs_as_partial_and_does_not_mutate(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first", ())
    selection = {
        "schema": "quality-runner-model-audit-selection/v1",
        "repositories": [
            {"repo_path": str(repo), "run_id": "first"},
            {"repo_path": str(repo.parent / "missing"), "run_id": "absent"},
        ],
    }
    before = sorted(str(p) for p in repo.rglob("*"))
    result = fleet_report(selection)
    assert result["status"] == "partial"
    assert result["coverage"] == {"selected": 2, "reported": 1, "unavailable": 1}
    assert sorted(str(p) for p in repo.rglob("*")) == before


def test_cli_mcp_and_retention_preserve_audit_evidence(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from quality_runner.artifacts import cleanup_artifacts
    from quality_runner.cli import main
    from quality_runner.mcp import call_tool, list_tools

    prepare_run(repo, "old-audit")
    complete(repo, "old-audit", ())
    assert main(["model-audit", "report", str(repo), "--run-id", "old-audit", "--json"]) == 0
    cli = json.loads(capsys.readouterr().out)
    mcp = call_tool(
        "quality_runner_model_audit",
        {"action": "report", "repo_path": str(repo), "run_id": "old-audit"},
    )
    assert json.loads(mcp["content"][0]["text"]) == cli
    assert any(tool["name"] == "quality_runner_model_audit" for tool in list_tools())
    for index in range(5):
        (repo / ".quality-runner/runs" / f"newer-{index}").mkdir()
    result = cleanup_artifacts(repo, config={"artifacts": {"retention_runs": 1}}, apply=False)
    assert "old-audit" in result["preserved_run_ids"]
    assert "old-audit" not in result["would_delete_run_ids"]


def test_symlink_inputs_and_evidence_cannot_escape_the_run(repo: Path) -> None:
    original = repo.parent / "private.txt"
    original.write_text("private fixture")
    (repo / "app.py").unlink()
    (repo / "app.py").symlink_to(original)
    with pytest.raises(OSError):
        prepare_run(repo, "symlink")
    assert original.read_text() == "private fixture"


def test_prior_review_content_is_not_in_new_reviewer_packet(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first", ("secret-prior-finding",))
    prepare_run(repo, "second", baseline="first", reuse="first", model="model-b")
    packet = (repo / ".quality-runner/runs/second/review-agent-packet.md").read_text()
    assert "secret-prior-finding" not in packet
    assert (repo / ".quality-runner/runs/second/source/app.py").read_bytes() == (
        repo / "app.py"
    ).read_bytes()


def test_retained_response_and_cross_run_receipts_are_bound(repo: Path) -> None:
    prepare_run(repo, "first")
    complete(repo, "first")
    adjudicate(repo, "first")
    prepare_run(repo, "second", baseline="first", reuse="first")
    complete(repo, "second")
    first = repo / ".quality-runner/runs/first"
    second = repo / ".quality-runner/runs/second"
    copied = write(
        second / "cross-run.json",
        json.loads((first / "verify-divide-zero-verified.json").read_text()),
    )
    with pytest.raises(ValueError, match="exact run"):
        verify(repo, "second", copied)
    response_path = first / "review-adapter-response.json"
    response = json.loads(response_path.read_text())
    response["findings"][0]["summary"] = "Tampered summary"
    write(response_path, response)
    with pytest.raises(ValueError, match="bound Fresh Review"):
        report(repo, "first")


def test_profile_schema_run_manifest_and_fleet_cli_partial(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from quality_runner.cli import main

    prepare_run(repo, "first")
    complete(repo, "first", ())
    directory = repo / ".quality-runner/runs/first"
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "quality_runner/schemas/model-audit-input.schema.json").read_text())
    manifest = json.loads((directory / "model-audit-manifest.json").read_text())
    for name in ("profile", "reviewer"):
        definition = schema["$defs"][name]
        assert set(manifest[name]) == set(definition["required"])
        assert set(manifest[name]) == set(definition["properties"])
        assert definition["additionalProperties"] is False
    generic = json.loads((directory / "run-manifest.json").read_text())
    assert generic["mode"] == "model-audit"
    assert generic["implementation_allowed"] is False
    selection = write(
        repo.parent / "selection.json",
        {
            "schema": "quality-runner-model-audit-selection/v1",
            "repositories": [{"repo_path": str(repo), "run_id": "missing"}],
        },
    )
    assert main(["model-audit", "fleet", "--selection", str(selection), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["coverage"]["unavailable"] == 1
