from __future__ import annotations

import re
from typing import Any

from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import (
    _has_todo_comment,
    _is_api_file,
    _is_javascript_source_file,
    _is_page_file,
    _is_runtime_file,
    _is_test_file,
    _is_ui_file,
    _verification_for_path,
)


def _harden_findings(relative_path: str, line: str, line_number: int) -> list[dict[str, Any]]:
    if not _is_javascript_source_file(relative_path):
        return []

    rules = [
        (
            "explicit-any",
            r"(?::\s*any\b|\bas\s+any\b|<any>)",
            "Replace `any` with a narrow local type, generic constraint, or existing contract.",
            "Type holes allow runtime shape drift through strict boundaries.",
        ),
        (
            "ts-ignore",
            r"@ts-ignore",
            "Remove the ignore or replace it with a documented `@ts-expect-error`.",
            "Ignored diagnostics can conceal real type drift.",
        ),
        (
            "silent-catch",
            r"catch\s*(?:\([^)]*\))?\s*{\s*}|\.catch\(\s*(?:\(\s*\)\s*)?=>\s*{}\s*\)",
            "Log with context or prove the failure is intentionally ignored.",
            "Silent failures make production debugging harder.",
        ),
        (
            "env-non-null-assertion",
            r"\bprocess\.env\.[A-Z0-9_]+!",
            "Route required env access through validation or fail closed.",
            "Deploy misconfiguration can become runtime crashes.",
        ),
    ]
    findings = [
        _finding(
            category="harden",
            severity="warning",
            confidence="high",
            file=relative_path,
            line=line_number,
            rule_id=rule_id,
            evidence=line,
            expected_improvement=expected,
            risk=risk,
            verification=_verification_for_path(relative_path),
            remediation_bucket="API hardening and type safety",
        )
        for rule_id, pattern, expected, risk in rules
        if re.search(pattern, line)
    ]
    if _is_runtime_file(relative_path) and re.search(
        r"\bconsole\.(?:log|debug|warn|error)\s*\(", line
    ):
        findings.append(
            _finding(
                category="harden",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="console-output",
                evidence=line,
                expected_improvement="Use structured logging or remove runtime console output.",
                risk="Noisy output hides real failures and can leak context.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="API hardening and logging",
            )
        )
    if _is_api_file(relative_path):
        if re.search(r"\bnew\s+TRPCError\s*\(", line):
            findings.append(
                _finding(
                    category="harden",
                    severity="warning",
                    confidence="high",
                    file=relative_path,
                    line=line_number,
                    rule_id="bare-trpc-error",
                    evidence=line,
                    expected_improvement="Use the project typed error taxonomy when available.",
                    risk="Bare tRPC errors weaken downstream error handling.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="API hardening, errors, instrumentation, logging",
                )
            )
        if re.search(
            r"\b(?:publicProcedure|protectedProcedure|adminProcedure)\b", line
        ) and not re.search(r"\binstrumented(?:Public|Protected|Admin)Procedure\b", line):
            findings.append(
                _finding(
                    category="harden",
                    severity="warning",
                    confidence="medium",
                    file=relative_path,
                    line=line_number,
                    rule_id="uninstrumented-trpc-procedure",
                    evidence=line,
                    expected_improvement="Use an instrumented procedure or document an explicit opt-out.",
                    risk="Uninstrumented procedures bypass latency and error visibility.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="API hardening, errors, instrumentation, logging",
                )
            )
        if re.search(
            r"\b(?:bio|name|displayName|username|comment|body|reason|title|label|description|note|notes)\s*:\s*z\.string\(\)",
            line,
        ) or re.search(
            r"\b(?:bio|name|displayName|username|comment|body|reason|title|label|description|note|notes)\s*=\s*z\.string\(\)",
            line,
        ):
            findings.append(
                _finding(
                    category="harden",
                    severity="warning",
                    confidence="medium",
                    file=relative_path,
                    line=line_number,
                    rule_id="raw-free-text-z-string",
                    evidence=line,
                    expected_improvement="Use an appropriate shared text sanitizer or bounded schema.",
                    risk="Raw free-text schemas bypass input hygiene.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="API hardening and input hygiene",
                )
            )
    return findings


