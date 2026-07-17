from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.code_quality_skills import scan_quality_skills
from quality_runner.skill_selection import load_selected_skills, repository_skill_signals


def scan_quality_skills_with_selection(
    repo_root: Path,
    scanned_files: list[dict[str, Any]],
    config: dict[str, Any],
    skill_review_report: dict[str, Any] | None = None,
    *,
    require_review_coverage: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    skills, _warnings, selection = load_selected_skills(
        repo_root,
        config,
        repo_signals=repository_skill_signals(repo_root, scanned_files),
    )
    findings, coverage, quality_skills = scan_quality_skills(
        repo_root=repo_root,
        scanned_files=scanned_files,
        config=config,
        skill_review_report=skill_review_report,
        selected_skills=skills,
        require_review_coverage=require_review_coverage,
    )
    return findings, coverage, quality_skills, selection
