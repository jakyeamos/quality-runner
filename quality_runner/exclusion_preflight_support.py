from __future__ import annotations

import hashlib
import subprocess
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import cast

from quality_runner import __version__
from quality_runner.config import CONFIG_FILE_NAME, load_repo_config
from quality_runner.scan_exclusions import (
    ALWAYS_EXCLUDED_PATH_PARTS,
    ARTIFACT_DIRECTORY_NAMES,
    TOP_LEVEL_ARTIFACT_DIRECTORY_NAMES,
    matches_scan_exclusion,
    scan_exclusion_contract,
)
from quality_runner.schema_constants import (
    SCAN_EXCLUSION_PACKET_SCHEMA,
    SCAN_EXCLUSION_REPORT_SCHEMA,
    SCAN_EXCLUSION_RESULT_SCHEMA,
)

EXCLUSION_PACKET_SCHEMA = SCAN_EXCLUSION_PACKET_SCHEMA
EXCLUSION_REPORT_SCHEMA = SCAN_EXCLUSION_REPORT_SCHEMA
EXCLUSION_RESULT_SCHEMA = SCAN_EXCLUSION_RESULT_SCHEMA

MAX_PREFLIGHT_FILES = 100_000
MAX_PREFLIGHT_DIRECTORIES = 20_000
MAX_CANDIDATES = 100
CANDIDATE_TEXT_FILE_THRESHOLD = 100
CANDIDATE_SCAN_SECONDS_THRESHOLD = 5.0
ESTIMATED_SCAN_SECONDS_PER_TEXT_FILE = 0.015

PROTECTED_ROOT_NAMES = frozenset(
    {
        "auth",
        "authentication",
        "authorization",
        ".github",
        ".git",
        ".quality-runner",
        "api",
        "app",
        "apps",
        "backend",
        "client",
        "config",
        "configs",
        "frontend",
        "lib",
        "libs",
        "migrations",
        "packages",
        "quality_evidence_contract",
        "quality_runner",
        "security",
        "secret",
        "secrets",
        "server",
        "services",
        "src",
        "test",
        "tests",
    }
)
SUSPICIOUS_NAME_TOKENS = frozenset(
    {
        "archive",
        "cache",
        "corpus",
        "dataset",
        "dist",
        "external",
        "fixture",
        "generated",
        "gen",
        "log",
        "logs",
        "notebook",
        "output",
        "outputs",
        "report",
        "reports",
        "scratch",
        "staging",
        "temp",
        "tmp",
        "vendor",
    }
)

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass
class DirectoryStats:
    file_count: int = 0
    text_file_count: int = 0
    directory_count: int = 0
    extensions: Counter[str] = field(default_factory=Counter)


