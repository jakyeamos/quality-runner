from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from quality_runner.fleet.discovery import (
    discover_repositories,
    repository_record_for_root,
    resolve_target_branch,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "qr-tests@example.com")
    _git(root, "config", "user.name", "Quality Runner Tests")
    (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "fixture")


def test_linked_worktrees_group_under_one_identity(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    root = projects / "fixture"
    _repo(root)
    linked = projects / "fixture-linked"
    _git(root, "worktree", "add", "-b", "dev-linked", str(linked))

    records = discover_repositories(projects)

    assert len(records) == 1
    assert records[0]["checkout_count"] == 2
    assert {item["is_registered_worktree"] for item in records[0]["checkouts"]} == {True}
    assert records[0]["primary_path"] == str(root.resolve())


def test_prunable_registered_worktree_is_recorded_without_execution_readiness(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    root = projects / "fixture"
    _repo(root)
    prunable = projects / "fixture-prunable"
    _git(root, "worktree", "add", "-b", "dev-prunable", str(prunable))
    shutil.rmtree(prunable)

    records = discover_repositories(projects)
    checkouts = records[0]["checkouts"]
    missing = next(item for item in checkouts if item["path"] == str(prunable.resolve()))

    assert missing["exists"] is False
    assert missing["prunable"] is True
    assert missing["detached"] is False


def test_nested_git_repositories_are_discovered_as_separate_identities(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    parent = projects / "parent"
    nested = parent / "nested"
    _repo(parent)
    _repo(nested)

    records = discover_repositories(projects)

    assert {item["primary_path"] for item in records} == {
        str(parent.resolve()),
        str(nested.resolve()),
    }


def test_generated_nested_worktrees_are_excluded_from_identity_discovery(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    parent = projects / "parent"
    generated = parent / "data" / "audit-worktrees" / "generated"
    _repo(parent)
    _repo(generated)

    records = discover_repositories(projects)

    assert [item["primary_path"] for item in records] == [str(parent.resolve())]


def test_no_remote_identity_uses_common_git_dir_or_path(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)

    record = repository_record_for_root(root)

    assert record["identity_provenance"]["normalized_origin"] is None
    assert record["identity_key"].startswith("common:")


def test_unattached_dev_branch_uses_clean_checkout_for_disposable_verification(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _repo(root)
    dev_head = _git(root, "rev-parse", "HEAD")
    _git(root, "branch", "main")
    _git(root, "switch", "main")

    target = resolve_target_branch(repository_record_for_root(root))

    assert target["status"] == "ready"
    assert target["branch"] == "dev"
    assert target["head"] == dev_head
    assert target["target_state"]["reason"].startswith("target branch is committed")


def test_only_local_branch_is_an_unambiguous_fallback(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "qr-tests@example.com")
    _git(root, "config", "user.name", "Quality Runner Tests")
    (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "fixture")

    target = resolve_target_branch(repository_record_for_root(root))

    assert target["status"] == "ready"
    assert target["branch"] == "main"
    assert target["source"] == "only_local_branch"


def test_missing_explicit_target_branch_is_blocked() -> None:
    target = resolve_target_branch(
        {"checkouts": [{"local_branches": ["dev"]}]},
        override="main",
    )

    assert target == {
        "branch": "main",
        "source": "explicit_override",
        "status": "blocked",
        "reason": "explicit target branch is not present in a discovered checkout",
        "checkout_id": None,
    }


def test_ambiguous_local_branches_without_fallback_are_blocked(tmp_path: Path) -> None:
    target = resolve_target_branch(
        {
            "primary_path": str(tmp_path),
            "checkouts": [
                {
                    "local_branches": ["feature", "main"],
                    "exists": False,
                }
            ],
        }
    )

    assert target["status"] == "blocked"
    assert target["source"] == "unresolved"
    assert target["reason"].startswith("no dev branch")


def test_target_without_clean_disposable_worktree_host_is_blocked() -> None:
    target = resolve_target_branch(
        {
            "checkouts": [
                {
                    "local_branches": ["dev"],
                    "branch": "feature",
                    "exists": True,
                    "working_tree": True,
                    "dirty": True,
                    "prunable": False,
                    "path": "/tmp/dirty-target-host",
                }
            ]
        }
    )

    assert target == {
        "branch": "dev",
        "source": "default_dev",
        "status": "blocked",
        "reason": "target branch exists but no clean checkout can host disposable verification",
        "checkout_id": None,
    }


def test_documented_main_branch_is_used_when_dev_is_absent(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("main is the canonical branch\n", encoding="utf-8")
    target = resolve_target_branch(
        {
            "primary_path": str(tmp_path),
            "checkouts": [
                {
                    "checkout_id": "main-checkout",
                    "local_branches": ["feature", "main"],
                    "branch": "main",
                    "exists": True,
                    "working_tree": True,
                    "dirty": False,
                    "detached": False,
                    "prunable": False,
                    "stale": False,
                    "head": "abc123",
                    "path": str(tmp_path),
                }
            ],
        }
    )

    assert target["status"] == "ready"
    assert target["branch"] == "main"
    assert target["source"] == "documented_fallback:README.md"


def test_bare_repository_is_a_host_not_an_attached_checkout(tmp_path: Path) -> None:
    bare = tmp_path / "fixture"
    _repo(bare)
    _git(bare, "config", "core.bare", "true")

    record = repository_record_for_root(bare)
    checkout = record["checkouts"][0]
    target = resolve_target_branch(record)

    assert checkout["working_tree"] is False
    assert checkout["branch"] is None
    assert checkout["detached"] is False
    assert target["status"] == "ready"
    assert target["target_state"]["reason"].startswith("target branch is committed")
