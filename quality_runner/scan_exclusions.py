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
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError:
            continue
        for child in children:
            if not is_scan_path_allowed(root, child, effective_exclusions):
                continue
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
