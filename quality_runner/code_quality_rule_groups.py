from __future__ import annotations

import re
from typing import Any

from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import (
    _has_todo_comment,
    _is_javascript_source_file,
    _is_page_file,
    _is_runtime_file,
    _is_test_file,
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
        (
            "wildcard-cors-origin",
            r"(?:Access-Control-Allow-Origin|origin)\s*[:=]\s*['\"]\*['\"]|cors\(\s*{[^}]*origin\s*:\s*['\"]\*['\"]",
            "Restrict CORS origins to known production hosts.",
            "Wildcard CORS can expose authenticated or internal APIs cross-origin.",
        ),
        (
            "unsafe-html-injection",
            r"\bdangerouslySetInnerHTML\b|\.innerHTML\s*=",
            "Render escaped text or sanitize trusted HTML at the boundary.",
            "HTML sinks can become XSS when external data reaches them.",
        ),
        (
            "eval-user-code",
            r"\beval\s*\(|\bnew\s+Function\s*\(",
            "Replace dynamic code execution with explicit parsing or dispatch.",
            "Dynamic evaluation turns data into executable code.",
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
        if re.search(pattern, line, re.IGNORECASE)
    ]
    if _has_sql_string_interpolation(line):
        findings.append(
            _finding(
                category="harden",
                severity="warning",
                confidence="high",
                file=relative_path,
                line=line_number,
                rule_id="sql-string-interpolation",
                evidence=line,
                expected_improvement="Use parameterized queries or the ORM parameter API.",
                risk="Interpolated SQL strings can turn external input into injection risk.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="API hardening and type safety",
            )
        )
    if re.search(
        r"\b(?:exec|execFile|execSync|spawn|spawnSync)\s*\(",
        line,
    ) and re.search(r"\b(?:req|request|params|body|query|input|argv)\b|\$\{", line):
        findings.append(
            _finding(
                category="harden",
                severity="warning",
                confidence="high",
                file=relative_path,
                line=line_number,
                rule_id="user-controlled-shell-command",
                evidence=line,
                expected_improvement="Map user input to allowlisted command arguments.",
                risk="External input in shell execution can become command injection.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="API hardening and unsafe sink cleanup",
            )
        )
    if re.search(
        r"\b(?:readFile|writeFile|unlink|rm|open|createReadStream|createWriteStream)\s*\(",
        line,
    ) and re.search(r"\b(?:req|request|params|body|query|input|argv)\b", line):
        findings.append(
            _finding(
                category="harden",
                severity="warning",
                confidence="high",
                file=relative_path,
                line=line_number,
                rule_id="user-controlled-file-path",
                evidence=line,
                expected_improvement="Resolve paths through an allowlisted root and reject traversal.",
                risk="External input in file paths can read, overwrite, or delete unintended files.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="API hardening and unsafe sink cleanup",
            )
        )
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


def _has_sql_string_interpolation(line: str) -> bool:
    if "`" not in line or "${" not in line:
        return False
    sql_shapes = (
        r"`[^`]*\bSELECT\b[\s\S]*\bFROM\b[^`]*\$\{",
        r"`[^`]*\bINSERT\s+INTO\b[^`]*\$\{",
        r"`[^`]*\bUPDATE\b[^`]*\bSET\b[^`]*\$\{",
        r"`[^`]*\bDELETE\s+FROM\b[^`]*\$\{",
        r"`[^`]*\bWITH\s+\w+\s+AS\s*\([^`]*\$\{",
        r"`[^`]*\bALTER\s+TABLE\b[^`]*\$\{",
        r"`[^`]*\bDROP\s+(?:TABLE|DATABASE|INDEX)\b[^`]*\$\{",
    )
    return any(re.search(pattern, line, re.IGNORECASE) for pattern in sql_shapes)


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
