from __future__ import annotations

from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

ALWAYS_EXCLUDED_PATH_PARTS = {
    ".git",
    ".quality-runner",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

DEFAULT_SCAN_EXCLUSIONS = [
    ".aios",
    ".planning",
    ".superpowers",
    ".tracker",
    "docs",
    "fixtures",
    "corpus",
    "generated-corpus",
    "generated-corpora",
    "vendor",
    "vendors",
    "vendored",
    "third_party",
]
MAX_SCAN_PROGRESS_PATHS = 20
_SCAN_PROGRESS: dict[str, Any] = {
    "last_directory": None,
    "last_paths": [],
    "visited_paths": 0,
    "skipped_paths": 0,
}


def resolve_scan_exclusions(config: dict[str, Any] | None) -> list[str]:
    configured = config.get("scan_exclusions") if isinstance(config, dict) else None
    if not isinstance(configured, list):
        return list(DEFAULT_SCAN_EXCLUSIONS)
    return _unique([*DEFAULT_SCAN_EXCLUSIONS, *configured])


def is_scan_path_allowed(root: Path, path: Path, scan_exclusions: list[str]) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if path.is_symlink():
        return False
    if any(part in ALWAYS_EXCLUDED_PATH_PARTS for part in relative.parts):
        return False
    relative_path = relative.as_posix()
    return not matches_scan_exclusion(relative_path, scan_exclusions)


def iter_allowed_paths(root: Path, scan_exclusions: list[str]) -> Iterator[Path]:
    effective_exclusions = _unique([*scan_exclusions, *gitignore_scan_exclusions(root)])
    reset_scan_progress()
    stack = [root]
    while stack:
        directory = stack.pop()
        _record_directory(root, directory)
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError:
            continue
        for child in children:
            if not is_scan_path_allowed(root, child, effective_exclusions):
                _record_skipped()
                continue
            _record_path(root, child)
            yield child
            if child.is_dir():
                stack.append(child)


def matches_scan_exclusion(relative_path: str, scan_exclusions: list[str]) -> bool:
    return any(
        _matches_exclusion(relative_path, pattern)
        for pattern in scan_exclusions
        if isinstance(pattern, str)
    )


def _matches_exclusion(relative_path: str, pattern: str) -> bool:
    normalized_pattern = pattern.strip().strip("/")
    if not normalized_pattern:
        return False
    normalized_path = relative_path.strip("/")
    if not normalized_path:
        return False
    if _is_plain_segment_pattern(normalized_pattern):
        return normalized_pattern in normalized_path.split("/")
    if fnmatchcase(normalized_path, normalized_pattern):
        return True
    if normalized_pattern.endswith("/**"):
        base_pattern = normalized_pattern[:-3].rstrip("/")
        return fnmatchcase(normalized_path, base_pattern)
    return False


def _is_plain_segment_pattern(pattern: str) -> bool:
    return "/" not in pattern and not any(char in pattern for char in "*?[]")


def _unique(values: list[object]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str) and value and value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


def gitignore_scan_exclusions(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.exists() or gitignore.is_symlink():
        return []
    try:
        lines = gitignore.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    patterns: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        patterns.append(stripped.lstrip("/").rstrip("/"))
    return _unique(patterns)


def reset_scan_progress() -> None:
    _SCAN_PROGRESS["last_directory"] = None
    _SCAN_PROGRESS["last_paths"] = []
    _SCAN_PROGRESS["visited_paths"] = 0
    _SCAN_PROGRESS["skipped_paths"] = 0


def scan_progress_snapshot() -> dict[str, Any]:
    return {
        "last_directory": _SCAN_PROGRESS["last_directory"],
        "last_paths": list(_SCAN_PROGRESS["last_paths"]),
        "visited_paths": _SCAN_PROGRESS["visited_paths"],
        "skipped_paths": _SCAN_PROGRESS["skipped_paths"],
    }


def _record_directory(root: Path, directory: Path) -> None:
    _SCAN_PROGRESS["last_directory"] = _relative_path(root, directory)


def _record_path(root: Path, path: Path) -> None:
    _SCAN_PROGRESS["visited_paths"] += 1
    paths = _SCAN_PROGRESS["last_paths"]
    if not isinstance(paths, list):
        paths = []
        _SCAN_PROGRESS["last_paths"] = paths
    paths.append(_relative_path(root, path))
    del paths[:-MAX_SCAN_PROGRESS_PATHS]


def _record_skipped() -> None:
    _SCAN_PROGRESS["skipped_paths"] += 1


def _relative_path(root: Path, path: Path) -> str | None:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return None
    return "." if relative == "." else relative
