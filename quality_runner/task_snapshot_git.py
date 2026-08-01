from __future__ import annotations

import os
import subprocess
from pathlib import Path


class SnapshotError(RuntimeError):
    pass


def isolated_object_environment(
    repo_root: Path,
    object_directory: Path,
) -> dict[str, str]:
    repository_objects = Path(
        git(
            repo_root,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "objects",
        ).strip()
    )
    return {
        **os.environ,
        "GIT_OBJECT_DIRECTORY": str(object_directory),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(repository_objects),
    }


def merge_tree(
    repo_root: Path,
    baseline_sha: str,
    head_sha: str,
    *,
    environment: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        ["git", "merge-tree", "--write-tree", baseline_sha, head_sha],
        cwd=repo_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = "\n".join(item.strip() for item in (result.stdout, result.stderr) if item.strip())
        raise SnapshotError(
            "target and task revisions cannot be represented as an unambiguous merge"
            + (f": {detail}" if detail else "")
        )
    tree = result.stdout.splitlines()[0].strip() if result.stdout else ""
    if len(tree) != 40 or any(character not in "0123456789abcdef" for character in tree):
        raise SnapshotError("git merge-tree returned an invalid tree identity")
    return tree


def git(repo_root: Path, *args: str) -> str:
    return git_bytes(repo_root, *args).decode("utf-8", errors="strict")


def git_bytes(
    repo_root: Path,
    *args: str,
    environment: dict[str, str] | None = None,
) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        env=environment,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout
