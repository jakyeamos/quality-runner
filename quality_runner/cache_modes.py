from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Literal, cast

CacheMode = Literal["repo", "external", "disabled"]
CACHE_MODES = frozenset({"repo", "external", "disabled"})


def resolve_cache_mode(
    cache_mode: str | None,
) -> CacheMode:
    if cache_mode is None:
        return "repo"
    if cache_mode not in CACHE_MODES:
        choices = ", ".join(sorted(CACHE_MODES))
        raise ValueError(f"cache_mode must be one of: {choices}")
    return cast(CacheMode, cache_mode)


def default_external_cache_root() -> Path:
    configured = os.environ.get("QUALITY_RUNNER_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "quality-runner"
    configured_xdg = os.environ.get("XDG_CACHE_HOME")
    if configured_xdg:
        return Path(configured_xdg).expanduser().resolve() / "quality-runner"
    return Path.home() / ".cache" / "quality-runner"


def cache_namespace(repo_root: Path) -> str:
    canonical = str(repo_root.expanduser().resolve()).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:24]


def cache_directory(
    repo_root: Path,
    *,
    mode: CacheMode,
    cache_root: Path | None = None,
    component: str,
) -> Path:
    root = repo_root.expanduser().resolve()
    if mode == "repo":
        return root / ".quality-runner" / "cache" / component
    if mode == "external":
        external_root = (
            cache_root.expanduser().resolve() if cache_root is not None else default_external_cache_root()
        )
        return external_root / cache_namespace(root) / component
    return root / ".quality-runner" / "cache" / component
