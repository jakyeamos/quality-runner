from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.code_quality_architecture import _path_matches_any
from quality_runner.code_quality_findings import _finding
from quality_runner.schema_constants import SKILL_REVIEW_PACKET_SCHEMA, SKILL_REVIEW_REPORT_SCHEMA

ACCEPTED_SEVERITIES = frozenset({"warning", "observation"})
ACCEPTED_CONFIDENCE = frozenset({"high", "medium", "low"})


def build_skill_review_packet(
    *,
    run_id: str | None,
    repo_root: Path,
    scanned_files: list[dict[str, Any]],
    skills: list[dict[str, Any]],
) -> dict[str, Any] | None:
    reviews = _active_reviews(skills)
    if not reviews:
        return None

    included_files = _included_files(scanned_files, reviews)
    return {
        "schema": SKILL_REVIEW_PACKET_SCHEMA,
        "run_id": run_id,
        "repo_root": str(repo_root.expanduser().resolve()),
        "active_skill_ids": sorted({str(skill["id"]) for skill in skills}),
        "reviews": reviews,
        "included_files": included_files,
        "output_schema": SKILL_REVIEW_REPORT_SCHEMA,
        "instructions": _packet_instructions(),
        "review_policy": {
            "recall_preference": "high",
            "allow_low_confidence": True,
            "require_file_line_evidence": True,
            "do_not_invent_evidence": True,
        },
        "safety": {
            "do_not_edit_source": True,
            "do_not_execute_remediation": True,
            "evidence_backed_findings_only": True,
        },
    }


