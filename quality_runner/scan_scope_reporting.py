from __future__ import annotations

import os
from pathlib import Path

from quality_runner.code_quality_paths import TEXT_EXTENSIONS
from quality_runner.core.audit_contracts import AuditPayload

TEXT_FILE_NAMES = {"Dockerfile", "Makefile"}
DEFAULT_SKIPPED_PATH_ESTIMATE_LIMIT = 10_000
ESTIMATED_SCAN_SECONDS_PER_TEXT_FILE = 0.015


def skipped_directory_entry(root: Path, path: Path, reason: str) -> AuditPayload:
    relative_path = path.relative_to(root).as_posix()
    estimated_files, estimate_truncated = estimate_text_files(path)
    return {
        "path": relative_path,
        "reason": reason,
        "estimated_text_files": estimated_files,
        "estimated_scan_seconds": estimated_scan_seconds(estimated_files),
        "estimate_truncated": estimate_truncated,
        "include_config_hint": (
            f'[quality_runner.structural_scan] include_ignored_paths = ["{relative_path}"]'
        ),
    }


def fast_skipped_directory_entry(root: Path, path: Path, reason: str) -> AuditPayload:
    relative_path = path.relative_to(root).as_posix()
    return {
        "path": relative_path,
        "reason": reason,
        "estimate_deferred": True,
        "include_config_hint": (
            f'[quality_runner.structural_scan] include_ignored_paths = ["{relative_path}"]'
        ),
    }


def scan_budget_summary(
    *,
    scanned_files: int,
    max_text_files: int,
    skipped_files: list[AuditPayload],
) -> AuditPayload:
    skipped_by_budget = [
        item for item in skipped_files if item.get("reason") == "scan budget exceeded"
    ]
    return {
        "max_text_files": max_text_files,
        "scanned_text_files": scanned_files,
        "budget_exceeded": bool(skipped_by_budget),
        "skipped_text_files": len(skipped_by_budget),
    }


def skipped_path_summary(skipped_files: list[AuditPayload]) -> AuditPayload:
    estimated_files = sum(
        value
        for item in skipped_files
        if isinstance(value := item.get("estimated_text_files"), int)
    )
    return {
        "skipped_paths": len(skipped_files),
        "skipped_estimated_text_files": estimated_files,
        "skipped_estimated_scan_seconds": estimated_scan_seconds(estimated_files),
        "skipped_estimate_truncated": any(
            item.get("estimate_truncated") is True for item in skipped_files
        ),
    }


def estimate_text_files(path: Path) -> tuple[int, bool]:
    if not path.is_dir():
        return 0, False

    count = 0
    for current_root, dir_names, file_names in os.walk(path):
        dir_names[:] = sorted(
            name for name in dir_names if not (Path(current_root) / name).is_symlink()
        )
        for file_name in sorted(file_names):
            file_path = Path(current_root) / file_name
            if file_path.is_symlink() or not file_path.is_file():
                continue
            if is_text_file(file_path):
                count += 1
                if count >= DEFAULT_SKIPPED_PATH_ESTIMATE_LIMIT:
                    return count, True
    return count, False


def estimated_scan_seconds(estimated_files: int) -> float:
    if estimated_files <= 0:
        return 0.0
    return max(0.1, round(estimated_files * ESTIMATED_SCAN_SECONDS_PER_TEXT_FILE, 1))


def is_text_file(path: Path) -> bool:
    return path.suffix in TEXT_EXTENSIONS or path.name in TEXT_FILE_NAMES
