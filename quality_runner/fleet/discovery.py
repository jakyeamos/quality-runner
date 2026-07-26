from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from quality_runner.fleet.contracts import (
    FLEET_CHECKOUT_SCHEMA,
    digest,
    relative_path,
    stable_id,
)

EXCLUDED_DIRECTORIES = {
    ".git",
    ".quality-runner",
    ".venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    ".pnpm-store",
    "node_modules",
    "vendor",
    "build",
    "dist",
    "coverage",
    "DerivedData",
}


def discover_repositories(projects_root: Path) -> list[dict[str, Any]]:
    root = projects_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"projects root is not a directory: {root}")
    candidates = _discover_roots(root)
    grouped: dict[str, list[Path]] = {}
    for candidate in candidates:
        identity_key = _identity_key(candidate)
        grouped.setdefault(identity_key, []).append(candidate)

    records: list[dict[str, Any]] = []
    for identity_key, roots in sorted(grouped.items()):
        checkout_paths: dict[str, Path] = {}
        for candidate in sorted(set(roots)):
            checkout_paths[str(candidate)] = candidate
            for worktree in _registered_worktrees(candidate):
                path = worktree.get("path")
                if isinstance(path, str) and path:
                    checkout_paths[str(Path(path).expanduser().resolve())] = (
                        Path(path).expanduser().resolve()
                    )
        sorted_paths = sorted(checkout_paths.values(), key=lambda path: path.as_posix())
        primary_path = min(roots, key=lambda path: path.as_posix())
        origin = _normalized_origin(primary_path)
        common_git_dir = _common_git_dir(primary_path)
        repo_id = stable_id("repo", identity_key)
        checkouts = [
            _checkout_record(
                repo_id=repo_id,
                path=path,
                primary=path == primary_path,
                projects_root=root,
            )
            for path in sorted_paths
        ]
        records.append(
            {
                "schema": "quality-runner-fleet-repository-v0.1",
                "repo_id": repo_id,
                "identity_key": identity_key,
                "identity_provenance": {
                    "normalized_origin": origin,
                    "common_git_dir": common_git_dir,
                    "grouping": "origin" if origin else "common_git_dir_or_path",
                },
                "primary_path": str(primary_path),
                "repository_class": _repository_class(primary_path, origin),
                "checkouts": checkouts,
                "checkout_count": len(checkouts),
                "repository_provenance": digest(
                    {
                        "identity_key": identity_key,
                        "primary_path": str(primary_path),
                        "checkouts": [checkout["checkout_id"] for checkout in checkouts],
                    }
                ),
            }
        )
    return records


def repository_record_for_root(root: Path) -> dict[str, Any]:
    resolved = root.expanduser().resolve()
    if not (resolved / ".git").exists():
        raise ValueError(f"repository root is not a git checkout: {resolved}")
    identity_key = _identity_key(resolved)
    origin = _normalized_origin(resolved)
    repo_id = stable_id("repo", identity_key)
    checkout = _checkout_record(
        repo_id=repo_id,
        path=resolved,
        primary=True,
        projects_root=resolved.parent,
    )
    return {
        "schema": "quality-runner-fleet-repository-v0.1",
        "repo_id": repo_id,
        "identity_key": identity_key,
        "identity_provenance": {
            "normalized_origin": origin,
            "common_git_dir": _common_git_dir(resolved),
            "grouping": "origin" if origin else "common_git_dir_or_path",
        },
        "primary_path": str(resolved),
        "repository_class": _repository_class(resolved, origin),
        "checkouts": [checkout],
        "checkout_count": 1,
        "repository_provenance": digest({"identity_key": identity_key, "checkout": checkout}),
    }


