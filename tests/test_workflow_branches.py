from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_support.quality_runner_fixtures import write_js_fixture


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_commit_all(repo_root: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
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
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return _git(repo_root, "rev-parse", "HEAD")


def _write_branch_marker(repo_root: Path, marker: str) -> None:
    (repo_root / f"{marker}.txt").write_text(f"{marker}\n", encoding="utf-8")


def test_run_payload_warns_when_checked_out_branch_is_not_main_or_most_advanced(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)
    _git(tmp_path, "init", "-b", "main")
    _git_commit_all(tmp_path, "Initial commit")
    _git(tmp_path, "switch", "-c", "old-feature")
    _write_branch_marker(tmp_path, "old-feature")
    _git_commit_all(tmp_path, "Old feature")
    _git(tmp_path, "switch", "main")
    _git(tmp_path, "switch", "-c", "advanced-feature")
    _write_branch_marker(tmp_path, "advanced-one")
    _git_commit_all(tmp_path, "Advanced one")
    _write_branch_marker(tmp_path, "advanced-two")
    _git_commit_all(tmp_path, "Advanced two")
    _git(tmp_path, "switch", "old-feature")

    payload = run_payload(repo_root=tmp_path, run_id="branch-warning-run", profile="default")
    repo_scan = json.loads(Path(payload["artifact_paths"]["repo_scan_json"]).read_text())

    assert _git(tmp_path, "branch", "--show-current") == "old-feature"
    assert {
        "code": "checked_out_branch_not_main_or_most_advanced",
        "message": (
            "Current branch 'old-feature' is neither main nor the local most-advanced branch "
            "'advanced-feature'. Re-run with --checkout-most-advanced-branch to scan "
            "'advanced-feature'."
        ),
        "path": ".",
    } in repo_scan["warnings"]
    assert repo_scan["warnings"] == payload["warnings"]


def test_run_payload_does_not_warn_when_dev_matches_main_head(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)
    _git(tmp_path, "init", "-b", "main")
    _git_commit_all(tmp_path, "Initial commit")
    _git(tmp_path, "switch", "-c", "dev")

    payload = run_payload(repo_root=tmp_path, run_id="matching-dev-run", profile="default")
    repo_scan = json.loads(Path(payload["artifact_paths"]["repo_scan_json"]).read_text())

    assert _git(tmp_path, "branch", "--show-current") == "dev"
    assert _git(tmp_path, "rev-parse", "dev") == _git(tmp_path, "rev-parse", "main")
    assert "checked_out_branch_not_main_or_most_advanced" not in {
        warning["code"] for warning in repo_scan["warnings"]
    }
    assert repo_scan["warnings"] == payload["warnings"]


def test_run_payload_can_checkout_most_advanced_branch_before_scanning(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)
    _git(tmp_path, "init", "-b", "main")
    _git_commit_all(tmp_path, "Initial commit")
    _git(tmp_path, "switch", "-c", "old-feature")
    _write_branch_marker(tmp_path, "old-feature")
    _git_commit_all(tmp_path, "Old feature")
    _git(tmp_path, "switch", "main")
    _git(tmp_path, "switch", "-c", "advanced-feature")
    _write_branch_marker(tmp_path, "advanced-one")
    _git_commit_all(tmp_path, "Advanced one")
    _write_branch_marker(tmp_path, "advanced-two")
    _git_commit_all(tmp_path, "Advanced two")
    _git(tmp_path, "switch", "old-feature")

    payload = run_payload(
        repo_root=tmp_path,
        run_id="branch-checkout-run",
        profile="default",
        checkout_most_advanced_branch=True,
    )
    manifest = json.loads(Path(payload["artifact_paths"]["run_manifest_json"]).read_text())
    repo_scan = json.loads(Path(payload["artifact_paths"]["repo_scan_json"]).read_text())

    assert _git(tmp_path, "branch", "--show-current") == "advanced-feature"
    assert manifest["git"]["branch"] == "advanced-feature"
    assert "advanced-two.txt" in {path.name for path in tmp_path.iterdir()}
    assert "checked_out_branch_not_main_or_most_advanced" not in {
        warning["code"] for warning in repo_scan["warnings"]
    }


def test_run_payload_refuses_to_checkout_most_advanced_branch_with_dirty_worktree(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)
    _git(tmp_path, "init", "-b", "main")
    _git_commit_all(tmp_path, "Initial commit")
    _git(tmp_path, "switch", "-c", "old-feature")
    _write_branch_marker(tmp_path, "old-feature")
    _git_commit_all(tmp_path, "Old feature")
    _git(tmp_path, "switch", "main")
    _git(tmp_path, "switch", "-c", "advanced-feature")
    _write_branch_marker(tmp_path, "advanced-one")
    _git_commit_all(tmp_path, "Advanced one")
    _write_branch_marker(tmp_path, "advanced-two")
    _git_commit_all(tmp_path, "Advanced two")
    _git(tmp_path, "switch", "old-feature")
    (tmp_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    try:
        run_payload(
            repo_root=tmp_path,
            run_id="dirty-branch-checkout-run",
            profile="default",
            checkout_most_advanced_branch=True,
        )
    except ValueError as error:
        assert "requires a clean git worktree" in str(error)
    else:
        raise AssertionError("expected dirty branch checkout to fail")
