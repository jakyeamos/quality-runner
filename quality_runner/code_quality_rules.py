from __future__ import annotations

import hashlib
import re
from typing import Any

from quality_runner.code_quality_paths import (
    _has_motion_without_reduced_motion,
    _has_todo_comment,
    _is_api_file,
    _is_deep_nesting,
    _is_javascript_source_file,
    _is_page_file,
    _is_router_path,
    _is_runtime_file,
    _is_source_file,
    _is_test_file,
    _is_ui_file,
    _nested_ternary,
    _verification_for_path,
)

CATEGORY_ORDER = [
    "harden",
    "simplify",
    "clarify",
    "deduplicate",
    "speed",
    "improve-tests",
    "ui_structural",
]
CONFIDENCE_WEIGHT = {"high": 3, "medium": 2, "low": 1}
SEVERITY_WEIGHT = {"warning": 3, "observation": 1}


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

        if "clarify" not in disabled_groups:
            findings.extend(_clarify_findings(relative_path, line, index))

        if (
            "speed" not in disabled_groups
            and is_javascript_source
            and loop_depth > 0
            and "await" in stripped
        ):
            findings.append(
                _finding(
                    category="speed",
                    severity="warning",
                    confidence="medium",
                    file=relative_path,
                    line=index,
                    rule_id="await-in-loop",
                    evidence=line,
                    expected_improvement="Batch independent work or document required sequencing.",
                    risk="Sequential async work can become a latency bottleneck.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="performance and batching improvements",
                )
            )

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

    return findings


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


def _finding(
    *,
    category: str,
    severity: str,
    confidence: str,
    file: str,
    line: int,
    rule_id: str,
    evidence: str,
    expected_improvement: str,
    risk: str,
    verification: str,
    remediation_bucket: str,
) -> dict[str, Any]:
    fingerprint = _fingerprint(rule_id, file, evidence)
    return {
        "id": "",
        "fingerprint": fingerprint,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "score": SEVERITY_WEIGHT[severity] * CONFIDENCE_WEIGHT[confidence],
        "file": file,
        "line": line,
        "rule_id": rule_id,
        "evidence": evidence.strip(),
        "expected_improvement": expected_improvement,
        "risk": risk,
        "verification": verification,
        "remediation_bucket": remediation_bucket,
    }


def _fingerprint(rule_id: str, file: str, evidence: str) -> str:
    normalized = " ".join(evidence.strip().split())
    return hashlib.sha256(f"{rule_id}:{file}:{normalized}".encode()).hexdigest()[:16]


def _finding_sort_key(finding: dict[str, Any]) -> tuple[int, int, str, int, str]:
    return (
        -int(finding["score"]),
        CATEGORY_ORDER.index(str(finding["category"])),
        str(finding["file"]),
        int(finding["line"]),
        str(finding["rule_id"]),
    )


def _counts(items: list[dict[str, Any]], field: str, keys: list[str]) -> dict[str, int]:
    counts = {key: 0 for key in keys}
    for item in items:
        value = item.get(field)
        if isinstance(value, str):
            counts[value] = counts.get(value, 0) + 1
    return counts
