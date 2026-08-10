from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
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
    ".build",
    ".cache",
    ".gradle",
    ".idea",
    ".quality-runner",
    ".venv",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".swiftpm",
    ".turbo",
    ".pnpm-store",
    ".worktrees",
    ".tmp",
    ".uv-cache",
    "node_modules",
    "vendor",
    "__pycache__",
    "artifacts",
    "data",
    "build",
    "dist",
    "coverage",
    "runs",
    "target",
    "worktrees",
    "DerivedData",
}

FLEET_POLICY_RELATIVE_PATH = Path(".quality-runner/fleet.json")
FLEET_POLICY_SCHEMA = "quality-runner-fleet-policy-v0.1"


def load_fleet_policy(projects_root: Path) -> dict[str, Any]:
    root = projects_root.expanduser().resolve()
    path = root / FLEET_POLICY_RELATIVE_PATH
    if not path.is_file():
        return {
            "schema": FLEET_POLICY_SCHEMA,
            "source": "default",
            "path": str(path),
            "exclude_paths": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"fleet policy is not valid JSON: {path}") from error
    if not isinstance(payload, dict) or payload.get("schema") != FLEET_POLICY_SCHEMA:
        raise ValueError(f"fleet policy must declare schema {FLEET_POLICY_SCHEMA}: {path}")
    raw_exclusions = payload.get("exclude_paths", [])
    if not isinstance(raw_exclusions, list):
        raise ValueError(f"fleet policy exclude_paths must be an array: {path}")
    exclusions: list[str] = []
    for raw in raw_exclusions:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"fleet policy exclusions must be non-empty strings: {path}")
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"fleet policy exclusions must stay under projects_root: {raw}")
        normalized = candidate.as_posix().strip("/")
        if normalized in {"", "."}:
            raise ValueError("fleet policy cannot exclude the projects root")
        exclusions.append(normalized)
    return {
        "schema": FLEET_POLICY_SCHEMA,
        "source": "projects_root",
        "path": str(path),
        "exclude_paths": sorted(set(exclusions)),
    }


def discover_repositories(
    projects_root: Path, *, policy: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    root = projects_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"projects root is not a directory: {root}")
    resolved_policy = policy or load_fleet_policy(root)
    excluded_paths = {
        str(path) for path in resolved_policy.get("exclude_paths", []) if isinstance(path, str)
    }
    candidates = _discover_roots(root, excluded_paths=excluded_paths)
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


def repositories_for_scope(
    projects_root: Path,
    repository_paths: Sequence[Path] | None,
    *,
    fleet_policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if repository_paths is None:
        return discover_repositories(projects_root, policy=fleet_policy)
    root = projects_root.expanduser().resolve()
    records: dict[str, dict[str, Any]] = {}
    for path in repository_paths:
        resolved = path.expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"repository path is outside the bounded projects root: {resolved}"
            ) from error
        record = repository_record_for_root(resolved)
        records[str(record["repo_id"])] = record
    return [records[repo_id] for repo_id in sorted(records)]


def resolve_target_branch(
    repository: dict[str, Any],
    *,
    override: str | None = None,
) -> dict[str, Any]:
    from quality_runner.fleet.targeting import resolve_target_branch as resolve

    return resolve(repository, override=override)


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


def _discover_roots(root: Path, *, excluded_paths: set[str] | None = None) -> list[Path]:
    exclusions = excluded_paths or set()
    found: list[Path] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(root).as_posix()
        if relative_current != "." and _fleet_path_is_excluded(relative_current, exclusions):
            directories[:] = []
            continue
        has_git = ".git" in directories or ".git" in files
        directories[:] = [
            name
            for name in directories
            if name not in EXCLUDED_DIRECTORIES
            and not _fleet_path_is_excluded(
                (current_path / name).relative_to(root).as_posix(), exclusions
            )
        ]
        if has_git:
            found.append(current_path.resolve())
    return sorted(set(found), key=lambda path: path.as_posix())


def _fleet_path_is_excluded(relative_path: str, exclusions: set[str]) -> bool:
    return any(
        relative_path == excluded or relative_path.startswith(f"{excluded}/")
        for excluded in exclusions
    )


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
    working_tree = (
        _git_output(root, "rev-parse", "--is-inside-work-tree") == "true" if exists else False
    )
    head = _git_output(root, "rev-parse", "HEAD") if exists else None
    branch = _git_output(root, "symbolic-ref", "--short", "-q", "HEAD") if working_tree else None
    status = (
        _git_output(root, "status", "--porcelain=v1", "--untracked-files=all")
        if working_tree
        else None
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
        "working_tree": working_tree,
        "exists": exists,
        "head": head,
        "branch": branch,
        "detached": working_tree and branch is None,
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


def _ahead_behind(
    root: Path, upstream: str | None, *, head: str = "HEAD"
) -> tuple[int | None, int | None]:
    if not upstream:
        return None, None
    output = _git_output(root, "rev-list", "--left-right", "--count", f"{head}...{upstream}")
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
