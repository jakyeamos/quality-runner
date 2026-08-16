from __future__ import annotations

import ast
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from quality_runner.code_quality_findings import finding
from quality_runner.code_quality_paths import is_test_file, verification_for_path

_JS_TEST_HEADER = re.compile(r"\b(?:it|test)\s*\(\s*(?P<quote>['\"])(?P<name>.*?)(?P=quote)\s*,")
_REMOVAL_NAME = re.compile(
    r"\b(?:removed|deleted|retired|no longer|stays? gone|remains? gone)\b",
    re.IGNORECASE,
)
_JS_ABSENCE_ASSERTION = re.compile(
    r"(?:\.not\.toBeInTheDocument\s*\(|queryBy(?:Text|Role|TestId|LabelText)\s*\([^\n]+"
    r"(?:toBeNull|not\.toBeInTheDocument)\s*\()",
    re.IGNORECASE,
)
_PY_ABSENCE_ASSERTION = re.compile(
    r"\bassert\s+(?:[^\n]+\s+not\s+in\s+[^\n]+|[^\n]+\s+is\s+None)\b",
    re.IGNORECASE,
)


def test_file_quality_findings(relative_path: str, text: str) -> list[dict[str, Any]]:
    if not is_test_file(relative_path):
        return []
    cases = _extract_test_cases(relative_path, text)
    findings: list[dict[str, Any]] = []
    for case in cases:
        normalized_name = re.sub(r"[_-]+", " ", case["name"])
        if not _REMOVAL_NAME.search(normalized_name):
            continue
        body = case["body"]
        if not _contains_only_absence_assertions(relative_path, body):
            continue
        findings.append(
            finding(
                category="improve-tests",
                severity="observation",
                confidence="high",
                file=relative_path,
                line=case["line"],
                rule_id="removed-behavior-lock",
                evidence=f"test {case['name']!r} asserts only that explicitly removed behavior is absent",
                expected_improvement=(
                    "Delete a tombstone test whose sole subject is intentionally removed behavior. "
                    "If the behavior is requested again, test the newly restored contract then."
                ),
                risk=(
                    "Absence-only tombstones preserve implementation history instead of durable behavior "
                    "and add suite cost without protecting an accidental regression path."
                ),
                verification=verification_for_path(relative_path),
                remediation_bucket="tests, E2E, scripts, CI cleanup",
                suggested_disposition="delete_candidate",
                disposition_rationale=(
                    "The test name explicitly identifies removal and its body contains an absence assertion."
                ),
                evidence_needed=[
                    "Confirm the absence is not itself a durable safety, authorization, or compatibility contract."
                ],
            )
        )
    return findings


def duplicate_test_findings(
    scanned_files: Sequence[Mapping[str, object]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for scanned_file in scanned_files:
        relative_path = scanned_file.get("path")
        text = scanned_file.get("text")
        if not isinstance(relative_path, str) or not isinstance(text, str):
            continue
        if not is_test_file(relative_path):
            continue
        language = "python" if relative_path.endswith(".py") else "javascript"
        for case in _extract_test_cases(relative_path, text):
            normalized = _normalize_body(case["body"])
            if len(normalized) >= 40:
                groups[(language, normalized)].append({"file": relative_path, **case})

    findings: list[dict[str, Any]] = []
    for cases in groups.values():
        if len(cases) < 2:
            continue
        ordered = sorted(cases, key=lambda item: (str(item["file"]), int(item["line"])))
        first = ordered[0]
        locations = ", ".join(f"{case['file']}:{case['line']}" for case in ordered[:4])
        findings.append(
            finding(
                category="improve-tests",
                severity="observation",
                confidence="medium",
                file=str(first["file"]),
                line=int(first["line"]),
                rule_id="exact-duplicate-test-body",
                evidence=f"identical test bodies at {locations}",
                expected_improvement=(
                    "Merge tests that exercise the same contract, or parameterize only when the cases "
                    "share a failure mode and oracle."
                ),
                risk="Copied test bodies drift and multiply maintenance and execution cost.",
                verification=verification_for_path(str(first["file"])),
                remediation_bucket="tests, E2E, scripts, CI cleanup",
                suggested_disposition="merge",
                disposition_rationale=(
                    "The normalized test bodies are identical; names and locations remain separate evidence."
                ),
                evidence_needed=[
                    "Confirm both tests fail for the same production mutation before consolidating them."
                ],
            )
        )
    return findings


def _extract_test_cases(relative_path: str, text: str) -> list[dict[str, Any]]:
    if relative_path.endswith(".py"):
        return _extract_python_test_cases(text)
    return _extract_javascript_test_cases(text)


def _extract_javascript_test_cases(text: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for match in _JS_TEST_HEADER.finditer(text):
        opening_brace = text.find("{", match.end())
        if opening_brace < 0:
            continue
        closing_brace = _matching_javascript_brace(text, opening_brace)
        if closing_brace is None:
            continue
        cases.append(
            {
                "name": match.group("name"),
                "body": text[opening_brace + 1 : closing_brace],
                "line": text.count("\n", 0, match.start()) + 1,
            }
        )
    return cases


def _matching_javascript_brace(text: str, opening_brace: int) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening_brace
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and following == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and following == "*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _extract_python_test_cases(text: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    cases: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_") or not node.body:
            continue
        body = "\n".join(ast.get_source_segment(text, item) or "" for item in node.body)
        cases.append({"name": node.name, "body": body, "line": node.lineno})
    return cases


def _normalize_body(body: str) -> str:
    return re.sub(r"\s+", "", body)


def _contains_only_absence_assertions(relative_path: str, body: str) -> bool:
    if relative_path.endswith(".py"):
        assertions = re.findall(r"^\s*assert\b[^\n]*", body, re.MULTILINE)
        absence_assertions = _PY_ABSENCE_ASSERTION.findall(body)
    else:
        assertions = re.findall(r"\bexpect\s*\(", body)
        absence_assertions = _JS_ABSENCE_ASSERTION.findall(body)
    return bool(assertions) and len(assertions) == len(absence_assertions)