def _clarify_findings(relative_path: str, line: str, line_number: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if _has_todo_comment(line):
        findings.append(
            _finding(
                category="clarify",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="todo-comment",
                evidence=line,
                expected_improvement="Resolve the comment or move it into a tracked plan with owner.",
                risk="Inline unresolved work ages into undocumented ambiguity.",
                verification='rg -n "TODO|FIXME|HACK|TBD" affected files',
                remediation_bucket="clarity and hygiene cleanup",
            )
        )
    if _is_page_file(relative_path) and re.search(
        r"\b(?:trpc\.|useQuery\s*\(|useMutation\s*\(|refetchInterval)\b", line
    ):
        findings.append(
            _finding(
                category="clarify",
                severity="warning",
                confidence="high",
                file=relative_path,
                line=line_number,
                rule_id="page-data-access",
                evidence=line,
                expected_improvement="Move data access and derived state into a co-located page hook.",
                risk="Page components with orchestration become hard to test.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="web/mobile clarity and page thinning",
            )
        )
    return findings


def _test_quality_findings(relative_path: str, line: str, line_number: int) -> list[dict[str, Any]]:
    if not _is_test_file(relative_path) or not _is_javascript_source_file(relative_path):
        return []
    findings: list[dict[str, Any]] = []
    if re.search(
        r"\bexpect\(\s*(true|false)\s*\)\.(?:toBe|toEqual|toStrictEqual)\(\s*\1\s*\)", line
    ) or re.search(r"\.toHaveBeenCalled\(\s*\)", line):
        findings.append(
            _finding(
                category="improve-tests",
                severity="warning",
                confidence="high",
                file=relative_path,
                line=line_number,
                rule_id="weak-test-assertion",
                evidence=line,
                expected_improvement="Assert behavior, payload shape, or state transition.",
                risk="Weak tests can pass while behavior regresses.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="tests, E2E, scripts, CI cleanup",
            )
        )
    if "console.log(" in line:
        findings.append(
            _finding(
                category="improve-tests",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="console-output",
                evidence=line,
                expected_improvement="Remove noisy test output or assert it deliberately.",
                risk="Noisy test logs hide real failures.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="tests, E2E, scripts, CI cleanup",
            )
        )
    return findings


def _ui_structural_findings(
    relative_path: str, line: str, line_number: int
) -> list[dict[str, Any]]:
    if not _is_ui_file(relative_path):
        return []
    specs = [
        (
            "gradient-text",
            "background-clip" in line and "text" in line and "gradient(" in line,
            "Use a solid text color; reserve gradients for meaningful surfaces.",
            "Gradient text is a common low-signal visual trope.",
        ),
        (
            "decorative-grid-background",
            "linear-gradient" in line
            and "1px" in line
            and ("90deg" in line or line.count("linear-gradient") > 1),
            "Remove decorative grid backgrounds unless the surface is a real canvas/map/measurement tool.",
            "Decorative grids read as generic AI decoration.",
        ),
        (
            "side-stripe-border",
            bool(re.search(r"border-(?:left|right)\s*:\s*(?:[2-9]|\d{2,})px", line)),
            "Use full borders, background tints, icons, or no accent instead.",
            "Side-stripe accents are a repetitive card/callout trope.",
        ),
        (
            "excessive-border-radius",
            bool(re.search(r"border-radius\s*:\s*(?:3[2-9]|[4-9]\d|\d{3,})px", line)),
            "Keep cards and panels within the project's radius scale.",
            "Over-rounded containers make interfaces feel generic.",
        ),
        (
            "arbitrary-z-index",
            bool(re.search(r"z-index\s*:\s*(?:999|9999|\d{4,})", line)),
            "Use a semantic z-index scale.",
            "Arbitrary stacking values make overlays fragile.",
        ),
        (
            "nested-card-markup",
            line.count('className="card') + line.count("className='card") >= 2,
            "Avoid nesting cards inside cards; flatten the layout or use sections.",
            "Nested cards create heavy, unclear visual hierarchy.",
        ),
        (
            "risky-hidden-reveal",
            bool(
                re.search(r"\b(?:opacity\s*:\s*0|visibility\s*:\s*hidden|display\s*:\s*none)", line)
            ),
            "Ensure reveal animations enhance visible content rather than gating it.",
            "Hidden default content can ship blank in paused/headless renderers.",
        ),
    ]
    return [
        _finding(
            category="ui_structural",
            severity="observation",
            confidence="medium",
            file=relative_path,
            line=line_number,
            rule_id=rule_id,
            evidence=line,
            expected_improvement=expected,
            risk=risk,
            verification=_verification_for_path(relative_path),
            remediation_bucket="UI structural quality",
        )
        for rule_id, matched, expected, risk in specs
        if matched
    ]
