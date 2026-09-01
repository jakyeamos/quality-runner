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
    findings.extend(_derived_expected_findings(relative_path, cases))
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


def _derived_expected_findings(
    relative_path: str,
    cases: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for case in cases:
        body = str(case["body"])
        aliases = _derived_aliases(relative_path, body)
        for match in _derived_assertions(relative_path, body, aliases):
            actual = str(match["actual"])
            expected = str(match["expected"])
            line = _case_line(relative_path, case, body, int(match["offset"]))
            findings.append(
                finding(
                    category="improve-tests",
                    severity="observation",
                    confidence="medium",
                    file=relative_path,
                    line=line,
                    rule_id="weak-test-assertion",
                    evidence=(
                        f"assertion compares {actual} with {expected}, where {expected} was "
                        f"directly derived from {actual}"
                    ),
                    expected_improvement=(
                        "Derive the expected value independently from the behavior under test, "
                        "then assert the externally observable result."
                    ),
                    risk=(
                        "An expected value copied from the observed value can pass while the "
                        "underlying behavior is wrong."
                    ),
                    verification=verification_for_path(relative_path),
                    remediation_bucket="tests, E2E, scripts, CI cleanup",
                    suggested_disposition="insufficient_evidence",
                    disposition_rationale=(
                        "The static data-flow match is suspicious but requires review of the "
                        "test's intended oracle."
                    ),
                    evidence_needed=[
                        "Confirm the expected value is independently specified rather than an alias of the actual result."
                    ],
                    subtype="derived-expected",
                )
            )
        for match in _mock_echo_assertions(relative_path, body):
            mock = str(match["mock"])
            expected = str(match["expected"])
            line = _case_line(relative_path, case, body, int(match["offset"]))
            findings.append(
                finding(
                    category="improve-tests",
                    severity="observation",
                    confidence="low",
                    file=relative_path,
                    line=line,
                    rule_id="weak-test-assertion",
                    evidence=(
                        f"mock interaction assertion uses {expected}, read from {mock}'s recorded call data"
                    ),
                    expected_improvement=(
                        "Assert the contract input or output independently of the mock's recorded call history."
                    ),
                    risk=(
                        "An assertion that re-reads a mock's own call record can validate the recorder "
                        "rather than the interaction."
                    ),
                    verification=verification_for_path(relative_path),
                    remediation_bucket="tests, E2E, scripts, CI cleanup",
                    suggested_disposition="insufficient_evidence",
                    disposition_rationale=(
                        "The mock/data-flow pattern needs review to distinguish an echo of the "
                        "recorder from a deliberate interaction assertion."
                    ),
                    evidence_needed=[
                        "Confirm the expected call argument originates outside the mock's call history."
                    ],
                    subtype="mock-echo",
                )
            )
    return findings


def _derived_aliases(relative_path: str, body: str) -> dict[str, str]:
    if relative_path.endswith(".py"):
        pattern = re.compile(
            r"(?:^|[;\n])\s*(?P<expected>[A-Za-z_]\w*)\s*=\s*"
            r"(?P<actual>[A-Za-z_]\w*)\s*;?(?=\s*(?:[;\n]|$))",
            re.MULTILINE,
        )
    else:
        pattern = re.compile(
            r"(?:^|[;\n])\s*(?:const|let|var)\s+"
            r"(?P<expected>[A-Za-z_$][\w$]*)\s*=\s*"
            r"(?P<actual>[A-Za-z_$][\w$]*)\s*;?(?=\s*(?:[;\n]|$))",
            re.MULTILINE,
        )
    aliases: dict[str, str] = {}
    for match in pattern.finditer(body):
        expected = match.group("expected")
        actual = match.group("actual")
        if expected.lower().replace("_", "") in {
            "expected",
            "want",
            "oracle",
            "expectedvalue",
        }:
            aliases[expected] = actual
    return aliases


def _derived_assertions(
    relative_path: str,
    body: str,
    aliases: dict[str, str],
) -> list[dict[str, Any]]:
    if not aliases:
        return []
    if relative_path.endswith(".py"):
        pattern = re.compile(
            r"\bassert\s+(?P<actual>[A-Za-z_]\w*)\s*==\s*(?P<expected>[A-Za-z_]\w*)"
        )
    else:
        pattern = re.compile(
            r"\bexpect\(\s*(?P<actual>[A-Za-z_$][\w$]*)\s*\)\.(?:toBe|toEqual|toStrictEqual)\(\s*(?P<expected>[A-Za-z_$][\w$]*)\s*\)"
        )
    return [
        {**match.groupdict(), "offset": match.start()}
        for match in pattern.finditer(body)
        if aliases.get(match.group("expected")) == match.group("actual")
    ]


def _mock_echo_assertions(relative_path: str, body: str) -> list[dict[str, Any]]:
    mock_path = r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*"
    if relative_path.endswith(".py"):
        recorded = re.compile(
            rf"\b(?P<mock>{mock_path})\.assert_called_(?:once_)?with\s*\(\s*"
            r"(?P<expected>[A-Za-z_]\w*)\s*\)"
        )
        aliases = {
            match.group("expected"): match.group("mock")
            for match in re.finditer(
                rf"(?:^|[;\n])\s*(?P<expected>[A-Za-z_]\w*)\s*=\s*"
                rf"(?P<mock>{mock_path})\.call_args\.args\[\d+\]"
                r"\s*;?(?=\s*(?:[;\n]|$))",
                body,
                re.MULTILINE,
            )
        }
        matches: list[dict[str, Any]] = []
        for match in recorded.finditer(body):
            mock = match.group("mock")
            expected = match.group("expected")
            if aliases.get(expected) == mock:
                matches.append({"mock": mock, "expected": expected, "offset": match.start()})
        return matches
    aliases = {
        match.group("expected"): match.group("mock")
        for match in re.finditer(
            rf"(?:^|[;\n])\s*(?:const|let|var)\s+(?P<expected>[A-Za-z_$][\w$]*)\s*=\s*"
            rf"(?P<mock>{mock_path})\.mock\.calls\[\d+\]\[\d+\]"
            r"\s*;?(?=\s*(?:[;\n]|$))",
            body,
            re.MULTILINE,
        )
    }
    pattern = re.compile(
        rf"\bexpect\(\s*(?P<mock>{mock_path})\s*\)\.toHaveBeen(?:CalledWith|LastCalledWith)\(\s*"
        r"(?P<expected>[A-Za-z_$][\w$]*)\s*\)"
    )
    return [
        {**match.groupdict(), "offset": match.start()}
        for match in pattern.finditer(body)
        if aliases.get(match.group("expected")) == match.group("mock")
    ]


def _case_line(
    relative_path: str,
    case: Mapping[str, Any],
    body: str,
    offset: int,
) -> int:
    header_line = int(case["line"])
    body_line_offset = 0 if not relative_path.endswith(".py") else 1
    return header_line + body_line_offset + body.count("\n", 0, offset)
