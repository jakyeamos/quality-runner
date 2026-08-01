from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import (
    _has_todo_comment,
    _is_test_file,
    _verification_for_path,
)

DEFAULT_REGISTRATION_GLOBS = ["**/cli.py", "**/router*.ts", "**/mcp.py"]
DEFAULT_ENTRYPOINT_GLOBS = ["**/main.*", "**/index.*", "**/src/app/**", "apps/*/src/app/**"]
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
WIP_TERMS = ("draft", "stub", "placeholder", "wip", "scaffold")

TS_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)"
)
PY_SYMBOL_RE = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
HANDLER_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:function|def)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*(?:Handler|_handler)|handle[A-Z_][A-Za-z0-9_]*|handle_[A-Za-z0-9_]+)"
)
_SYMBOL_REFERENCE_RE = re.compile(r"(?<![\w$])([A-Za-z_$][\w$]*)(?![\w$])")


@dataclass(frozen=True)
class _ReferenceIndex:
    paths_by_symbol: Mapping[str, frozenset[str]]
    registration_paths_by_symbol: Mapping[str, frozenset[str]]


def unwired_findings(
    scanned_files: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    policy = _integrate_policy(config)
    if not policy["enabled"]:
        return []

    source_files = [_source_file(item) for item in scanned_files]
    source_files = [item for item in source_files if item is not None]
    registration_files = [
        item
        for item in source_files
        if _path_matches_any(item["path"], policy["registration_globs"])
    ]
    registration_paths = {item["path"] for item in registration_files}
    reference_index = _build_reference_index(
        source_files,
        registration_paths=registration_paths,
    )
    findings: list[dict[str, Any]] = []
    for item in source_files:
        path = item["path"]
        if _is_test_file(path) or _is_barrel_file(path):
            continue
        findings.extend(_stub_findings(item))
        findings.extend(_todo_scaffold_findings(item, policy["entrypoint_globs"]))
        findings.extend(
            _export_without_reference_findings(
                item,
                reference_index,
                entrypoint_globs=policy["entrypoint_globs"],
            )
        )
        findings.extend(
            _handler_without_registration_findings(
                item,
                reference_index,
                registration_paths,
            )
        )
    return findings


def _source_file(item: dict[str, Any]) -> dict[str, Any] | None:
    path = item.get("path")
    text = item.get("text")
    lines = item.get("lines")
    if (
        isinstance(path, str)
        and Path(path).suffix in SOURCE_SUFFIXES
        and isinstance(text, str)
        and isinstance(lines, list)
    ):
        return {
            "path": path,
            "text": text,
            "lines": [line for line in lines if isinstance(line, str)],
        }
    return None


def _stub_findings(item: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    path = item["path"]
    lines = item["lines"]
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if _is_stub_line(line=line, stripped=stripped, lines=lines, line_number=index):
            evidence = line
        else:
            continue
        findings.append(
            _finding(
                category="integrate",
                severity="warning",
                confidence="high" if "NotImplementedError" in line else "medium",
                file=path,
                line=index,
                rule_id="stub-implementation",
                evidence=evidence,
                expected_improvement=(
                    "Decide whether this partial implementation should be finished, wired into "
                    "its caller, descoped, or accepted as intentional WIP."
                ),
                risk="Stubbed implementation can look complete while the feature path is not usable.",
                verification=_verification_for_path(path),
                remediation_bucket="Integration and wiring decisions",
            )
        )
    return findings


def _todo_scaffold_findings(
    item: dict[str, Any], entrypoint_globs: list[str]
) -> list[dict[str, Any]]:
    path = item["path"]
    lines = item["lines"]
    todo_lines = [
        (index, line) for index, line in enumerate(lines, start=1) if _has_todo_comment(line)
    ]
    if len(todo_lines) < 3:
        return []
    if not (
        _path_matches_any(path, entrypoint_globs) or _path_or_text_suggests_wip(path, item["text"])
    ):
        return []
    first_line, first_evidence = todo_lines[0]
    return [
        _finding(
            category="integrate",
            severity="warning",
            confidence="medium",
            file=path,
            line=first_line,
            rule_id="todo-scaffold",
            evidence=f"{len(todo_lines)} TODO/FIXME/HACK/TBD comments; first: {first_evidence.strip()}",
            expected_improvement=(
                "Choose whether this scaffold should be completed and wired, descoped, or "
                "tracked as explicit WIP with an owner."
            ),
            risk="TODO-heavy scaffolded files often represent started work that never reached an entrypoint.",
            verification=_verification_for_path(path),
            remediation_bucket="Integration and wiring decisions",
        )
    ]


def _export_without_reference_findings(
    item: dict[str, Any],
    reference_index: _ReferenceIndex,
    *,
    entrypoint_globs: list[str],
) -> list[dict[str, Any]]:
    path = item["path"]
    if _path_matches_any(path, entrypoint_globs):
        return []
    findings: list[dict[str, Any]] = []
    for index, line in enumerate(item["lines"], start=1):
        symbol = _exported_symbol(path, line)
        if symbol is None or _skip_symbol(symbol):
            continue
        if _symbol_referenced_elsewhere(symbol, path, reference_index):
            continue
        findings.append(
            _finding(
                category="integrate",
                severity="warning",
                confidence="medium",
                file=path,
                line=index,
                rule_id="export-without-references",
                evidence=f"{symbol} is defined in {path} with no scanned source references outside this file.",
                expected_improvement=(
                    f"Decide whether to wire {symbol} into an entrypoint, finish the caller, "
                    "descope the partial work, or record intentional WIP."
                ),
                risk="Exported or top-level surfaces with no callers are often unfinished wiring rather than cleanup-only dead code.",
                verification=_verification_for_path(path),
                remediation_bucket="Integration and wiring decisions",
            )
        )
    return findings


def _handler_without_registration_findings(
    item: dict[str, Any],
    reference_index: _ReferenceIndex,
    registration_paths: set[str],
) -> list[dict[str, Any]]:
    if not registration_paths:
        return []
    path = item["path"]
    findings: list[dict[str, Any]] = []
    for index, line in enumerate(item["lines"], start=1):
        match = HANDLER_RE.match(line)
        if match is None:
            continue
        symbol = match.group(1)
        if _symbol_referenced_in_paths(symbol, path, reference_index):
            continue
        findings.append(
            _finding(
                category="integrate",
                severity="warning",
                confidence="medium",
                file=path,
                line=index,
                rule_id="handler-without-registration",
                evidence=f"{symbol} is handler-shaped but is not referenced by configured registration files.",
                expected_improvement=(
                    f"Decide whether {symbol} should be registered, finished, descoped, "
                    "or accepted as explicit WIP."
                ),
                risk="Handlers and commands that are not registered are invisible to users and automation.",
                verification=_verification_for_path(path),
                remediation_bucket="Integration and wiring decisions",
            )
        )
    return findings


def _integrate_policy(config: dict[str, Any]) -> dict[str, Any]:
    section = config.get("integrate")
    if not isinstance(section, dict):
        section = {}
    enabled = section.get("enabled")
    return {
        "enabled": enabled is not False,
        "registration_globs": _string_list(section.get("registration_globs"))
        or DEFAULT_REGISTRATION_GLOBS,
        "entrypoint_globs": _string_list(section.get("entrypoint_globs"))
        or DEFAULT_ENTRYPOINT_GLOBS,
    }


def _near_definition(lines: list[str], line_number: int) -> bool:
    start = max(0, line_number - 4)
    for previous in reversed(lines[start : line_number - 1]):
        stripped = previous.strip()
        if not stripped:
            continue
        return stripped.endswith(":") and (
            stripped.startswith(("def ", "async def ", "class "))
            or re.match(r"(?:export\s+)?(?:async\s+)?function\b", stripped) is not None
        )
    return False


def _is_stub_line(*, line: str, stripped: str, lines: list[str], line_number: int) -> bool:
    return "NotImplementedError" in line or (
        stripped in {"pass", "..."} and _near_definition(lines, line_number)
    )


def _exported_symbol(path: str, line: str) -> str | None:
    match = PY_SYMBOL_RE.match(line) if Path(path).suffix == ".py" else TS_EXPORT_RE.match(line)
    return match.group(1) if match is not None else None


def _build_reference_index(
    source_files: list[dict[str, Any]],
    *,
    registration_paths: set[str] | None = None,
) -> _ReferenceIndex:
    references: dict[str, set[str]] = {}
    registration_references: dict[str, set[str]] = {}
    configured_registration_paths = registration_paths or set()
    for item in source_files:
        path = item["path"]
        if _is_test_file(path):
            continue
        for match in _SYMBOL_REFERENCE_RE.finditer(item["text"]):
            symbol = match.group(1)
            references.setdefault(symbol, set()).add(path)
            if path in configured_registration_paths:
                registration_references.setdefault(symbol, set()).add(path)
    return _ReferenceIndex(
        paths_by_symbol={symbol: frozenset(paths) for symbol, paths in references.items()},
        registration_paths_by_symbol={
            symbol: frozenset(paths) for symbol, paths in registration_references.items()
        },
    )


def _symbol_referenced_elsewhere(
    symbol: str,
    defining_path: str,
    reference_index: _ReferenceIndex,
) -> bool:
    paths = reference_index.paths_by_symbol.get(symbol)
    if not paths:
        return False
    return len(paths) > 1 if defining_path in paths else True


def _symbol_referenced_in_paths(
    symbol: str,
    defining_path: str,
    reference_index: _ReferenceIndex,
) -> bool:
    paths = reference_index.registration_paths_by_symbol.get(symbol)
    if not paths:
        return False
    return len(paths) > 1 if defining_path in paths else True


def _skip_symbol(symbol: str) -> bool:
    return (
        symbol.startswith("_")
        or symbol in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "default"}
        or symbol.endswith(("Props", "Params"))
    )


def _is_barrel_file(path: str) -> bool:
    name = Path(path).name
    return name in {"__init__.py", "index.ts", "index.tsx", "index.js", "index.jsx"}


def _path_or_text_suggests_wip(path: str, text: str) -> bool:
    haystack = f"{path}\n{text[:2000]}".lower()
    return any(term in haystack for term in WIP_TERMS)


def _path_matches_any(relative_path: str, patterns: list[str]) -> bool:
    return any(_path_matches_glob(relative_path, pattern) for pattern in patterns)


def _path_matches_glob(relative_path: str, pattern: str) -> bool:
    normalized_path = relative_path.strip("/")
    normalized_pattern = pattern.strip().strip("/")
    if not normalized_path or not normalized_pattern:
        return False
    if fnmatchcase(normalized_path, normalized_pattern):
        return True
    if normalized_pattern.startswith("**/"):
        return fnmatchcase(normalized_path, normalized_pattern[3:])
    return False


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
