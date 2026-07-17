from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from quality_runner.code_quality_paths import TEXT_EXTENSIONS
from quality_runner.exclusion_preflight_support import (
    CANDIDATE_SCAN_SECONDS_THRESHOLD,
    CANDIDATE_TEXT_FILE_THRESHOLD,
    MAX_CANDIDATES,
    MAX_PREFLIGHT_DIRECTORIES,
    MAX_PREFLIGHT_FILES,
    DirectoryStats,
    candidate_id,
    dict_value,
    directory_stats,
    estimated_scan_seconds,
    git_file_paths,
    is_effectively_excluded,
    is_same_or_child,
    path_markers,
    path_prefixes,
    positive_int,
    protected_path_reasons,
    relative_path,
)
from quality_runner.scan_exclusions import (
    SCAN_EXCLUSION_MODULES,
    SCAN_EXCLUSION_SCOPE_ALL,
    matches_scan_exclusion,
)


def inventory_candidates(
    root: Path,
    *,
    effective_exclusions: list[str],
    gitignore_patterns: list[str],
    config: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    stats: dict[str, DirectoryStats] = {"": DirectoryStats()}
    marker_paths: set[str] = set()
    marker_cache: dict[str, tuple[list[str], list[str]]] = {}
    visited_directories = 0
    visited_files = 0
    truncated = False
    for current_root, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current_root)
        current_relative = relative_path(root, current_path)
        if current_relative and is_effectively_excluded(current_relative, effective_exclusions):
            dir_names[:] = []
            continue
        visited_directories += 1
        if visited_directories > MAX_PREFLIGHT_DIRECTORIES:
            truncated = True
            dir_names[:] = []
            break
        for prefix in path_prefixes(current_relative):
            directory_stats(stats, prefix).directory_count += 1
        generated_markers, artifact_markers = path_markers(current_relative)
        if current_relative and (generated_markers or artifact_markers):
            marker_paths.add(current_relative)
            marker_cache[current_relative] = (generated_markers, artifact_markers)

        kept_dirs: list[str] = []
        for directory_name in sorted(dir_names):
            child = current_path / directory_name
            child_relative = relative_path(root, child)
            if child.is_symlink() or is_effectively_excluded(child_relative, effective_exclusions):
                continue
            kept_dirs.append(directory_name)
        dir_names[:] = kept_dirs

        for file_name in sorted(file_names):
            file_path = current_path / file_name
            if file_path.is_symlink() or not file_path.is_file():
                continue
            visited_files += 1
            if visited_files > MAX_PREFLIGHT_FILES:
                truncated = True
                dir_names[:] = []
                break
            extension = file_path.suffix.lower() or "[no-extension]"
            is_text = file_path.suffix.lower() in TEXT_EXTENSIONS or file_path.name in {
                "Dockerfile",
                "Makefile",
            }
            for prefix in path_prefixes(current_relative):
                directory = directory_stats(stats, prefix)
                directory.file_count += 1
                if is_text:
                    directory.text_file_count += 1
                directory.extensions[extension] += 1
        if truncated:
            break

    tracked_available, tracked_paths, untracked_paths = git_file_paths(root)
    potential_paths = set(marker_paths)
    for current_relative, directory in stats.items():
        if not current_relative or current_relative in marker_paths:
            continue
        estimated_seconds = estimated_scan_seconds(directory.text_file_count)
        untracked_count = (
            sum(1 for path in untracked_paths if is_same_or_child(path, current_relative))
            if tracked_available
            else 0
        )
        tracked_count = (
            sum(1 for path in tracked_paths if is_same_or_child(path, current_relative))
            if tracked_available
            else 0
        )
        is_unowned = (
            tracked_available
            and directory.file_count > 0
            and tracked_count == 0
            and untracked_count > 0
        )
        if (
            directory.text_file_count >= CANDIDATE_TEXT_FILE_THRESHOLD
            or estimated_seconds >= CANDIDATE_SCAN_SECONDS_THRESHOLD
            or is_unowned
        ) and not protected_path_reasons(current_relative):
            potential_paths.add(current_relative)

    selected_paths: list[str] = []
    for current_relative in sorted(
        potential_paths, key=lambda item: (len(PurePosixPath(item).parts), item)
    ):
        if any(is_same_or_child(current_relative, selected) for selected in selected_paths):
            continue
        selected_paths.append(current_relative)
    selected_paths = sorted(selected_paths)[:MAX_CANDIDATES]

    max_text_files = positive_int(dict_value(config.get("structural_scan")).get("max_text_files"))
    candidates: list[dict[str, object]] = []
    for current_relative in selected_paths:
        directory = stats.get(current_relative, DirectoryStats())
        generated_markers, artifact_markers = marker_cache.get(
            current_relative, path_markers(current_relative)
        )
        protected_reasons = protected_path_reasons(current_relative)
        tracked_count = (
            sum(1 for path in tracked_paths if is_same_or_child(path, current_relative))
            if tracked_available
            else None
        )
        untracked_count = (
            sum(1 for path in untracked_paths if is_same_or_child(path, current_relative))
            if tracked_available
            else None
        )
        unowned_count = (
            max(directory.file_count - int(tracked_count or 0), 0) if tracked_available else None
        )
        ignored = matches_scan_exclusion(current_relative, gitignore_patterns)
        estimated_seconds = estimated_scan_seconds(directory.text_file_count)
        timeout_signals: list[str] = []
        if estimated_seconds >= CANDIDATE_SCAN_SECONDS_THRESHOLD:
            timeout_signals.append("estimated scan cost exceeds the review threshold")
        if max_text_files and directory.text_file_count >= max_text_files:
            timeout_signals.append(
                f"estimated text files reach configured max_text_files={max_text_files}"
            )
        if truncated and directory.text_file_count >= MAX_PREFLIGHT_FILES:
            timeout_signals.append("preflight estimate was bounded by the traversal limit")
        evidence: dict[str, object] = {
            "tracked_status": (
                "tracked"
                if tracked_available and tracked_count
                else "untracked-or-unowned"
                if tracked_available
                else "unknown-no-git-root"
            ),
            "tracked_file_count": tracked_count,
            "untracked_file_count": untracked_count,
            "unowned_file_count": unowned_count,
            "unowned": bool(unowned_count and unowned_count > 0) if tracked_available else None,
            "ignored": ignored,
            "file_count": directory.file_count,
            "directory_count": directory.directory_count,
            "extensions": dict(sorted(directory.extensions.items())),
            "generated_markers": generated_markers,
            "artifact_markers": artifact_markers,
            "estimated_text_files": directory.text_file_count,
            "estimated_scan_seconds": estimated_seconds,
            "estimate_truncated": truncated,
            "timeout_signals": timeout_signals,
        }
        has_strong_marker = bool(generated_markers or artifact_markers)
        confidence = (
            "high"
            if has_strong_marker and (evidence["unowned"] is True or estimated_seconds >= 5)
            else "medium"
            if has_strong_marker
            else "low"
        )
        candidates.append(
            {
                "candidate_id": candidate_id(current_relative),
                "path": current_relative,
                "proposed_scope": {
                    "path": current_relative,
                    "pattern": f"{current_relative}/**",
                    "module_scope": SCAN_EXCLUSION_SCOPE_ALL,
                    "available_module_scopes": [
                        SCAN_EXCLUSION_SCOPE_ALL,
                        *SCAN_EXCLUSION_MODULES,
                    ],
                },
                "evidence": evidence,
                "protected": bool(protected_reasons),
                "protected_reasons": protected_reasons,
                "suggested_decision": "defer"
                if protected_reasons
                else "exclude"
                if has_strong_marker
                else "defer",
                "confidence": confidence,
            }
        )
    return candidates, {
        "visited_directories": min(visited_directories, MAX_PREFLIGHT_DIRECTORIES),
        "visited_files": min(visited_files, MAX_PREFLIGHT_FILES),
        "truncated": truncated,
        "candidate_count": len(candidates),
        "limits": {
            "max_directories": MAX_PREFLIGHT_DIRECTORIES,
            "max_files": MAX_PREFLIGHT_FILES,
            "max_candidates": MAX_CANDIDATES,
        },
    }
