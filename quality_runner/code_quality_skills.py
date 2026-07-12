from __future__ import annotations

import re
from typing import Any

from quality_runner.code_quality_architecture import (
    _extract_import_specifiers,
    _import_violates_boundary,
    _path_matches_any,
)
from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import _verification_for_path
from quality_runner.skill_config import load_active_skills
from quality_runner.skill_review import review_report_findings, validate_skill_review_report


def scan_quality_skills(
    *,
    repo_root: Any,
    scanned_files: list[dict[str, Any]],
    config: dict[str, Any],
    skill_review_report: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    skills, _warnings = load_active_skills(repo_root, config)
    if not skills:
        return [], [], []

    findings: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for skill in skills:
        skill_id = str(skill["id"])
        skill_name = str(skill["name"])
        applies_to = skill.get("applies_to")
        path_filter = applies_to if isinstance(applies_to, list) else None

        for rule in skill.get("deterministic_rules", []):
            if not isinstance(rule, dict):
                continue
            paths = _rule_paths(rule, path_filter)
            scoped_files = _scoped_files(scanned_files, paths, path_filter)
            skip_reason = _rule_skip_reason(rule)
            rule_findings: list[dict[str, Any]] = []
            if skip_reason is None:
                rule_type = rule.get("type")
                if rule_type == "disallowed_pattern":
                    rule_findings = _disallowed_pattern_findings(
                        scanned_files,
                        skill_id=skill_id,
                        skill_name=skill_name,
                        rule=rule,
                        path_filter=path_filter,
                    )
                elif rule_type == "trigger_without_required":
                    rule_findings = _trigger_without_required_findings(
                        scanned_files,
                        skill_id=skill_id,
                        skill_name=skill_name,
                        rule=rule,
                        path_filter=path_filter,
                    )
                elif rule_type == "import_boundary":
                    rule_findings = _import_boundary_findings(
                        scanned_files,
                        skill_id=skill_id,
                        skill_name=skill_name,
                        rule=rule,
                        path_filter=path_filter,
                    )
            findings.extend(rule_findings)
            coverage.append(
                _rule_coverage(
                    skill=skill,
                    rule=rule,
                    scoped_files=scoped_files,
                    findings=rule_findings,
                    skip_reason=skip_reason,
                )
            )

    review_findings: list[dict[str, Any]] = []
    review_status = "review_required"
    rejected_review_findings = 0
    if skill_review_report is not None:
        validation = validate_skill_review_report(
            skill_review_report,
            skills=skills,
            repo_root=repo_root,
        )
        rejected_review_findings = int(validation.get("rejected_count") or 0)
        if validation.get("errors"):
            review_status = "review_rejected"
        else:
            review_status = "reviewed"
            review_findings = review_report_findings(
                skills, skill_review_report, repo_root=repo_root
            )
        findings.extend(review_findings)

    for skill in skills:
        skill_id = str(skill["id"])
        applies_to = skill.get("applies_to")
        path_filter = applies_to if isinstance(applies_to, list) else None
        for review in skill.get("agent_reviews", []):
            if not isinstance(review, dict):
                continue
            review_id = str(review["id"])
            paths = [item for item in review.get("paths", []) if isinstance(item, str)]
            scoped_files = _scoped_files(scanned_files, paths, path_filter)
            review_matches = [
                finding
                for finding in review_findings
                if finding.get("skill_id") == skill_id and finding.get("review_id") == review_id
            ]
            review_coverage: dict[str, Any] = {
                "skill_id": skill_id,
                "skill_name": str(skill["name"]),
                "skill_version": str(skill.get("version", "0.1.0")),
                "rule_id": review_id,
                "rule_type": "agent_review",
                "rule_category": str(review.get("category", "")),
                "severity": str(review.get("severity", "observation")),
                "paths": paths,
                "scoped_files": len(scoped_files),
                "matched_files": len({str(item.get("file")) for item in review_matches}),
                "finding_count": len(review_matches),
                "status": review_status,
            }
            if rejected_review_findings:
                review_coverage["rejected_finding_count"] = rejected_review_findings
            coverage.append(review_coverage)

    quality_skills = [
        {
            "id": str(skill["id"]),
            "name": str(skill["name"]),
            "version": str(skill.get("version", "0.1.0")),
            "content_sha256": str(skill.get("content_sha256", "")),
        }
        for skill in sorted(skills, key=lambda item: str(item["id"]))
    ]
    return findings, coverage, quality_skills


def skill_findings(
    *,
    repo_root: Any,
    scanned_files: list[dict[str, Any]],
    config: dict[str, Any],
    skill_review_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    findings, _coverage, _quality_skills = scan_quality_skills(
        repo_root=repo_root,
        scanned_files=scanned_files,
        config=config,
        skill_review_report=skill_review_report,
    )
    return findings


def _skill_category(skill_id: str) -> str:
    return f"skill:{skill_id}"


def _skill_rule_id(skill_id: str, rule_id: str) -> str:
    return f"{skill_id}/{rule_id}"


def _rule_severity(rule: dict[str, Any]) -> str:
    severity = rule.get("severity")
    return severity if severity in {"warning", "observation"} else "warning"


def _rule_paths(rule: dict[str, Any], path_filter: list[str] | None) -> list[str]:
    paths = [item for item in rule.get("paths", []) if isinstance(item, str)]
    if path_filter is None:
        return paths
    return paths or path_filter


def _file_in_scope(relative_path: str, paths: list[str], path_filter: list[str] | None) -> bool:
    if path_filter is not None and not _path_matches_any(relative_path, path_filter):
        return False
    return _path_matches_any(relative_path, paths)


def _skill_finding(
    *,
    skill_id: str,
    skill_name: str,
    rule: dict[str, Any],
    file: str,
    line: int,
    evidence: str,
) -> dict[str, Any]:
    rule_id = str(rule["id"])
    return _finding(
        category=_skill_category(skill_id),
        severity=_rule_severity(rule),
        confidence=_rule_confidence(rule),
        file=file,
        line=line,
        rule_id=_skill_rule_id(skill_id, rule_id),
        evidence=evidence,
        expected_improvement=str(rule["expected"]),
        risk=str(rule["risk"]),
        verification=str(rule.get("verification") or _verification_for_path(file)),
        remediation_bucket=f"Skill: {skill_name}",
        rule_message=str(rule.get("message", "")),
        rule_category=str(rule.get("category", "")),
    )


def _rule_confidence(rule: dict[str, Any]) -> str:
    confidence = rule.get("confidence")
    return confidence if confidence in {"high", "medium", "low"} else "medium"


def _scoped_files(
    scanned_files: list[dict[str, Any]],
    paths: list[str],
    path_filter: list[str] | None,
) -> list[str]:
    return [
        str(item["path"])
        for item in scanned_files
        if isinstance(item.get("path"), str)
        and _file_in_scope(str(item["path"]), paths, path_filter)
    ]


def _compile_regexes(patterns: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error:
            continue
    return compiled


def _rule_skip_reason(rule: dict[str, Any]) -> str | None:
    rule_type = rule.get("type")
    if rule_type not in {"disallowed_pattern", "trigger_without_required", "import_boundary"}:
        return f"unsupported rule type: {rule_type}"
    if not _rule_paths(rule, None):
        return "no paths configured"
    if rule_type == "disallowed_pattern":
        patterns = [item for item in rule.get("disallowed_patterns", []) if isinstance(item, str)]
        if not patterns:
            return "no disallowed_patterns configured"
        if not _compile_regexes(patterns):
            return "all configured disallowed_patterns are invalid regexes"
    elif rule_type == "trigger_without_required":
        triggers = [item for item in rule.get("trigger_patterns", []) if isinstance(item, str)]
        required = [item for item in rule.get("required_patterns", []) if isinstance(item, str)]
        if not triggers or not required:
            return "trigger_patterns and required_patterns are required"
        if not _compile_regexes(triggers):
            return "all configured trigger_patterns are invalid regexes"
        if not _compile_regexes(required):
            return "all configured required_patterns are invalid regexes"
    else:
        disallowed = [item for item in rule.get("disallowed_imports", []) if isinstance(item, str)]
        if not disallowed:
            return "no disallowed_imports configured"
    return None


def _rule_coverage(
    *,
    skill: dict[str, Any],
    rule: dict[str, Any],
    scoped_files: list[str],
    findings: list[dict[str, Any]],
    skip_reason: str | None,
) -> dict[str, Any]:
    if skip_reason is not None:
        status = "skipped"
    elif not scoped_files:
        status = "no_matching_files"
    elif findings:
        status = "matched"
    else:
        status = "evaluated"
    coverage: dict[str, Any] = {
        "skill_id": str(skill["id"]),
        "skill_name": str(skill["name"]),
        "skill_version": str(skill.get("version", "0.1.0")),
        "rule_id": str(rule["id"]),
        "rule_type": str(rule["type"]),
        "rule_category": str(rule.get("category", "")),
        "severity": _rule_severity(rule),
        "confidence": _rule_confidence(rule),
        "paths": [item for item in rule.get("paths", []) if isinstance(item, str)],
        "scoped_files": len(scoped_files),
        "matched_files": len({str(item.get("file")) for item in findings}),
        "finding_count": len(findings),
        "status": status,
    }
    if skip_reason is not None:
        coverage["skipped_reason"] = skip_reason
    return coverage


def _disallowed_pattern_findings(
    scanned_files: list[dict[str, Any]],
    *,
    skill_id: str,
    skill_name: str,
    rule: dict[str, Any],
    path_filter: list[str] | None,
) -> list[dict[str, Any]]:
    paths = _rule_paths(rule, path_filter)
    patterns = [item for item in rule.get("disallowed_patterns", []) if isinstance(item, str)]
    if not paths or not patterns:
        return []

    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error:
            continue
    if not compiled:
        return []

    findings: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _file_in_scope(relative_path, paths, path_filter):
            continue
        lines = item.get("lines")
        if not isinstance(lines, list):
            continue
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, str):
                continue
            for pattern in compiled:
                if not pattern.search(line):
                    continue
                findings.append(
                    _skill_finding(
                        skill_id=skill_id,
                        skill_name=skill_name,
                        rule=rule,
                        file=relative_path,
                        line=index,
                        evidence=line.strip(),
                    )
                )
                break
    return findings


def _trigger_without_required_findings(
    scanned_files: list[dict[str, Any]],
    *,
    skill_id: str,
    skill_name: str,
    rule: dict[str, Any],
    path_filter: list[str] | None,
) -> list[dict[str, Any]]:
    paths = _rule_paths(rule, path_filter)
    trigger_patterns = [item for item in rule.get("trigger_patterns", []) if isinstance(item, str)]
    required_patterns = [
        item for item in rule.get("required_patterns", []) if isinstance(item, str)
    ]
    if not paths or not trigger_patterns or not required_patterns:
        return []

    compiled_triggers: list[re.Pattern[str]] = []
    for pattern in trigger_patterns:
        try:
            compiled_triggers.append(re.compile(pattern))
        except re.error:
            continue
    compiled_required: list[re.Pattern[str]] = []
    for pattern in required_patterns:
        try:
            compiled_required.append(re.compile(pattern))
        except re.error:
            continue
    if not compiled_triggers:
        return []

    findings: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _file_in_scope(relative_path, paths, path_filter):
            continue
        lines = item.get("lines")
        text = item.get("text")
        if not isinstance(lines, list) or not isinstance(text, str):
            continue
        if compiled_required and any(pattern.search(text) for pattern in compiled_required):
            continue
        trigger_line: int | None = None
        trigger_evidence = ""
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, str):
                continue
            if any(pattern.search(line) for pattern in compiled_triggers):
                trigger_line = index
                trigger_evidence = line.strip()
                break
        if trigger_line is not None:
            findings.append(
                _skill_finding(
                    skill_id=skill_id,
                    skill_name=skill_name,
                    rule=rule,
                    file=relative_path,
                    line=trigger_line,
                    evidence=trigger_evidence,
                )
            )
    return findings


def _import_boundary_findings(
    scanned_files: list[dict[str, Any]],
    *,
    skill_id: str,
    skill_name: str,
    rule: dict[str, Any],
    path_filter: list[str] | None,
) -> list[dict[str, Any]]:
    paths = _rule_paths(rule, path_filter)
    disallowed = [item for item in rule.get("disallowed_imports", []) if isinstance(item, str)]
    allowed = [item for item in rule.get("allowed_imports", []) if isinstance(item, str)]
    if not paths or not disallowed:
        return []

    findings: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _file_in_scope(relative_path, paths, path_filter):
            continue
        lines = item.get("lines")
        if not isinstance(lines, list):
            continue
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, str):
                continue
            for specifier in _extract_import_specifiers(line):
                if not _import_violates_boundary(
                    source_file=relative_path,
                    specifier=specifier,
                    disallowed_patterns=disallowed,
                    allowed_patterns=allowed,
                ):
                    continue
                findings.append(
                    _skill_finding(
                        skill_id=skill_id,
                        skill_name=skill_name,
                        rule=rule,
                        file=relative_path,
                        line=index,
                        evidence=line.strip(),
                    )
                )
    return findings
