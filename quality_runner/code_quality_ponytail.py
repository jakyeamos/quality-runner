from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import (
    _is_javascript_source_file,
    _is_test_file,
    _verification_for_path,
)

COMMON_ENV_VARS = {
    "CI",
    "HOME",
    "NODE_ENV",
    "PATH",
    "PWD",
    "SHELL",
    "TMPDIR",
    "USER",
}
TRIVIAL_DEPENDENCY_REPLACEMENTS = {
    "axios": ("native", "fetch"),
    "classnames": ("shrink", "a tiny local class join or template literal"),
    "clsx": ("shrink", "a tiny local class join or template literal"),
    "date-fns": ("native", "Intl.DateTimeFormat or Date"),
    "lodash": ("stdlib", "standard Array/Object helpers"),
    "lodash-es": ("stdlib", "standard Array/Object helpers"),
    "moment": ("native", "Intl.DateTimeFormat or Date"),
    "query-string": ("native", "URLSearchParams"),
    "uuid": ("native", "crypto.randomUUID()"),
}


def ponytail_findings(scanned_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    findings.extend(_single_implementation_abstractions(scanned_files))
    findings.extend(_single_product_factories(scanned_files))
    findings.extend(_pass_through_wrappers(scanned_files))
    findings.extend(_undocumented_env_flags(scanned_files))
    findings.extend(_single_use_trivial_dependencies(scanned_files))
    findings.extend(_hand_rolled_native_helpers(scanned_files))
    return findings


def _single_implementation_abstractions(
    scanned_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    code_text = "\n".join(
        str(item["text"]) for item in scanned_files if _is_javascript_source_file(str(item["path"]))
    )
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _is_javascript_source_file(relative_path) or _is_test_file(relative_path):
            continue
        for index, line in enumerate(_lines(item), start=1):
            match = re.search(
                r"\b(?:(interface)|(abstract)\s+class)\s+([A-Z][A-Za-z0-9_]*)\b",
                line,
            )
            if match is None:
                continue
            declarations.append(
                {
                    "name": match.group(3),
                    "kind": "interface" if match.group(1) else "abstract class",
                    "file": relative_path,
                    "line": index,
                    "evidence": line,
                }
            )

    findings: list[dict[str, Any]] = []
    for declaration in declarations:
        name = str(declaration["name"])
        implementation_count = len(
            re.findall(rf"\b(?:implements|extends)\s+[A-Za-z0-9_,\s]*\b{name}\b", code_text)
        )
        if implementation_count != 1:
            continue
        findings.append(
            _ponytail_finding(
                tag="yagni",
                file=str(declaration["file"]),
                line=int(declaration["line"]),
                rule_id="single-implementation-abstraction",
                evidence=str(declaration["evidence"]),
                expected=(
                    f"Inline or collapse the {declaration['kind']} until a second implementation exists."
                ),
                risk="Single-implementation abstractions add indirection without buying flexibility.",
            )
        )
    return findings


def _single_product_factories(scanned_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _is_javascript_source_file(relative_path) or _is_test_file(relative_path):
            continue
        text = str(item["text"])
        symbol = re.search(
            r"\b(?:class|function|const)\s+([A-Za-z0-9_]*(?:Factory|Registry|Strategy))\b", text
        )
        path_name = Path(relative_path).stem
        if symbol is None and not re.search(r"(?:factory|registry|strategy)", path_name, re.I):
            continue
        product_markers = (
            len(re.findall(r"\bcase\s+['\"]", text))
            + len(re.findall(r"\.register\s*\(", text))
            + len(re.findall(r"\.set\s*\(", text))
            + len(re.findall(r"\bnew\s+[A-Z][A-Za-z0-9_]*\s*\(", text))
        )
        if product_markers != 1:
            continue
        line_number, evidence = _first_line(_lines(item), r"\b(?:Factory|Registry|Strategy)\b")
        findings.append(
            _ponytail_finding(
                tag="yagni",
                file=relative_path,
                line=line_number,
                rule_id="single-product-factory",
                evidence=evidence,
                expected="Replace the factory/registry/strategy layer with the direct implementation.",
                risk="A one-product factory preserves speculative flexibility as permanent code.",
            )
        )
    return findings


def _pass_through_wrappers(scanned_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _is_javascript_source_file(relative_path) or _is_test_file(relative_path):
            continue
        lines = _lines(item)
        for start, end, name in _function_blocks(lines):
            body = "\n".join(lines[start + 1 : end]).strip()
            compact = re.sub(r"\s+", " ", body)
            match = re.fullmatch(
                r"return\s+(?:await\s+)?([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\([^;]*\);?",
                compact,
            )
            if match is None or match.group(1).split(".")[-1] == name:
                continue
            findings.append(
                _ponytail_finding(
                    tag="shrink",
                    file=relative_path,
                    line=start + 1,
                    rule_id="pass-through-wrapper",
                    evidence=lines[start],
                    expected="Call the delegated function directly or give the wrapper real policy.",
                    risk="Pass-through wrappers add names and files without reducing caller complexity.",
                )
            )
    return findings


def _undocumented_env_flags(scanned_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    occurrences: dict[str, list[dict[str, Any]]] = {}
    documentation_text = "\n".join(
        str(item["text"])
        for item in scanned_files
        if Path(str(item["path"])).suffix in {".md", ".toml", ".yaml", ".yml"}
    )
    for item in scanned_files:
        relative_path = str(item["path"])
        if _is_test_file(relative_path):
            continue
        for index, line in enumerate(_lines(item), start=1):
            for env_name in _env_names(line):
                if env_name in COMMON_ENV_VARS:
                    continue
                occurrences.setdefault(env_name, []).append(
                    {"file": relative_path, "line": index, "evidence": line}
                )

    findings: list[dict[str, Any]] = []
    for env_name, env_occurrences in sorted(occurrences.items()):
        if len(env_occurrences) != 1 or env_name in documentation_text:
            continue
        occurrence = env_occurrences[0]
        findings.append(
            _ponytail_finding(
                tag="yagni",
                file=str(occurrence["file"]),
                line=int(occurrence["line"]),
                rule_id="undocumented-env-flag",
                evidence=str(occurrence["evidence"]),
                expected=f"Document {env_name} or remove the one-off configuration branch.",
                risk="Undocumented single-read flags become invisible behavior switches.",
            )
        )
    return findings


def _single_use_trivial_dependencies(
    scanned_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    dependencies = _package_dependencies(scanned_files)
    if not dependencies:
        return []

    imports: dict[str, list[dict[str, Any]]] = {}
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _is_javascript_source_file(relative_path) or _is_test_file(relative_path):
            continue
        for index, line in enumerate(_lines(item), start=1):
            package_name = _imported_package(line)
            if package_name is None:
                continue
            imports.setdefault(package_name, []).append(
                {"file": relative_path, "line": index, "evidence": line}
            )

    findings: list[dict[str, Any]] = []
    for package_name, occurrences in sorted(imports.items()):
        if (
            package_name not in dependencies
            or package_name not in TRIVIAL_DEPENDENCY_REPLACEMENTS
            or len(occurrences) != 1
        ):
            continue
        tag, replacement = TRIVIAL_DEPENDENCY_REPLACEMENTS[package_name]
        occurrence = occurrences[0]
        findings.append(
            _ponytail_finding(
                tag=tag,
                file=str(occurrence["file"]),
                line=int(occurrence["line"]),
                rule_id="single-use-trivial-dependency",
                evidence=str(occurrence["evidence"]),
                expected=f"Use {replacement} instead of a one-use dependency.",
                risk="Single-use utility dependencies increase install and supply-chain surface.",
            )
        )
    return findings


def _hand_rolled_native_helpers(scanned_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if _is_test_file(relative_path):
            continue
        is_javascript_source = _is_javascript_source_file(relative_path)
        lines = _lines(item)
        text = str(item["text"])
        for index, line in enumerate(lines, start=1):
            if is_javascript_source and "Math.random().toString(36)" in line:
                findings.append(
                    _ponytail_finding(
                        tag="native",
                        file=relative_path,
                        line=index,
                        rule_id="hand-rolled-uuid",
                        evidence=line,
                        expected="Use crypto.randomUUID() when a random identifier is enough.",
                        risk="Hand-rolled IDs are easy to make collision-prone or biased.",
                    )
                )
            if is_javascript_source and re.search(
                r"\.split\(['\"]&['\"]\).+\.split\(['\"]=['\"]\)", line
            ):
                findings.append(
                    _ponytail_finding(
                        tag="native",
                        file=relative_path,
                        line=index,
                        rule_id="hand-rolled-url-parser",
                        evidence=line,
                        expected="Use URLSearchParams or URL for query parsing.",
                        risk="Hand-rolled URL parsing misses encoding and repeated-key edge cases.",
                    )
                )
            if relative_path.endswith(".py") and _looks_like_csv_split(
                relative_path, lines, index, line
            ):
                findings.append(
                    _ponytail_finding(
                        tag="stdlib",
                        file=relative_path,
                        line=index,
                        rule_id="hand-rolled-csv-parser",
                        evidence=line,
                        expected="Use Python's csv module for CSV parsing.",
                        risk="Comma splitting breaks quoted fields, escaped values, and newlines.",
                    )
                )
        if (
            is_javascript_source
            and re.search(r"\bfunction\s+debounce\b", text)
            and {"setTimeout", "clearTimeout"}
            <= set(re.findall(r"\b(?:setTimeout|clearTimeout)\b", text))
        ):
            line_number, evidence = _first_line(lines, r"\bfunction\s+debounce\b")
            findings.append(
                _ponytail_finding(
                    tag="shrink",
                    file=relative_path,
                    line=line_number,
                    rule_id="hand-rolled-debounce",
                    evidence=evidence,
                    expected="Use the existing debounce helper/dependency or keep this local to its caller.",
                    risk="Shared debounce helpers grow edge cases around cancellation, leading, and flushing.",
                )
            )
    return findings


def _looks_like_csv_split(
    relative_path: str, lines: list[str], line_number: int, line: str
) -> bool:
    if re.search(r"\bsplit\(['\"],['\"]\)", line) is None:
        return False
    context = "\n".join(lines[max(0, line_number - 4) : line_number + 1]).lower()
    return "csv" in relative_path.lower() or "csv" in context


def _ponytail_finding(
    *,
    tag: str,
    file: str,
    line: int,
    rule_id: str,
    evidence: str,
    expected: str,
    risk: str,
) -> dict[str, Any]:
    return _finding(
        category="ponytail",
        severity="observation",
        confidence="medium",
        file=file,
        line=line,
        rule_id=rule_id,
        evidence=f"{tag}: {evidence}",
        expected_improvement=expected,
        risk=risk,
        verification=_verification_for_path(file),
        remediation_bucket=f"Ponytail debt: {tag}",
    )


def _lines(item: dict[str, Any]) -> list[str]:
    lines = item.get("lines")
    return lines if isinstance(lines, list) and all(isinstance(line, str) for line in lines) else []


def _function_blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    blocks: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = re.search(
            r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*{",
            line,
        )
        if match is None:
            continue
        end = _block_end(lines, index)
        if end > index:
            blocks.append((index, end, match.group(1)))
    return blocks


def _block_end(lines: list[str], start: int) -> int:
    depth = 0
    opened = False
    for index in range(start, len(lines)):
        line = lines[index]
        depth += line.count("{")
        opened = opened or depth > 0
        depth -= line.count("}")
        if opened and depth <= 0:
            return index
    return start


def _env_names(line: str) -> list[str]:
    names = [match.group(1) for match in re.finditer(r"\bprocess\.env\.([A-Z0-9_]+)", line)]
    names.extend(
        match.group(1)
        for match in re.finditer(r"\bos\.environ(?:\.get)?\(\s*['\"]([A-Z0-9_]+)['\"]", line)
    )
    names.extend(
        match.group(1) for match in re.finditer(r"\bgetenv\(\s*['\"]([A-Z0-9_]+)['\"]", line)
    )
    return names


def _package_dependencies(scanned_files: list[dict[str, Any]]) -> set[str]:
    dependencies: set[str] = set()
    for item in scanned_files:
        if str(item["path"]).endswith("package.json"):
            try:
                payload = json.loads(str(item["text"]))
            except json.JSONDecodeError:
                continue
            for section in ("dependencies", "devDependencies", "optionalDependencies"):
                values = payload.get(section)
                if isinstance(values, dict):
                    dependencies.update(key for key in values if isinstance(key, str))
    return dependencies


def _imported_package(line: str) -> str | None:
    match = re.search(r"\bfrom\s+['\"]([^'\"]+)['\"]|\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)", line)
    if match is None:
        return None
    raw = match.group(1) or match.group(2)
    if raw.startswith((".", "/")):
        return None
    parts = raw.split("/")
    return "/".join(parts[:2]) if raw.startswith("@") and len(parts) >= 2 else parts[0]


def _first_line(lines: list[str], pattern: str) -> tuple[int, str]:
    for index, line in enumerate(lines, start=1):
        if re.search(pattern, line):
            return index, line
    return 1, lines[0] if lines else ""
