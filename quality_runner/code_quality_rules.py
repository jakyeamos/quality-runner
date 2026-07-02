from __future__ import annotations

import re
from typing import Any

from quality_runner.code_quality_api_rules import _api_contract_findings, _api_line_findings
from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import (
    _has_motion_without_reduced_motion,
    _is_deep_nesting,
    _is_javascript_source_file,
    _is_router_path,
    _is_source_file,
    _is_test_file,
    _is_ui_file,
    _nested_ternary,
    _verification_for_path,
)
from quality_runner.code_quality_rule_groups import (
    _clarify_findings,
    _harden_findings,
    _test_quality_findings,
)
from quality_runner.code_quality_ui_rules import (
    _ui_file_level_findings,
    _ui_structural_findings,
)


def _scan_file(
    *,
    relative_path: str,
    text: str,
    lines: list[str],
    disabled_groups: set[str],
    large_file_lines: int,
    fat_router_lines: int,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    is_javascript_source = _is_javascript_source_file(relative_path)
    block_depth = 0
    loop_depth = 0
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if "simplify" not in disabled_groups and is_javascript_source:
            if _is_deep_nesting(stripped, block_depth):
                findings.append(
                    _finding(
                        category="simplify",
                        severity="warning",
                        confidence="medium",
                        file=relative_path,
                        line=index,
                        rule_id="deep-nesting",
                        evidence=line,
                        expected_improvement=(
                            "Flatten guard clauses, extract decision helpers, or split rendering branches."
                        ),
                        risk="Deeply nested flow is hard to review and easy to change incorrectly.",
                        verification=_verification_for_path(relative_path),
                        remediation_bucket="simplification and shrink pass",
                    )
                )
            if _nested_ternary(line):
                findings.append(
                    _finding(
                        category="simplify",
                        severity="warning",
                        confidence="high",
                        file=relative_path,
                        line=index,
                        rule_id="nested-ternary",
                        evidence=line,
                        expected_improvement="Replace nested ternaries with named branches or helpers.",
                        risk="Nested ternaries hide branch behavior.",
                        verification=_verification_for_path(relative_path),
                        remediation_bucket="simplification and shrink pass",
                    )
                )

        if "harden" not in disabled_groups:
            findings.extend(_harden_findings(relative_path, line, index))
            findings.extend(_api_line_findings(relative_path, line, index))

        if "clarify" not in disabled_groups:
            findings.extend(_clarify_findings(relative_path, line, index))

        if (
            "speed" not in disabled_groups
            and is_javascript_source
            and loop_depth > 0
            and "await" in stripped
        ):
            finding = _await_in_loop_finding(relative_path, line, index, lines)
            if finding is not None:
                findings.append(finding)

        if "improve-tests" not in disabled_groups:
            findings.extend(_test_quality_findings(relative_path, line, index))

        if "ui_structural" not in disabled_groups:
            findings.extend(_ui_structural_findings(relative_path, line, index))

        if is_javascript_source:
            if stripped.startswith(("for ", "for(", "for await", "while ", "while(")):
                loop_depth += 1
            block_depth = max(0, block_depth + line.count("{") - line.count("}"))
            if stripped.startswith("}") and loop_depth > 0:
                loop_depth -= 1

    if "simplify" not in disabled_groups and _is_source_file(relative_path):
        if len(lines) > large_file_lines and not _is_test_file(relative_path):
            findings.append(
                _finding(
                    category="simplify",
                    severity="warning",
                    confidence="high",
                    file=relative_path,
                    line=1,
                    rule_id="large-source-file",
                    evidence=f"{len(lines)} lines",
                    expected_improvement="Split mixed responsibilities into focused modules.",
                    risk="Large files increase review cost and refactor risk.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="simplification and shrink pass",
                )
            )
        if _is_router_path(relative_path) and len(lines) > fat_router_lines:
            findings.append(
                _finding(
                    category="simplify",
                    severity="warning",
                    confidence="high",
                    file=relative_path,
                    line=1,
                    rule_id="fat-router",
                    evidence=f"{len(lines)} router lines",
                    expected_improvement=(
                        "Keep routers focused on validation, authorization, delegation, and response shaping."
                    ),
                    risk="Fat routers mix API boundary and domain logic.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="simplification and shrink pass",
                )
            )

    if (
        "ui_structural" not in disabled_groups
        and _is_ui_file(relative_path)
        and _has_motion_without_reduced_motion(text)
    ):
        findings.append(
            _finding(
                category="ui_structural",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=1,
                rule_id="missing-reduced-motion",
                evidence="motion properties without prefers-reduced-motion fallback",
                expected_improvement="Add a reduced-motion alternative for animation or transition.",
                risk="Motion-sensitive users may get inaccessible UI.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="UI structural quality",
            )
        )

    if "ui_structural" not in disabled_groups:
        findings.extend(_ui_file_level_findings(relative_path, text, lines))

    if "harden" not in disabled_groups or "speed" not in disabled_groups:
        findings.extend(
            finding
            for finding in _api_contract_findings(relative_path, text, lines)
            if str(finding["category"]) not in disabled_groups
        )

    return findings


def _await_in_loop_finding(
    relative_path: str, line: str, line_number: int, lines: list[str]
) -> dict[str, Any] | None:
    context = "\n".join(lines[max(0, line_number - 8) : min(len(lines), line_number + 3)])
    lowered_context = context.lower()
    lowered_line = line.lower()

    if _is_test_file(relative_path) and "expect(" in line:
        return None
    if re.search(r"\breader\.read\s*\(", line):
        return None

    severity = "warning"
    confidence = "medium"
    expected = "Batch independent work or document required sequencing."
    risk = "Sequential async work can become a latency bottleneck."

    if _is_test_file(relative_path):
        severity = "observation"
        confidence = "low"
        expected = "Confirm the loop must stay serial or move independent test setup into a batch."
        risk = "Sequential test utilities can slow suites, but may be deliberate for stability."
    elif "interceptors" in lowered_context or re.search(r"\bawait\s+fn\s*\(", line):
        severity = "observation"
        confidence = "low"
        expected = "Keep interceptor chains serial when each step depends on the previous result."
        risk = "Interceptor awaits are often intentional, but can hide slow extension points."
    elif (
        "while (true)" in lowered_context
        and re.search(r"\b(?:poll|retry|sleep|delay|wait|timeout)\b", lowered_context)
    ) or re.search(r"\b(?:poll|retry|sleep|delay|wait)\b", lowered_line):
        severity = "observation"
        confidence = "low"
        expected = "Confirm polling cadence and timeout bounds are explicit."
        risk = "Polling awaits can be expected, but missing bounds turn them into latency traps."

    return _finding(
        category="speed",
        severity=severity,
        confidence=confidence,
        file=relative_path,
        line=line_number,
        rule_id="await-in-loop",
        evidence=line,
        expected_improvement=expected,
        risk=risk,
        verification=_verification_for_path(relative_path),
        remediation_bucket="performance and batching improvements",
    )
