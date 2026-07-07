from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from quality_runner.worktree_verify import gate_worktree_session


def _init_git_repo(repo: Path, *, filename: str = "tracked.txt", contents: str = "original\n") -> None:
    tracked = repo / filename
    tracked.write_text(contents, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", filename], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=quality-runner@example.com",
            "-c",
            "user.name=Quality Runner",
            "commit",
            "-m",
            "Initial commit",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _mutating_gate_toml(command: str) -> str:
    return "\n".join(
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
            "",
        ]
    )


def test_disposable_worktree_runs_mutating_gate_without_touching_dirty_source(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    _init_git_repo(tmp_path)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("dirty working copy\n", encoding="utf-8")
    command = (
        f"{sys.executable} -c "
        "\"from pathlib import Path; Path('tracked.txt').write_text('mutated\\\\n')\""
    )
    (tmp_path / ".quality-runner.toml").write_text(_mutating_gate_toml(command), encoding="utf-8")

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="disposable-mutating",
        read_only_gates=True,
        worktree_mode="disposable",
        allow_dirty_worktree_verify=True,
    )
    verification = json.loads(Path(payload["artifact_paths"]["gate_verification_json"]).read_text())

    assert tracked.read_text(encoding="utf-8") == "dirty working copy\n"
    assert verification["verification_context"]["worktree_mode"] == "disposable"
    assert verification["verification_context"]["mutations_isolated"] is True
    assert verification["verification_context"]["dirty_source_worktree"] is True
    assert not (tmp_path / ".quality-runner" / "worktrees" / "disposable-mutating").exists()
    gate = verification["gates"][0]
    assert gate["status"] == "passed"
    assert gate.get("skip_type") != "mutating-gate-not-run"


def test_disposable_worktree_refuses_dirty_repo_without_override(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    _init_git_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        _mutating_gate_toml(f"{sys.executable} -c \"print('ok')\""),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="clean git worktree"):
        verify_gates_payload(
            repo_root=tmp_path,
            run_id="dirty-refused",
            worktree_mode="disposable",
        )


def test_disposable_worktree_requires_git_repo(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.0.1"\n')

    with pytest.raises(ValueError, match="requires a git repository"):
        verify_gates_payload(
            repo_root=tmp_path,
            run_id="not-git",
            worktree_mode="disposable",
        )


def test_gate_worktree_session_cleans_up_on_failure(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    worktree_path = tmp_path / ".quality-runner" / "worktrees" / "cleanup-run"

    with pytest.raises(RuntimeError, match="boom"):
        with gate_worktree_session(
            repo_root=tmp_path,
            run_id="cleanup-run",
            worktree_mode="disposable",
        ) as session:
            assert session.execution_root == worktree_path
            assert worktree_path.exists()
            raise RuntimeError("boom")

    assert not worktree_path.exists()


def test_in_place_verification_context_is_recorded(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    _init_git_repo(tmp_path)
    (tmp_path / ".quality-runner.toml").write_text(
        _mutating_gate_toml(f"{sys.executable} -c \"print('ok')\""),
        encoding="utf-8",
    )

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="in-place-context",
        worktree_mode="in-place",
    )
    verification = json.loads(Path(payload["artifact_paths"]["gate_verification_json"]).read_text())

    assert verification["verification_context"]["worktree_mode"] == "in-place"
    assert verification["verification_context"]["mutations_isolated"] is False
