from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.agent_review_policy import (
    AgentReviewMode,
    review_status_for_mode,
)
from quality_runner.artifacts import write_json, write_text
from quality_runner.cache_modes import CacheMode
from quality_runner.code_quality import create_code_quality_scan
from quality_runner.core.audit_contracts import TextScanScope
from quality_runner.skill_review import (
    build_skill_review_packet,
    render_skill_review_packet_markdown,
    validate_skill_review_report,
)
from quality_runner.skill_selection import load_selected_skills, repository_skill_signals


def create_code_quality_scan_with_skills(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
    skill_review_report: dict[str, Any] | None,
    require_skill_review_coverage: bool = False,
    text_scan_scope: TextScanScope | None = None,
    persist_cache: bool = True,
    analysis_mode: str = "full",
    cache_mode: CacheMode | str = "repo",
    cache_root: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    code_quality_scan = create_code_quality_scan(
        repo_root,
        scan=scan,
        config=config,
        skill_review_report=skill_review_report,
        require_skill_review_coverage=require_skill_review_coverage,
        text_scan_scope=text_scan_scope,
        persist_cache=persist_cache,
        analysis_mode=analysis_mode,
        cache_mode=cache_mode,
        cache_root=cache_root,
    )
    selection = code_quality_scan.get("skill_selection")
    skill_warnings = (
        [item for item in selection.get("warnings", []) if isinstance(item, dict)]
        if isinstance(selection, dict)
        else []
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
    agent_review_mode: AgentReviewMode = "auto",
    require_skill_review_coverage: bool = False,
) -> dict[str, str]:
    selection = code_quality_scan.get("skill_selection")
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

    diagnostic_signals = (
        selection.get("repo_signals")
        if isinstance(selection, dict) and isinstance(selection.get("repo_signals"), list)
        else None
    )
    repo_signals = (
        repository_skill_signals(repo_root, scanned_files) if scanned_files else diagnostic_signals
    )
    skills, _warnings, _selection = load_selected_skills(
        repo_root,
        config,
        repo_signals=repo_signals,
    )
    if not skills:
        return {}

    artifact_paths: dict[str, str] = {}
    if agent_review_mode != "off":
        packet = build_skill_review_packet(
            run_id=run_id,
            repo_root=repo_root,
            scanned_files=scanned_files,
            skills=skills,
        )
        if packet is not None:
            review_policy = packet.get("review_policy")
            if isinstance(review_policy, dict):
                packet["review_policy"] = {
                    **review_policy,
                    "execution_mode": (
                        "automatic" if agent_review_mode == "auto" else "supervised"
                    ),
                    "required_review_count": len(packet.get("reviews", [])),
                }
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
            require_review_coverage=require_skill_review_coverage,
        )
        if validation.get("passed") is True:
            artifact_paths["skill_review_report_json"] = str(
                write_json(run_dir / "skill-review-report.json", skill_review_report)
            )
    return artifact_paths


def skill_review_summary(
    *,
    code_quality_scan: dict[str, Any],
    artifact_paths: dict[str, str],
    skill_review_report: dict[str, Any] | None = None,
    agent_review_mode: AgentReviewMode = "auto",
) -> dict[str, Any] | None:
    coverage = code_quality_scan.get("skill_coverage")
    if not isinstance(coverage, list):
        return None

    reviews = [
        item
        for item in coverage
        if isinstance(item, dict) and item.get("rule_type") == "agent_review"
    ]
    if not reviews:
        return None

    statuses = {str(item.get("status")) for item in reviews}
    unresolved = "reviewed" not in statuses or any(
        str(item.get("status")) != "reviewed" for item in reviews
    )
    status = review_status_for_mode(
        mode=agent_review_mode,
        unresolved=unresolved,
        rejected="review_rejected" in statuses,
    )

    review_ids = sorted(
        f"{item['skill_id']}/{item['rule_id']}"
        for item in reviews
        if isinstance(item.get("skill_id"), str) and isinstance(item.get("rule_id"), str)
    )
    unresolved_review_ids = sorted(
        f"{item['skill_id']}/{item['rule_id']}"
        for item in reviews
        if item.get("status") != "reviewed"
        and isinstance(item.get("skill_id"), str)
        and isinstance(item.get("rule_id"), str)
    )
    summary: dict[str, Any] = {
        "mode": agent_review_mode,
        "status": status,
        "automatic": agent_review_mode == "auto",
        "active_skill_ids": sorted(
            {str(item["skill_id"]) for item in reviews if isinstance(item.get("skill_id"), str)}
        ),
        "review_ids": review_ids,
        "unresolved_review_ids": unresolved_review_ids,
        "review_count": len(review_ids),
        "unresolved_count": len(unresolved_review_ids),
    }
    for artifact_key, summary_key in (
        ("skill_review_packet_json", "packet_json"),
        ("skill_review_packet_md", "packet_markdown"),
        ("skill_review_report_json", "report_json"),
    ):
        path = artifact_paths.get(artifact_key)
        if isinstance(path, str) and path:
            summary[summary_key] = path
    if isinstance(skill_review_report, dict):
        report_run_id = skill_review_report.get("run_id")
        if isinstance(report_run_id, str) and report_run_id:
            summary["report_source_run_id"] = report_run_id
    return summary


