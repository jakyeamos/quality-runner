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
from quality_runner.skill_review import review_report_findings


def skill_findings(
    *,
    repo_root: Any,
    scanned_files: list[dict[str, Any]],
    config: dict[str, Any],
    skill_review_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    skills, _warnings = load_active_skills(repo_root, config)
    if not skills:
        return []

    findings: list[dict[str, Any]] = []
    for skill in skills:
        skill_id = str(skill["id"])
        skill_name = str(skill["name"])
        applies_to = skill.get("applies_to")
        path_filter = applies_to if isinstance(applies_to, list) else None

        for rule in skill.get("deterministic_rules", []):
            if not isinstance(rule, dict):
                continue
            rule_type = rule.get("type")
            if rule_type == "disallowed_pattern":
                findings.extend(
                    _disallowed_pattern_findings(
                        scanned_files,
                        skill_id=skill_id,
                        skill_name=skill_name,
                        rule=rule,
                        path_filter=path_filter,
                    )
                )
            elif rule_type == "trigger_without_required":
                findings.extend(
                    _trigger_without_required_findings(
                        scanned_files,
                        skill_id=skill_id,
                        skill_name=skill_name,
                        rule=rule,
                        path_filter=path_filter,
                    )
                )
            elif rule_type == "import_boundary":
                findings.extend(
                    _import_boundary_findings(
                        scanned_files,
                        skill_id=skill_id,
                        skill_name=skill_name,
                        rule=rule,
                        path_filter=path_filter,
                    )
                )

    if skill_review_report is not None:
        findings.extend(review_report_findings(skills, skill_review_report, repo_root=repo_root))

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
        confidence="medium",
        file=file,
        line=line,
        rule_id=_skill_rule_id(skill_id, rule_id),
        evidence=evidence,
        expected_improvement=str(rule["expected"]),
        risk=str(rule["risk"]),
        verification=str(rule.get("verification") or _verification_for_path(file)),
        remediation_bucket=f"Skill: {skill_name}",
    )


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
