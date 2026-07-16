from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from quality_runner.workflow import inspect_payload
from quality_runner.workflow_verify import verify_gates_payload


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _release_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    gate_lines: list[str] = []
    for gate_id in (
        "formatter",
        "lint",
        "typecheck",
        "tests",
        "build",
        "dead_code",
        "runtime_smoke",
        "pre_pr",
        "pre_cr",
        "package_consumer_smoke",
    ):
        gate_lines.extend(
            [
                "",
                "[[quality_runner.gates]]",
                f'id = "{gate_id}"',
                'command = "true"',
                'ecosystem = "shell"',
                'source = "fixture"',
                'owner = "release"',
                "required = true",
                'severity = "blocker"',
            ]
        )
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "release-fixture"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    (repo / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'default_profile = "release"',
                "",
                "[quality_runner.readiness]",
                'evidence_file = "release-evidence.json"',
                *gate_lines,
            ]
        ),
        encoding="utf-8",
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Quality Runner Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    head = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    (repo / "ci-status.json").write_text(
        json.dumps(
            {
                "provenance": {
                    "head_sha": head,
                    "ref": branch,
                    "workflow_run_id": "workflow-1",
                    "captured_at": datetime.now(UTC).isoformat(),
                },
                "checks": [
                    {
                        "name": "Quality / Release",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (repo / "release-evidence.json").write_text(
        json.dumps(
            {
                "schema": "quality-runner-release-evidence-v0.1",
                "target": {"head_sha": head, "ref": branch},
                "release_version": "1.2.3",
                "owner": {"name": "Release Owner", "role": "maintainer"},
                "acceptance": [{"id": "release", "status": "accepted", "evidence": ["fixture"]}],
                "artifact": {
                    "version": "1.2.3",
                    "digest": "sha256:" + "a" * 64,
                    "source_head": head,
                },
            }
        ),
        encoding="utf-8",
    )
    return repo, branch


def test_release_profile_reaches_readiness_pass(tmp_path: Path) -> None:
    repo, _ = _release_repo(tmp_path)
    payload = verify_gates_payload(
        repo_root=repo,
        run_id="release-pass",
        profile="release",
        ci_status_json=repo / "ci-status.json",
        read_only_gates=True,
        worktree_mode="disposable",
        allow_dirty_worktree_verify=True,
    )
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text(encoding="utf-8")
    )
    assert verification["readiness"]["status"] == "passed"
    assert verification["status"] == "passed"


def test_release_profile_blocks_stale_ci_evidence(tmp_path: Path) -> None:
    repo, branch = _release_repo(tmp_path)
    ci_status = json.loads((repo / "ci-status.json").read_text(encoding="utf-8"))
    ci_status["provenance"]["head_sha"] = "0" * 40
    (repo / "ci-status.json").write_text(json.dumps(ci_status), encoding="utf-8")
    payload = verify_gates_payload(
        repo_root=repo,
        run_id="release-stale-ci",
        profile="release",
        ci_status_json=repo / "ci-status.json",
        read_only_gates=True,
        worktree_mode="in-place",
    )
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text(encoding="utf-8")
    )
    assert branch
    assert verification["status"] == "blocked"
    assert "evidence_provenance" in verification["readiness"]["unresolved_gate_ids"]


def test_readiness_evidence_override_is_reflected_in_inspect_artifact(tmp_path: Path) -> None:
    repo, _ = _release_repo(tmp_path)
    override = repo / "custom-release-evidence.json"

    payload = inspect_payload(
        repo_root=repo,
        run_id="release-inspect-override",
        profile="release",
        readiness_evidence_file=override,
    )
    capability_matrix = json.loads(
        Path(payload["artifact_paths"]["capability_matrix_json"]).read_text(encoding="utf-8")
    )

    assert capability_matrix["readiness"]["evidence_file"] == str(override)
