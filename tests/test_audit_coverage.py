from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from quality_runner.fleet.audit_coverage import assess_audit_coverage
from quality_runner.fleet.discovery import repository_record_for_root, resolve_target_branch


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "qr-coverage-tests@example.com")
    _git(root, "config", "user.name", "Quality Runner Coverage Tests")
    (root / "README.md").write_text("# Coverage fixture\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "fixture")


def _coverage(root: Path) -> dict[str, Any]:
    repository = repository_record_for_root(root)
    repository["target_branch"] = resolve_target_branch(repository)
    return assess_audit_coverage(repository)


def _feature_commit(root: Path) -> str:
    _git(root, "switch", "-c", "feature")
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(root, "add", "feature.txt")
    _git(root, "commit", "-m", "feature")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "switch", "dev")
    return head


def test_complete_coverage_excludes_branches_contained_in_dev(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    _feature_commit(root)
    _git(root, "merge", "--ff-only", "feature")

    coverage = _coverage(root)

    assert coverage["status"] == "complete"
    assert coverage["comparison_eligible"] is True
    assert coverage["unfolded_branch_count"] == 0
    assert coverage["excluded_ref_counts"] == {"merged": 1}


def test_unique_feature_branch_marks_canonical_findings_incomplete(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    feature_head = _feature_commit(root)

    coverage = _coverage(root)

    assert coverage["status"] == "incomplete_unfolded"
    assert coverage["canonical_findings_valid"] is True
    assert coverage["comparison_eligible"] is False
    assert coverage["publication_ready"] is False
    assert coverage["unfolded_branch_count"] == 1
    assert coverage["unfolded_branches"] == [
        {
            "ref": "feature",
            "head": feature_head,
            "source": "local",
            "aliases": [],
            "kind": "branch",
            "unique_commits": 1,
            "unique_patches": 1,
            "disposition": "unfolded",
            "safe_action": "review_and_fold_branch",
        }
    ]


def test_patch_equivalent_branch_does_not_make_coverage_incomplete(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    feature_head = _feature_commit(root)
    (root / "dev.txt").write_text("dev\n", encoding="utf-8")
    _git(root, "add", "dev.txt")
    _git(root, "commit", "-m", "dev work")
    _git(root, "cherry-pick", feature_head)

    coverage = _coverage(root)

    assert coverage["status"] == "complete"
    assert coverage["excluded_ref_counts"] == {"patch_equivalent": 1}


def test_dirty_target_worktree_is_visible_without_reading_its_diff(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    (root / "README.md").write_text("dirty\n", encoding="utf-8")

    coverage = _coverage(root)

    assert coverage["status"] == "incomplete_unfolded"
    assert coverage["dirty_worktree_count"] == 1
    dirty = coverage["dirty_worktrees"][0]
    assert dirty["branch"] == "dev"
    assert dirty["status_hash"]
    assert "path" not in dirty


def test_detached_unique_commits_are_ambiguous_instead_of_silently_ignored(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _repo(root)
    detached = tmp_path / "detached"
    _git(root, "worktree", "add", "--detach", str(detached), "dev")
    (detached / "detached.txt").write_text("detached\n", encoding="utf-8")
    _git(detached, "add", "detached.txt")
    _git(detached, "commit", "-m", "detached work")

    coverage = _coverage(root)

    assert coverage["status"] == "blocked_ambiguous"
    assert coverage["ambiguous_item_count"] == 1
    assert coverage["ambiguous_items"][0]["kind"] == "detached_head"
    assert coverage["ambiguous_items"][0]["unique_commits"] == 1


def test_remote_tracking_only_work_is_flagged(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    feature_head = _feature_commit(root)
    _git(root, "update-ref", "refs/remotes/origin/remote-feature", feature_head)
    _git(root, "branch", "-D", "feature")

    coverage = _coverage(root)

    assert coverage["status"] == "incomplete_unfolded"
    assert coverage["unfolded_branches"][0]["ref"] == "origin/remote-feature"
    assert coverage["unfolded_branches"][0]["source"] == "remote_tracking"


def test_reviewed_custody_disposition_accounts_for_a_live_branch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    feature_head = _feature_commit(root)
    repository = repository_record_for_root(root)
    repository["target_branch"] = resolve_target_branch(repository)

    coverage = assess_audit_coverage(repository)
    covered = assess_audit_coverage(
        repository,
        custody_dispositions=[
            {
                "kind": "branch",
                "ref": "feature",
                "head": feature_head,
                "target_head": coverage["canonical_head"],
                "disposition": "semantic_superseded",
                "reason": "Target contains the reviewed behavior at a newer canonical head.",
                "evidence": {"reviewed_head": feature_head},
                "reviewed_at": "2026-08-25T00:00:00Z",
            }
        ],
    )

    assert covered["status"] == "complete"
    assert covered["comparison_eligible"] is True
    assert covered["observed_unfolded_branch_count"] == 1
    assert covered["unfolded_branch_count"] == 0
    assert covered["custody_dispositioned_count"] == 1
    assert covered["custody_dispositioned_items"][0]["custody_disposition"]["type"] == (
        "semantic_superseded"
    )


def test_unmatched_custody_disposition_cannot_hide_a_gap(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    _feature_commit(root)
    repository = repository_record_for_root(root)
    repository["target_branch"] = resolve_target_branch(repository)

    coverage = assess_audit_coverage(
        repository,
        custody_dispositions=[
            {
                "kind": "branch",
                "ref": "not-live",
                "head": "0" * 40,
                "disposition": "semantic_superseded",
                "reason": "This must not match a live branch.",
                "evidence": {"reviewed": True},
            }
        ],
    )

    assert coverage["status"] == "blocked_ambiguous"
    assert coverage["unfolded_branch_count"] == 1
    assert coverage["custody_disposition_errors"][0]["safe_action"] == (
        "refresh_the_manifest_against_live_state"
    )