def repository_fingerprint(
    repo_root: Path,
    *,
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    root = repo_root.expanduser().resolve()
    resolved_config = config if config is not None else load_repo_config(root)
    exclusions = scan_exclusion_contract(root, resolved_config)
    git_root = git_output(root, "rev-parse", "--show-toplevel")
    if git_root is None or Path(git_root).resolve() != root:
        return {
            "git": False,
            "head_sha": None,
            "branch": None,
            "tracked_worktree_dirty": None,
            "config_sha256": file_sha256(root / CONFIG_FILE_NAME),
            "gitignore_sha256": exclusions["gitignore_sha256"],
            "scan_exclusion_fingerprint": exclusions["fingerprint"],
            "effective_scan_exclusions_by_module": exclusions[
                "effective_scan_exclusions_by_module"
            ],
            "quality_runner_version": __version__,
        }
    status = git_output(root, "status", "--porcelain", "--untracked-files=no")
    return {
        "git": True,
        "head_sha": git_output(root, "rev-parse", "HEAD"),
        "branch": git_output(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "tracked_worktree_dirty": bool(status),
        "config_sha256": file_sha256(root / CONFIG_FILE_NAME),
        "gitignore_sha256": exclusions["gitignore_sha256"],
        "scan_exclusion_fingerprint": exclusions["fingerprint"],
        "effective_scan_exclusions_by_module": exclusions["effective_scan_exclusions_by_module"],
        "quality_runner_version": __version__,
    }


def git_file_paths(root: Path) -> tuple[bool, list[str], list[str]]:
    git_root = git_output(root, "rev-parse", "--show-toplevel")
    if git_root is None or Path(git_root).resolve() != root:
        return False, [], []
    tracked = git_output(root, "ls-files", "-z", "--")
    untracked = git_output(root, "ls-files", "--others", "--exclude-standard", "-z", "--")
    if tracked is None or untracked is None:
        return False, [], []
    return True, split_nul_paths(tracked), split_nul_paths(untracked)


def git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, check=False, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip("\n") or None


def split_nul_paths(value: str) -> list[str]:
    return [item for item in value.split("\0") if item]


def relative_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    return "" if not relative.parts else relative.as_posix()


def path_prefixes(relative: str) -> list[str]:
    parts = PurePosixPath(relative).parts if relative else ()
    return ["/".join(parts[:index]) for index in range(len(parts), -1, -1)]


def directory_stats(stats: dict[str, DirectoryStats], relative: str) -> DirectoryStats:
    if relative not in stats:
        stats[relative] = DirectoryStats()
    return stats[relative]


def path_markers(relative: str) -> tuple[list[str], list[str]]:
    if not relative:
        return [], []
    name = PurePosixPath(relative).name.lower()
    generated: list[str] = []
    artifacts: list[str] = []
    if "generated" in name or name in {"gen", "autogen", "autogenerated"}:
        generated.append(f"directory name suggests generated content: {name}")
    if name in ARTIFACT_DIRECTORY_NAMES:
        artifacts.append(f"known artifact directory: {name}")
    if name in TOP_LEVEL_ARTIFACT_DIRECTORY_NAMES:
        artifacts.append(f"known top-level artifact directory: {name}")
    for token in sorted(SUSPICIOUS_NAME_TOKENS):
        if token in name and token not in {"generated", "gen"}:
            artifacts.append(f"directory name contains artifact marker: {token}")
    return generated, artifacts


def is_effectively_excluded(relative: str, exclusions: list[str]) -> bool:
    if not relative:
        return False
    if any(part in ALWAYS_EXCLUDED_PATH_PARTS for part in PurePosixPath(relative).parts):
        return True
    return matches_scan_exclusion(relative, exclusions)


def is_same_or_child(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + "/")


def protected_path_reasons(relative: str) -> list[str]:
    reasons: list[str] = []
    source_roots = {
        "src",
        "app",
        "apps",
        "lib",
        "libs",
        "packages",
        "server",
        "client",
        "backend",
        "frontend",
        "api",
        "services",
    }
    for part in PurePosixPath(relative).parts:
        lowered = part.lower()
        if lowered in PROTECTED_ROOT_NAMES:
            category = "source root" if lowered in source_roots else "security/configuration root"
            reasons.append(f"{category}: {part}")
    return unique_strings(reasons)


def relative_path_error(value: str) -> str | None:
    if value.startswith(("/", "~")):
        return "must be repo-relative"
    if "\x00" in value:
        return "must not contain NUL bytes"
    if "\\" in value:
        return "must use POSIX separators"
    if any(char in value for char in "*?[]{}"):
        return "wildcards and broad globs are not allowed"
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return "must not contain traversal or empty path segments"
    if PurePosixPath(value).as_posix() != value:
        return "must use a normalized repo-relative path"
    return None


def path_has_symlink_component(root: Path, relative: str) -> bool:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def candidate_id(relative: str) -> str:
    return f"EXC-{hashlib.sha256(relative.encode('utf-8')).hexdigest()[:12]}"


def estimated_scan_seconds(text_files: int) -> float:
    if text_files <= 0:
        return 0.0
    return max(0.1, round(text_files * ESTIMATED_SCAN_SECONDS_PER_TEXT_FILE, 1))


def file_sha256(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    except OSError:
        return None


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def json_safe(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return str(value)


def dict_value(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def object_value(value: object) -> dict[str, object]:
    return dict_value(value)


def object_list(value: object) -> list[dict[str, object]]:
    return (
        [cast(dict[str, object], item) for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def unique_strings(values: Sequence[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str) and value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