def skill_review_markdown(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []

    lines = ["", "## Active Skill Reviews", ""]
    lines.append(f"- Mode: {value.get('mode', 'auto')}")
    lines.append(f"- Status: {value.get('status')}")
    if value.get("automatic") is True:
        lines.append("- Execution: automatic supervising-agent review")
    active_skill_ids = value.get("active_skill_ids")
    if isinstance(active_skill_ids, list) and active_skill_ids:
        lines.append(f"- Active packs: {', '.join(str(item) for item in active_skill_ids)}")
    review_ids = value.get("review_ids")
    if isinstance(review_ids, list) and review_ids:
        lines.append(f"- Reviews: {', '.join(str(item) for item in review_ids)}")
    unresolved = value.get("unresolved_review_ids")
    if isinstance(unresolved, list) and unresolved:
        lines.append(f"- Unresolved reviews: {', '.join(str(item) for item in unresolved)}")

    packet_json = value.get("packet_json")
    packet_markdown = value.get("packet_markdown")
    report_json = value.get("report_json")
    if isinstance(packet_json, str) and packet_json:
        lines.append(f"- Review packet: {packet_json}")
    if isinstance(packet_markdown, str) and packet_markdown != packet_json:
        lines.append(f"- Review packet Markdown: {packet_markdown}")
    if isinstance(report_json, str) and report_json:
        lines.append(f"- Merged review report: {report_json}")
    report_source_run_id = value.get("report_source_run_id")
    if isinstance(report_source_run_id, str) and report_source_run_id:
        lines.append(f"- Report source run: {report_source_run_id}")

    status = value.get("status")
    if status == "review-required":
        lines.extend(
            [
                "",
                "Action required: read the review packet, inspect the scoped files, write the agent review report, and rerun Quality Runner with `--skill-review-report <report.json>`.",
                "Do not treat this handoff as complete until the report is merged and the status becomes `reviewed`.",
            ]
        )
    elif status == "review-rejected":
        lines.extend(
            [
                "",
                "Action required: correct the rejected review report or its evidence, then rerun Quality Runner with `--skill-review-report <report.json>`.",
            ]
        )
    elif status == "review-pending":
        lines.extend(
            [
                "",
                (
                    "The supervising agent should automatically inspect every active review "
                    "rubric and produce the report."
                    if value.get("automatic") is True
                    else "Agent reviews may run in parallel with this QR run."
                ),
                "When complete, rerun Quality Runner with `--skill-review-report <report.json>` to merge the validated report.",
            ]
        )
    elif status == "not-run":
        lines.extend(
            [
                "",
                "Agent reviews were explicitly disabled for this run; deterministic QR checks remain available.",
            ]
        )
    else:
        lines.extend(["", "The active skill-review report was merged into this run."])
    return lines


def load_skill_review_report_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("skill review report must be a JSON object")
    return payload


def quality_skill_identities(code_quality_scan: dict[str, Any]) -> list[dict[str, Any]]:
    skills = code_quality_scan.get("quality_skills")
    if not isinstance(skills, list):
        return []
    return [
        item
        for item in skills
        if isinstance(item, dict)
        and all(
            isinstance(item.get(field), str) and item.get(field)
            for field in (
                "id",
                "name",
                "version",
                "content_sha256",
            )
        )
    ]
