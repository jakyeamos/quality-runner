from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from quality_runner.application.gate_verification import run_gate_verification
from quality_runner.core.verification_contracts import GateExecutionPolicy, VerificationRequest
from quality_runner.intent import build_intent_packet
from quality_runner.refresh_timeout import workflow_deadline
from quality_runner.workflow import verify_gates_payload


def test_verification_service_preserves_v1_intent_artifact_projection(tmp_path: Path) -> None:
    run_id = "intent-projection"
    result = run_gate_verification(
        VerificationRequest(
            repo_root=tmp_path,
            run_id=run_id,
            profile=None,
            ci_status_json=None,
            checkout_most_advanced_branch=False,
            policy=GateExecutionPolicy(
                timeout_seconds=120,
                execute_discovered_gates=False,
                read_only_gates=False,
                allow_mutating_gates=False,
                worktree_mode="in-place",
                allow_dirty_worktree_verify=False,
            ),
            skill_review_report=None,
            intent=build_intent_packet(
                run_id=run_id,
                goal="Preserve the legacy verification artifact projection.",
                source="test",
                supplied_by="test",
            ),
        )
    )

    handoff = _json(result.artifact_paths["agent_handoff_json"])
    manifest = _json(result.artifact_paths["run_manifest_json"])
    context = _json(result.artifact_paths["remediation_context_json"])
    handoff_artifact_paths = _object(handoff["artifact_paths"])
    manifest_artifact_paths = _object(manifest["artifact_paths"])

    assert "intent_json" in result.artifact_paths
    assert context["schema"] == "quality-runner-remediation-context-v0.1"
    assert handoff["remediation_context"]["artifact_path"].endswith("remediation-context.json")
    assert "intent_json" in manifest_artifact_paths
    assert "intent_json" not in handoff_artifact_paths


def test_disposable_gate_execution_cannot_leak_untracked_source_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    command = (
        f"{sys.executable} -c "
        "\"from pathlib import Path; Path('untracked-from-gate.txt').write_text('created')\""
    )
    _write_gate_config(tmp_path, command=command, mutating_risk="safe")
    _commit_all(tmp_path, "Add gate fixture")

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="untracked-isolation",
        execute_discovered_gates=True,
        worktree_mode="disposable",
    )
    verification = _json(payload["artifact_paths"]["gate_verification_json"])
    gates = verification["gates"]
    assert isinstance(gates, list)
    assert gates
    first_gate = _object(gates[0])

    assert first_gate["status"] == "passed"
    assert not (tmp_path / "untracked-from-gate.txt").exists()
    assert not (tmp_path / ".quality-runner" / "worktrees" / "untracked-isolation").exists()


def test_interrupted_disposable_verification_cleans_worktree_and_registration(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    command = f'{sys.executable} -c "import time; time.sleep(10)"'
    _write_gate_config(tmp_path, command=command, mutating_risk="safe")
    _commit_all(tmp_path, "Add slow gate fixture")
    worktree_path = tmp_path / ".quality-runner" / "worktrees" / "interrupted-disposable"

    with pytest.raises(TimeoutError, match="M3 test deadline"):
        with workflow_deadline(seconds=1, reason="M3 test deadline"):
            verify_gates_payload(
                repo_root=tmp_path,
                run_id="interrupted-disposable",
                execute_discovered_gates=True,
                worktree_mode="disposable",
            )

    registrations = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert not worktree_path.exists()
    assert str(worktree_path) not in registrations
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "original\n"


def _init_git_repo(repo: Path) -> None:
    (repo / "tracked.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    _commit_all(repo, "Initial commit")


def _write_gate_config(repo: Path, *, command: str, mutating_risk: str) -> None:
    (repo / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["tests"]',
                "",
                "[[quality_runner.gates]]",
                'id = "tests"',
                f"command = {json.dumps(command)}",
                'ecosystem = "python"',
                'source = "local policy"',
                'owner = "qa"',
                "required = true",
                'severity = "blocker"',
                f'mutating_risk = "{mutating_risk}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _commit_all(repo: Path, message: str) -> None:
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
            message,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _json(path: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _object(payload)


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)