def resolve_target_branch(
    repository: dict[str, Any],
    *,
    override: str | None = None,
) -> dict[str, Any]:
    checkouts = [item for item in repository.get("checkouts", []) if isinstance(item, dict)]
    branches = sorted(
        {
            branch
            for checkout in checkouts
            for branch in checkout.get("local_branches", [])
            if isinstance(branch, str) and branch
        }
    )
    if override:
        if override not in branches:
            return {
                "branch": override,
                "source": "explicit_override",
                "status": "blocked",
                "reason": "explicit target branch is not present in a discovered checkout",
                "checkout_id": None,
            }
        source = "explicit_override"
        target_branch = override
    elif "dev" in branches:
        source = "default_dev"
        target_branch = "dev"
    else:
        documented = _documented_branch(repository)
        if documented is None or documented[0] not in branches:
            return {
                "branch": None,
                "source": "unresolved",
                "status": "blocked",
                "reason": "no dev branch or documented canonical fallback was found",
                "checkout_id": None,
            }
        target_branch, source = documented

    candidates = [
        checkout
        for checkout in checkouts
        if checkout.get("branch") == target_branch and checkout.get("exists") is True
    ]
    candidates.sort(key=lambda item: (item.get("dirty") is True, str(item.get("path", ""))))
    target_checkout = candidates[0] if candidates else None
    if target_checkout is None:
        return {
            "branch": target_branch,
            "source": source,
            "status": "blocked",
            "reason": "target branch exists but no attached checkout is currently available",
            "checkout_id": None,
        }
    state = _target_state(target_checkout)
    return {
        "branch": target_branch,
        "source": source,
        "status": "ready" if state["status"] == "ready" else state["status"],
        "reason": state["reason"],
        "checkout_id": target_checkout.get("checkout_id"),
        "head": target_checkout.get("head"),
        "target_state": state,
    }


def checkout_fingerprint(path: Path) -> dict[str, Any]:
    root = path.expanduser().resolve()
    status = _git_output(root, "status", "--porcelain=v1", "--untracked-files=all") or ""
    diff = _git_output(root, "diff", "--binary") or ""
    cached_diff = _git_output(root, "diff", "--cached", "--binary") or ""
    head = _git_output(root, "rev-parse", "HEAD")
    branch = _git_output(root, "symbolic-ref", "--short", "-q", "HEAD")
    return {
        "head": head,
        "branch": branch,
        "dirty": bool(status),
        "status_hash": digest(status),
        "diff_hash": digest({"worktree": diff, "cached": cached_diff}),
        "provenance_hash": digest(
            {"head": head, "branch": branch, "status": status, "diff": diff, "cached": cached_diff}
        ),
    }


def _discover_roots(root: Path) -> list[Path]:
    found: list[Path] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        has_git = ".git" in directories or ".git" in files
        directories[:] = [name for name in directories if name not in EXCLUDED_DIRECTORIES]
        current_path = Path(current)
        if has_git:
            found.append(current_path.resolve())
            directories[:] = []
    return sorted(set(found), key=lambda path: path.as_posix())


def _identity_key(root: Path) -> str:
    origin = _normalized_origin(root)
    if origin:
        return f"origin:{origin}"
    common = _common_git_dir(root)
    if common:
        return f"common:{common}"
    return f"path:{root.resolve()}"


def _normalized_origin(root: Path) -> str | None:
    remote = _git_output(root, "config", "--get", "remote.origin.url")
    if not remote:
        return None
    value = remote.strip()
    if value.startswith("git@") and ":" in value:
        host, path = value[4:].split(":", maxsplit=1)
        return f"{host.lower()}/{path.removesuffix('.git').strip('/').lower()}"
    parsed = urlparse(value)
    if parsed.hostname:
        path = parsed.path.removesuffix(".git").strip("/").lower()
        return f"{parsed.hostname.lower()}/{path}"
    return value.removesuffix(".git").rstrip("/").lower()