def render_skill_review_packet_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Quality Runner Skill Review Packet",
        "",
        f"- Schema: {packet.get('schema')}",
        f"- Run id: {packet.get('run_id')}",
        f"- Repo root: {packet.get('repo_root')}",
        "",
        "## Safety",
        "",
        "- Do not edit source files.",
        "- Do not execute remediation.",
        "- Produce evidence-backed findings only.",
        "",
        "## Review policy",
        "",
        "- Prefer high recall and report plausible evidence-backed issues.",
        "- Use low confidence when certainty is limited.",
        "- Never invent file or line evidence.",
        "",
        "## Reviews",
        "",
    ]

    reviews = packet.get("reviews")
    if isinstance(reviews, list):
        for review in reviews:
            if not isinstance(review, dict):
                continue
            lines.extend(
                [
                    f"### {review.get('skill_id')}/{review.get('review_id')}",
                    "",
                    f"- Skill: {review.get('skill_name')}",
                    f"- Paths: {', '.join(review.get('paths', []))}",
                    "",
                    "#### Rubric",
                    "",
                    str(review.get("rubric", "")).strip(),
                    "",
                ]
            )
            focus = review.get("focus")
            if isinstance(focus, list) and focus:
                lines.append("#### Focus")
                lines.append("")
                for item in focus:
                    lines.append(f"- {item}")
                lines.append("")

    lines.extend(
        [
            "## Output",
            "",
            f"Return JSON using schema `{packet.get('output_schema')}`.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def validate_skill_review_report(
    report: dict[str, Any],
    *,
    skills: list[dict[str, Any]] | None = None,
    repo_root: Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    rejected: list[dict[str, Any]] = []

    schema = report.get("schema")
    if schema != SKILL_REVIEW_REPORT_SCHEMA:
        errors.append(f"unsupported schema: {schema}")

    if run_id is not None:
        report_run_id = report.get("run_id")
        if report_run_id != run_id:
            errors.append(f"run_id mismatch: expected {run_id}, got {report_run_id}")

    active_reviews = _review_index(skills or [])
    findings = report.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        return _validation_result(errors=errors, accepted=[], rejected=[])

    accepted: list[dict[str, Any]] = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            rejected.append({"index": index, "reason": "finding must be an object"})
            continue
        rejection = _validate_report_finding(
            finding,
            active_reviews=active_reviews,
            repo_root=repo_root,
        )
        if rejection is not None:
            rejected.append({"index": index, "reason": rejection})
            continue
        accepted.append(_normalize_report_finding(finding))

    accepted.sort(key=_accepted_finding_sort_key)
    return _validation_result(errors=errors, accepted=accepted, rejected=rejected)


def review_report_findings(
    skills: list[dict[str, Any]],
    report: dict[str, Any],
    *,
    repo_root: Path,
) -> list[dict[str, Any]]:
    validation = validate_skill_review_report(report, skills=skills, repo_root=repo_root)
    if validation.get("errors"):
        return []

    accepted = validation.get("accepted")
    if not isinstance(accepted, list):
        return []

    skill_names = {str(skill["id"]): str(skill["name"]) for skill in skills}
    review_categories = {
        (str(skill["id"]), str(review["id"])): str(review.get("category", ""))
        for skill in skills
        for review in skill.get("agent_reviews", [])
        if isinstance(review, dict) and isinstance(review.get("id"), str)
    }
    findings: list[dict[str, Any]] = []
    for item in accepted:
        skill_id = str(item["skill_id"])
        skill_name = skill_names.get(skill_id, skill_id)
        severity = str(item["severity"])
        confidence = str(item["confidence"])
        file = str(item["file"])
        finding = _finding(
            category=f"skill:{skill_id}",
            severity=severity,
            confidence=confidence,
            file=file,
            line=int(item["line"]),
            rule_id=str(item["rule_id"]),
            evidence=str(item["evidence"]),
            expected_improvement=str(item["expected_improvement"]),
            risk=str(item["risk"]),
            verification=str(item["verification"]),
            remediation_bucket=f"Skill: {skill_name}",
            rule_category=review_categories.get((skill_id, str(item["review_id"])), ""),
        )
        finding["skill_id"] = skill_id
        finding["review_id"] = str(item["review_id"])
        findings.append(finding)
    return findings


def _active_reviews(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for skill in skills:
        skill_id = str(skill["id"])
        skill_name = str(skill["name"])
        for review in skill.get("agent_reviews", []):
            if not isinstance(review, dict):
                continue
            review_id = review.get("id")
            paths = review.get("paths")
            rubric = review.get("rubric")
            if not isinstance(review_id, str) or not review_id:
                continue
            if not isinstance(paths, list) or not paths:
                continue
            if not isinstance(rubric, str) or not rubric:
                continue
            reviews.append(
                {
                    "skill_id": skill_id,
                    "skill_name": skill_name,
                    "review_id": review_id,
                    "paths": [item for item in paths if isinstance(item, str)],
                    "rubric": rubric.strip(),
                    "focus": [item for item in review.get("focus", []) if isinstance(item, str)],
                    "severity": review.get("severity")
                    if review.get("severity") in ACCEPTED_SEVERITIES
                    else "observation",
                }
            )
    return sorted(reviews, key=lambda item: (item["skill_id"], item["review_id"]))


def _included_files(
    scanned_files: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    path_patterns: list[str] = []
    for review in reviews:
        path_patterns.extend(review.get("paths", []))

    included: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _path_matches_any(relative_path, path_patterns):
            continue
        lines = item.get("lines")
        line_count = len(lines) if isinstance(lines, list) else 0
        included.append({"path": relative_path, "line_count": line_count})
    return sorted(included, key=lambda item: item["path"])


def _review_index(skills: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(skill["id"]), str(review["id"]))
        for skill in skills
        for review in skill.get("agent_reviews", [])
        if isinstance(review, dict) and isinstance(review.get("id"), str)
    }


def _validate_report_finding(
    finding: dict[str, Any],
    *,
    active_reviews: set[tuple[str, str]],
    repo_root: Path | None,
) -> str | None:
    skill_id = finding.get("skill_id")
    review_id = finding.get("review_id")
    if not isinstance(skill_id, str) or not skill_id:
        return "missing skill_id"
    if not isinstance(review_id, str) or not review_id:
        return "missing review_id"
    if (skill_id, review_id) not in active_reviews:
        return "inactive skill or review"

    file = finding.get("file")
    line = finding.get("line")
    evidence = finding.get("evidence")
    if not isinstance(file, str) or not file:
        return "missing file"
    if not isinstance(line, int) or line < 1:
        return "missing or invalid line"
    if not isinstance(evidence, str) or not evidence.strip():
        return "missing evidence"

    if repo_root is not None:
        resolved = (repo_root / file).resolve()
        try:
            resolved.relative_to(repo_root.expanduser().resolve())
        except ValueError:
            return "file outside repo"

    for field in ("summary", "risk", "expected_improvement", "verification"):
        value = finding.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"missing {field}"

    return None


def _normalize_report_finding(finding: dict[str, Any]) -> dict[str, Any]:
    skill_id = str(finding["skill_id"])
    review_id = str(finding["review_id"])
    rule_id = finding.get("rule_id")
    if not isinstance(rule_id, str) or not rule_id:
        rule_id = f"{skill_id}/{review_id}/finding"

    severity = finding.get("severity")
    if severity not in ACCEPTED_SEVERITIES:
        severity = "observation"

    confidence = finding.get("confidence")
    if confidence not in ACCEPTED_CONFIDENCE:
        confidence = "medium"

    return {
        "skill_id": skill_id,
        "review_id": review_id,
        "rule_id": rule_id,
        "severity": severity,
        "confidence": confidence,
        "file": str(finding["file"]),
        "line": int(finding["line"]),
        "summary": str(finding["summary"]).strip(),
        "evidence": str(finding["evidence"]).strip(),
        "risk": str(finding["risk"]).strip(),
        "expected_improvement": str(finding["expected_improvement"]).strip(),
        "verification": str(finding["verification"]).strip(),
    }


def _accepted_finding_sort_key(item: dict[str, Any]) -> tuple[str, str, str, int, str]:
    return (
        str(item["skill_id"]),
        str(item["review_id"]),
        str(item["file"]),
        int(item["line"]),
        str(item["rule_id"]),
    )


def _validation_result(
    *,
    errors: list[str],
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "quality-runner-skill-review-validation-v0.1",
        "status": "rejected" if errors else "accepted",
        "passed": not errors,
        "errors": errors,
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }


def _packet_instructions() -> str:
    return (
        "Review the listed files against each rubric. Prefer high recall: report every "
        "plausible issue that has concrete file/line evidence, using observation severity "
        "and low confidence when appropriate. Do not invent evidence, edit source files, "
        "or execute remediation. Return JSON using the required output schema."
    )
