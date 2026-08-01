from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from quality_runner.semantic_similarity_cache import (
    SemanticSimilarityCache,
    cache_identity,
    cache_key,
)

SimilarityMaterializer = Callable[[Mapping[str, object]], dict[str, Any]]
SimilarityScan = Callable[[], dict[str, Any]]


def cached_semantic_similarity_scan(
    repo_root: Path,
    *,
    scanned_files: Sequence[Mapping[str, object]] | None,
    policy: Mapping[str, object],
    disabled_groups: set[str],
    persist_cache: bool,
    cache_root: Path | None,
    implementation_paths: Sequence[Path],
    excluded_path_parts: set[str],
    supported_extensions: set[str],
    scan: SimilarityScan,
    materialize: SimilarityMaterializer,
) -> dict[str, Any]:
    cache = SemanticSimilarityCache(
        repo_root,
        cache_root=cache_root,
        persist=persist_cache,
    )
    cache_files = _cache_input_files(
        repo_root,
        scanned_files,
        excluded_path_parts=excluded_path_parts,
        supported_extensions=supported_extensions,
    )
    considered_files = len(cache_files)
    if "deduplicate" in disabled_groups or policy.get("similarity_enabled") is False:
        result = scan()
        return _with_cache_evidence(
            result,
            cache=cache,
            cache_status="disabled",
            considered_files=considered_files,
        )
    similarity_key = cache_key(
        scanned_files=cache_files,
        policy=policy,
        disabled_groups=disabled_groups,
        implementation_paths=implementation_paths,
    )
    identity = cache_identity(
        scanned_files=cache_files,
        policy=policy,
        disabled_groups=disabled_groups,
        implementation_paths=implementation_paths,
    )
    if persist_cache:
        cached = cache.get(key=similarity_key, identity=identity, materialize=materialize)
        if cached is not None:
            return _with_cache_evidence(
                cached,
                cache=cache,
                cache_status="hit",
                considered_files=considered_files,
            )
    result = scan()
    cache_status = "miss" if persist_cache else "disabled"
    if persist_cache and result.get("status") in {"executed", "not_applicable"}:
        cache.put(key=similarity_key, identity=identity, result=result)
    return _with_cache_evidence(
        result,
        cache=cache,
        cache_status=cache_status,
        considered_files=considered_files,
    )


def _with_cache_evidence(
    result: dict[str, Any],
    *,
    cache: SemanticSimilarityCache,
    cache_status: str,
    considered_files: int,
) -> dict[str, Any]:
    return {
        **result,
        "cache_status": cache_status,
        "cache_evidence": cache.evidence(
            cache_status=cache_status,
            considered_files=considered_files,
        ),
    }


def _cache_input_files(
    repo_root: Path,
    scanned_files: Sequence[Mapping[str, object]] | None,
    *,
    excluded_path_parts: set[str],
    supported_extensions: set[str],
) -> list[dict[str, object]]:
    if scanned_files is not None:
        return [dict(item) for item in scanned_files]
    files: list[dict[str, object]] = []
    resolved_root = repo_root.expanduser().resolve()
    for current_root, directory_names, file_names in os.walk(resolved_root):
        directory_names[:] = [
            name
            for name in directory_names
            if name not in excluded_path_parts and not name.startswith(".git")
        ]
        for file_name in file_names:
            path = Path(current_root) / file_name
            if path.suffix.lower() not in supported_extensions:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files.append({"path": path.relative_to(resolved_root).as_posix(), "text": text})
    return files
