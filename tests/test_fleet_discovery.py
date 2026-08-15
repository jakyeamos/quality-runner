from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from quality_runner.fleet.discovery import (
    discover_repositories,
    load_fleet_policy,
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


def _add_remote_commit(root: Path, tmp_path: Path) -> tuple[str, str]:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "dev")
    producer = tmp_path / "producer"
    subprocess.run(
        ["git", "clone", "--branch", "dev", str(remote), str(producer)],
        check=True,
        capture_output=True,
    )
    _git(producer, "config", "user.email", "qr-tests@example.com")
    _git(producer, "config", "user.name", "Quality Runner Tests")
    (producer / "remote.txt").write_text("remote\n", encoding="utf-8")
    _git(producer, "add", "remote.txt")
    _git(producer, "commit", "-m", "remote commit")
    _git(producer, "push", "origin", "dev")
    local_head = _git(root, "rev-parse", "dev")
    _git(root, "fetch", "origin")
    return local_head, _git(root, "rev-parse", "origin/dev")


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


def test_projects_root_fleet_policy_excludes_paths_and_descendants(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    included = projects / "included"
    excluded = projects / "test-fixtures" / "fixture"
    harvested = projects / "tmcp" / ".tmcp" / "harvest-sources" / "taste-skill"
    _repo(included)
    _repo(excluded)
    _repo(harvested)
    policy_path = projects / ".quality-runner" / "fleet.json"
    policy_path.parent.mkdir()
    policy_path.write_text(
        '{"schema":"quality-runner-fleet-policy-v0.1","exclude_paths":'
        '["test-fixtures","tmcp/.tmcp/harvest-sources/taste-skill"]}',
        encoding="utf-8",
    )

    policy = load_fleet_policy(projects)
    records = discover_repositories(projects)

    assert policy["exclude_paths"] == [
        "test-fixtures",
        "tmcp/.tmcp/harvest-sources/taste-skill",
    ]
    assert [item["primary_path"] for item in records] == [str(included.resolve())]


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


def test_target_prefers_checkout_at_target_head_over_preserved_feature_checkout(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _repo(root)
    dev_head = _git(root, "rev-parse", "dev")
    _git(root, "branch", "feature")
    _git(root, "switch", "feature")
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(root, "add", "feature.txt")
    _git(root, "commit", "-m", "feature")

    target_checkout = tmp_path / "target-checkout"
    _git(root, "worktree", "add", "--detach", str(target_checkout), "dev")
    try:
        repository = repository_record_for_root(root)
        target = resolve_target_branch(repository)
        checkout_by_path = {
            Path(item["path"]).resolve(): item
            for item in repository["checkouts"]
            if isinstance(item.get("path"), str)
        }

        assert target["head"] == dev_head
        assert target["checkout_id"] == checkout_by_path[target_checkout.resolve()]["checkout_id"]
    finally:
        _git(root, "worktree", "remove", str(target_checkout))


def test_target_behind_upstream_reports_exact_fast_forward_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    local_head, upstream_head = _add_remote_commit(root, tmp_path)

    target = resolve_target_branch(repository_record_for_root(root))

    assert target["status"] == "stale"
    assert target["target_state"] == {
        "local_head": local_head,
        "upstream": "origin/dev",
        "upstream_head": upstream_head,
        "ahead": 0,
        "behind": 1,
        "safe_action": "fast_forward_local_target",
        "status": "stale",
        "reason": "target branch is behind its configured upstream",
    }


def test_diverged_target_is_blocked_and_not_offered_fast_forward(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    _add_remote_commit(root, tmp_path)
    (root / "local.txt").write_text("local\n", encoding="utf-8")
    _git(root, "add", "local.txt")
    _git(root, "commit", "-m", "local commit")

    target = resolve_target_branch(repository_record_for_root(root))

    assert target["status"] == "blocked"
    assert target["target_state"]["ahead"] == 1
    assert target["target_state"]["behind"] == 1
    assert target["target_state"]["safe_action"] == "reconcile_diverged_target"


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


def test_dirty_checkout_can_host_committed_target_in_disposable_worktree(tmp_path: Path) -> None:
    root = tmp_path / "dirty-target-host"
    _repo(root)
    dev_head = _git(root, "rev-parse", "HEAD")
    _git(root, "branch", "feature")
    _git(root, "switch", "feature")
    (root / "uncommitted.txt").write_text("preserve me\n", encoding="utf-8")

    target = resolve_target_branch(repository_record_for_root(root))

    assert target["status"] == "ready"
    assert target["branch"] == "dev"
    assert target["head"] == dev_head
    assert "fingerprinted checkout" in target["reason"]


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
