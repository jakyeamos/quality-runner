from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.artifacts import write_json, write_text
from quality_runner.code_quality import create_code_quality_scan
from quality_runner.core.audit_contracts import TextScanScope
from quality_runner.skill_config import load_active_skills
from quality_runner.skill_review import (
    build_skill_review_packet,
    render_skill_review_packet_markdown,
    validate_skill_review_report,
)


def create_code_quality_scan_with_skills(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
    skill_review_report: dict[str, Any] | None,
    text_scan_scope: TextScanScope | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    _, skill_warnings = load_active_skills(repo_root, config)
    code_quality_scan = create_code_quality_scan(
        repo_root,
        scan=scan,
        config=config,
        skill_review_report=skill_review_report,
        text_scan_scope=text_scan_scope,
    )
    return code_quality_scan, skill_warnings


def append_warnings(scan: dict[str, Any], extra: list[dict[str, str]]) -> dict[str, Any]:
    if not extra:
        return scan
    merged = dict(scan)
    existing = merged.get("warnings")
    warnings = (
        [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    )
    warnings.extend(extra)
    merged["warnings"] = warnings
    return merged


def write_skill_review_artifacts(
    *,
    run_dir: Path,
    run_id: str,
    repo_root: Path,
    config: dict[str, Any],
    code_quality_scan: dict[str, Any],
    skill_review_report: dict[str, Any] | None,
) -> dict[str, str]:
    skills, _warnings = load_active_skills(repo_root, config)
    if not skills:
        return {}

    accountability = code_quality_scan.get("accountability")
    scanned_files = []
    if isinstance(accountability, list):
        for item in accountability:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            line_count = item.get("line_count")
            if isinstance(path, str) and isinstance(line_count, int):
                scanned_files.append({"path": path, "lines": [""] * line_count})

    artifact_paths: dict[str, str] = {}
    packet = build_skill_review_packet(
        run_id=run_id,
        repo_root=repo_root,
        scanned_files=scanned_files,
        skills=skills,
    )
    if packet is not None:
        artifact_paths["skill_review_packet_json"] = str(
            write_json(run_dir / "skill-review-packet.json", packet)
        )
        artifact_paths["skill_review_packet_md"] = str(
            write_text(
                run_dir / "skill-review-packet.md",
                render_skill_review_packet_markdown(packet),
            )
        )

    if skill_review_report is not None:
        validation = validate_skill_review_report(
            skill_review_report,
            skills=skills,
            repo_root=repo_root,
            run_id=run_id,
        )
        if validation.get("passed") is True:
            artifact_paths["skill_review_report_json"] = str(
                write_json(run_dir / "skill-review-report.json", skill_review_report)
            )
    return artifact_paths


def load_skill_review_report_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("skill review report must be a JSON object")
    return payload