def _common_git_dir(root: Path) -> str | None:
    value = _git_output(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return str(Path(value).resolve()) if value else None


def _registered_worktrees(root: Path) -> list[dict[str, str]]:
    result = _git_run(root, "worktree", "list", "--porcelain")
    if result is None:
        return []
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.splitlines():
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line.removeprefix("worktree ").strip()
        elif line.startswith("HEAD "):
            current["head"] = line.removeprefix("HEAD ").strip()
        elif line.startswith("branch "):
            current["branch"] = line.removeprefix("branch ").removeprefix("refs/heads/").strip()
        elif line.startswith("prunable"):
            current["prunable"] = line.removeprefix("prunable").strip() or "true"
    if current:
        records.append(current)
    return records


def _checkout_record(
    *,
    repo_id: str,
    path: Path,
    primary: bool,
    projects_root: Path,
) -> dict[str, Any]:
    root = path.expanduser().resolve()
    exists = root.exists() and root.is_dir()
    head = _git_output(root, "rev-parse", "HEAD") if exists else None
    branch = _git_output(root, "symbolic-ref", "--short", "-q", "HEAD") if exists else None
    if (
        exists
        and branch is None
        and _git_output(root, "rev-parse", "--is-inside-work-tree") == "true"
    ):
        branch = None
    status = (
        _git_output(root, "status", "--porcelain=v1", "--untracked-files=all") if exists else None
    )
    upstream = (
        _git_output(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        if exists
        else None
    )
    ahead, behind = _ahead_behind(root, upstream) if exists and upstream else (None, None)
    worktree_record = (
        next(
            (
                item
                for item in _registered_worktrees(root)
                if Path(item.get("path", "")).resolve() == root
            ),
            {},
        )
        if exists
        else {}
    )
    prunable = "prunable" in worktree_record or not exists
    checkout_id = stable_id("checkout", repo_id, str(root))
    return {
        "schema": FLEET_CHECKOUT_SCHEMA,
        "checkout_id": checkout_id,
        "repo_id": repo_id,
        "path": str(root),
        "relative_to_projects_root": relative_path(projects_root, root),
        "is_primary": primary,
        "is_registered_worktree": bool(worktree_record),
        "exists": exists,
        "head": head,
        "branch": branch,
        "detached": exists and branch is None,
        "dirty": None if status is None else bool(status),
        "prunable": prunable,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "stale": bool(behind and behind > 0),
        "local_branches": _local_branches(root) if exists else [],
        "fingerprint": {
            "head": head,
            "branch": branch,
            "dirty": None if status is None else bool(status),
            "status_hash": digest(status or ""),
        }
        if exists
        else None,
        "provenance_hash": digest(
            {
                "path": str(root),
                "head": head,
                "branch": branch,
                "status": status,
                "upstream": upstream,
                "ahead": ahead,
                "behind": behind,
                "prunable": prunable,
            }
        ),
    }


def _target_state(checkout: dict[str, Any]) -> dict[str, str]:
    if checkout.get("exists") is not True:
        return {"status": "blocked", "reason": "target checkout does not exist"}
    if checkout.get("detached") is True:
        return {"status": "blocked", "reason": "target checkout is detached"}
    if checkout.get("prunable") is True:
        return {"status": "blocked", "reason": "target checkout is prunable"}
    if checkout.get("dirty") is True:
        return {"status": "blocked", "reason": "target checkout is dirty"}
    if not isinstance(checkout.get("head"), str) or not checkout.get("head"):
        return {"status": "blocked", "reason": "target checkout has no verifiable HEAD"}
    if checkout.get("stale") is True:
        return {"status": "stale", "reason": "target checkout is behind its configured upstream"}
    return {"status": "ready", "reason": "target checkout is clean, attached, and verifiable"}


def _documented_branch(repository: dict[str, Any]) -> tuple[str, str] | None:
    root = Path(str(repository.get("primary_path", ".")))
    texts: list[tuple[str, str]] = []
    for relative in (
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "CONTRIBUTING.md",
        ".agents/context/README.md",
    ):
        path = root / relative
        if path.is_file():
            try:
                texts.append((relative, path.read_text(encoding="utf-8")[:100_000]))
            except OSError:
                continue
    patterns = (
        (
            r"(?:canonical|default|primary|routine|development)\s+(?:branch|lane)[^\n]{0,80}\b(develop|trunk|main)\b",
            "documented_fallback",
        ),
        (
            r"\b(develop|trunk|main)\b\s+(?:branch|is)\s+(?:the\s+)?(?:canonical|default|primary)",
            "documented_fallback",
        ),
    )
    for path, text in texts:
        for pattern, source in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1), f"{source}:{path}"
    return None


def _repository_class(root: Path, origin: str | None) -> str:
    if (root / "Package.swift").exists() or any(root.glob("*.xcodeproj")):
        return "apple"
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        return "python"
    if (root / "package.json").exists():
        return "javascript"
    if (root / "go.mod").exists():
        return "go"
    if (root / "Cargo.toml").exists():
        return "rust"
    return "remote-other" if origin else "local-other"


def _local_branches(root: Path) -> list[str]:
    output = _git_output(root, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return sorted(output.splitlines()) if output else []


def _ahead_behind(root: Path, upstream: str | None) -> tuple[int | None, int | None]:
    if not upstream:
        return None, None
    output = _git_output(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
    if not output:
        return None, None
    parts = output.split()
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def _git_run(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _git_output(root: Path, *args: str) -> str | None:
    output = _git_run(root, *args)
    if output is None:
        return None
    value = output.strip()
    return value or None
