from __future__ import annotations

from collections.abc import Iterator, Sequence
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

ARTIFACT_DIRECTORY_NAMES = {
    ".cache",
    ".local",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".parcel-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    ".turbo",
    ".uv-cache",
    ".vercel",
    ".vite",
    "coverage",
    "htmlcov",
    "out",
    "playwright-report",
    "test-results",
}
TOP_LEVEL_ARTIFACT_DIRECTORY_NAMES = {
    "artifact",
    "artifacts",
    "checkpoints",
    "data",
    "figures",
    "logs",
    "notebooks",
    "output",
    "outputs",
    "plots",
    "reports",
    "staging",
}

DEFAULT_SCAN_EXCLUSIONS = [
    ".claude/worktrees/**",
    ".codex/worktrees/**",
    ".aider",
    ".aios",
    ".continue",
    ".cursor",
    ".planning",
    ".design-sync/previews/**",
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
    *sorted(ARTIFACT_DIRECTORY_NAMES),
    *[f"{name}/**" for name in sorted(TOP_LEVEL_ARTIFACT_DIRECTORY_NAMES)],
]
SCAN_EXCLUSION_MODULES = ("structural", "code_quality", "security")
SCAN_EXCLUSION_SCOPE_ALL = "all-modules"
SCAN_EXCLUSION_SCOPE_MODULE = "module-scoped"

type ScanExclusionOverlay = list[str] | dict[str, list[str]]
MAX_SCAN_PROGRESS_PATHS = 20
_SCAN_PROGRESS: dict[str, Any] = {
    "last_directory": None,
    "last_paths": [],
    "last_skipped_paths": [],
    "visited_paths": 0,
    "skipped_paths": 0,
    "visited_top_level_counts": {},
    "skipped_top_level_counts": {},
}


def resolve_scan_exclusions(
    config: dict[str, Any] | None,
    *,
    module: str | None = None,
) -> list[str]:
    configured = config.get("scan_exclusions") if isinstance(config, dict) else None
    exclusions = (
        [*DEFAULT_SCAN_EXCLUSIONS, *configured]
        if isinstance(configured, list)
        else list(DEFAULT_SCAN_EXCLUSIONS)
    )
    if module is None:
        return _unique(exclusions)
    normalized_module = normalize_scan_exclusion_module(module)
    module_config = config.get("scan_exclusions_by_module") if isinstance(config, dict) else None
    module_exclusions = (
        module_config.get(normalized_module) if isinstance(module_config, dict) else None
    )
    if isinstance(module_exclusions, list):
        exclusions.extend(module_exclusions)
    return _unique(exclusions)


def resolve_scan_exclusions_by_module(config: dict[str, Any] | None) -> dict[str, list[str]]:
    return {
        SCAN_EXCLUSION_SCOPE_ALL: resolve_scan_exclusions(config),
        **{
            module: resolve_scan_exclusions(config, module=module)
            for module in SCAN_EXCLUSION_MODULES
        },
    }


def effective_scan_exclusions(
    root: Path,
    config: dict[str, Any] | None,
    *,
    module: str | None = None,
) -> list[str]:
    return _unique(
        [
            *resolve_scan_exclusions(config, module=module),
            *gitignore_scan_exclusions(root),
        ]
    )


def effective_scan_exclusions_by_module(
    root: Path,
    config: dict[str, Any] | None,
) -> dict[str, list[str]]:
    return {
        scope: effective_scan_exclusions(
            root,
            config,
            module=None if scope == SCAN_EXCLUSION_SCOPE_ALL else scope,
        )
        for scope in (SCAN_EXCLUSION_SCOPE_ALL, *SCAN_EXCLUSION_MODULES)
    }


def normalize_scan_exclusion_module(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in SCAN_EXCLUSION_MODULES:
        allowed = ", ".join(SCAN_EXCLUSION_MODULES)
        raise ValueError(f"unknown scan-exclusion module {value!r}; expected one of: {allowed}")
    return normalized


def scan_exclusion_overlay_parts(
    overlay: ScanExclusionOverlay | None,
) -> tuple[list[str], dict[str, list[str]]]:
    if overlay is None:
        return [], {}
    if isinstance(overlay, list):
        return list(overlay), {}
    global_paths: list[str] = []
    module_paths: dict[str, list[str]] = {}
    for raw_scope, paths in overlay.items():
        if raw_scope in {SCAN_EXCLUSION_SCOPE_ALL, "all_modules"}:
            global_paths.extend(paths)
            continue
        scope = normalize_scan_exclusion_module(raw_scope)
        module_paths.setdefault(scope, []).extend(paths)
    return global_paths, module_paths


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
                _record_skipped(root, child)
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


def _unique(values: Sequence[object]) -> list[str]:
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
    _SCAN_PROGRESS["last_skipped_paths"] = []
    _SCAN_PROGRESS["visited_paths"] = 0
    _SCAN_PROGRESS["skipped_paths"] = 0
    _SCAN_PROGRESS["visited_top_level_counts"] = {}
    _SCAN_PROGRESS["skipped_top_level_counts"] = {}


def scan_progress_snapshot() -> dict[str, Any]:
    return {
        "last_directory": _SCAN_PROGRESS["last_directory"],
        "last_paths": list(_SCAN_PROGRESS["last_paths"]),
        "last_skipped_paths": list(_SCAN_PROGRESS["last_skipped_paths"]),
        "visited_paths": _SCAN_PROGRESS["visited_paths"],
        "skipped_paths": _SCAN_PROGRESS["skipped_paths"],
        "visited_top_level_counts": dict(_SCAN_PROGRESS["visited_top_level_counts"]),
        "skipped_top_level_counts": dict(_SCAN_PROGRESS["skipped_top_level_counts"]),
    }


def _record_directory(root: Path, directory: Path) -> None:
    _SCAN_PROGRESS["last_directory"] = _relative_path(root, directory)


def _record_path(root: Path, path: Path) -> None:
    _SCAN_PROGRESS["visited_paths"] += 1
    _increment_count("visited_top_level_counts", _top_level(root, path))
    paths = _SCAN_PROGRESS["last_paths"]
    if not isinstance(paths, list):
        paths = []
        _SCAN_PROGRESS["last_paths"] = paths
    paths.append(_relative_path(root, path))
    del paths[:-MAX_SCAN_PROGRESS_PATHS]


def _record_skipped(root: Path, path: Path) -> None:
    _SCAN_PROGRESS["skipped_paths"] += 1
    _increment_count("skipped_top_level_counts", _top_level(root, path))
    paths = _SCAN_PROGRESS["last_skipped_paths"]
    if not isinstance(paths, list):
        paths = []
        _SCAN_PROGRESS["last_skipped_paths"] = paths
    paths.append(_relative_path(root, path))
    del paths[:-MAX_SCAN_PROGRESS_PATHS]


def _increment_count(key: str, value: str | None) -> None:
    if value is None:
        return
    counts = _SCAN_PROGRESS[key]
    if not isinstance(counts, dict):
        counts = {}
        _SCAN_PROGRESS[key] = counts
    counts[value] = int(counts.get(value, 0)) + 1


def _top_level(root: Path, path: Path) -> str | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    return relative.parts[0] if relative.parts else "."


def _relative_path(root: Path, path: Path) -> str | None:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return None
    return "." if relative == "." else relative
