"""Static evidence for a repository's stable runtime error-code contract."""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import MAX_DOCUMENT_BYTES, relative_path

MAX_SOURCE_FILES = 600
SOURCE_SUFFIXES = {
    ".c",
    ".cpp",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}
SKIPPED_DIRECTORIES = {
    ".git",
    ".next",
    ".pytest_cache",
    ".venv",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
DECLARATION_PATTERNS = (
    re.compile(r"\b(?:type|interface|enum|class)\s+\w*errorcode\w*", re.IGNORECASE),
    re.compile(r"\b(?:const|let|var)\s+\w*errorcodes?\w*\s*[:=]", re.IGNORECASE),
    re.compile(r"\bErrorCodeSchema\s*=\s*[^\n]+\benum\s*\(", re.IGNORECASE),
    re.compile(r"\b(?:errorCode|error_code)\s*[:=]\s*", re.IGNORECASE),
)
CODE_ASSIGNMENT_LITERAL_PATTERN = re.compile(
    r"\b(?:[A-Z][A-Z0-9_]{2,}|errorCode|error_code)\s*[:=]\s*['\"]([A-Za-z][A-Za-z0-9_.:-]{2,64})['\"]",
)
CODE_LIST_LITERAL_PATTERN = re.compile(r"['\"]([A-Za-z][A-Za-z0-9_.:-]{2,64})['\"]")
PROPAGATION_PATTERN = re.compile(
    r"\b(?:errorCode|error_code)\b[^\n]{0,120}\b(?:response|result|envelope|payload|serialize|json)",
    re.IGNORECASE,
)
DOC_PATTERN = re.compile(
    r"\b(?:stable|machine[- ]readable|diagnos|error[_ -]?code)\w*\b",
    re.IGNORECASE,
)
TEST_PATTERN = re.compile(
    r"\b(?:errorCode|error_code|ErrorCode)\b|(?:expect|assert|should)[^\n]{0,100}\bcode\b",
    re.IGNORECASE,
)


def assess_stable_error_codes(root: Path) -> dict[str, Any]:
    """Assess stable error-code evidence without executing or modifying a repo."""

    source_files = _source_files(root)
    if not source_files:
        return {
            "score": None,
            "status": "not_applicable",
            "message": "No supported runtime source surface was found for stable error codes.",
            "evidence": [{"path": ".", "detail": "No bounded source files were discovered."}],
        }

    sources: list[tuple[Path, str]] = []
    unreadable = 0
    for path in source_files:
        try:
            if path.stat().st_size > MAX_DOCUMENT_BYTES:
                unreadable += 1
                continue
            sources.append((path, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            unreadable += 1

    if not sources:
        return _result(
            score=None,
            status="blocked",
            message="Supported runtime source was found, but none could be read within the evidence bound.",
            evidence=_evidence(root, source_files, unreadable, [], [], []),
        )

    declarations = [
        (path, text)
        for path, text in sources
        if any(pattern.search(text) for pattern in DECLARATION_PATTERNS)
    ]
    literals: set[str] = set()
    for _, text in declarations:
        literals.update(match.group(1) for match in CODE_ASSIGNMENT_LITERAL_PATTERN.finditer(text))
        if re.search(r"\b(?:ErrorCodeSchema|ErrorCodes?)\b", text, re.IGNORECASE):
            literals.update(match.group(1) for match in CODE_LIST_LITERAL_PATTERN.finditer(text))
    propagation = [(path, text) for path, text in sources if PROPAGATION_PATTERN.search(text)]
    tests = [
        (path, text) for path, text in sources if _is_test_path(path) and TEST_PATTERN.search(text)
    ]
    documents = _documentation_files(root)
    documented = [path for path, text in documents if DOC_PATTERN.search(text)]

    if not declarations:
        return _result(
            score=0,
            status="absent",
            message="No stable error-code declaration or machine-readable error identity was found.",
            evidence=_evidence(root, source_files, unreadable, documented, tests, propagation),
        )

    score = 1
    if propagation or len(literals) >= 2:
        score = 2
    if documented and tests:
        score = 3
    unique_codes = len(literals) >= 2
    if score >= 3 and unique_codes and propagation and len(declarations) >= 1:
        score = 4

    status = {1: "discoverable", 2: "structured", 3: "validated", 4: "maintained"}[score]
    message = {
        1: "Error-code language is present, but a stable machine-readable contract is not yet established.",
        2: "Stable error-code declarations or propagation are present, but documentation and regression evidence are incomplete.",
        3: "Stable error codes are declared, documented, and covered by regression tests; propagation evidence remains incomplete.",
        4: "Stable error codes are declared, unique, documented, tested, and propagated through machine-readable results.",
    }[score]
    evidence = _evidence(root, source_files, unreadable, documented, tests, propagation)
    evidence.extend(
        [
            {"path": relative_path(root, path), "detail": "stable error-code declaration"}
            for path, _ in declarations[:8]
        ]
    )
    evidence.append(
        {
            "path": "<bounded inventory>",
            "detail": f"{len(literals)} distinct code literal(s); {len(declarations)} declaration file(s); {len(propagation)} propagation file(s)",
        }
    )
    return _result(score=score, status=status, message=message, evidence=evidence[:16])


def stable_error_code_finding_arguments(
    *, repository: dict[str, Any], as_of: str
) -> dict[str, Any]:
    assessment = assess_stable_error_codes(
        Path(str(repository["primary_path"])).expanduser().resolve()
    )
    return {
        "repository": repository,
        "dimension": "diagnosability.stable_error_codes",
        "score": assessment["score"],
        "as_of": as_of,
        "status": assessment["status"],
        "severity": "observation",
        "priority": "P1",
        "confidence": "high" if assessment["status"] != "unknown" else "medium",
        "message": assessment["message"],
        "evidence": assessment["evidence"],
        "validation_commands": ["qr fleet audit run --repo-path REPO --json"],
    }


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    try:
        for path in sorted(root.rglob("*")):
            if len(files) >= MAX_SOURCE_FILES:
                break
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.lower() not in SOURCE_SUFFIXES
            ):
                continue
            if any(part in SKIPPED_DIRECTORIES for part in path.relative_to(root).parts):
                continue
            files.append(path)
    except OSError:
        return files
    return files


def _documentation_files(root: Path) -> list[tuple[Path, str]]:
    paths = [root / "README.md", root / "CONTRIBUTING.md"]
    docs_root = root / "docs"
    if docs_root.is_dir():
        with suppress(OSError):
            paths.extend(sorted(docs_root.rglob("*.md"))[:120])
    documents: list[tuple[Path, str]] = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            continue
        try:
            if path.stat().st_size <= MAX_DOCUMENT_BYTES:
                documents.append((path, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return documents


def _is_test_path(path: Path) -> bool:
    name = path.name.lower()
    return (
        "test" in name
        or "spec" in name
        or any(
            part.lower() in {"test", "tests", "spec", "specs", "__tests__"} for part in path.parts
        )
    )


def _evidence(
    root: Path,
    source_files: list[Path],
    unreadable: int,
    documented: list[Path],
    tests: list[tuple[Path, str]],
    propagation: list[tuple[Path, str]],
) -> list[dict[str, str]]:
    evidence = [
        {
            "path": "<bounded inventory>",
            "detail": f"{len(source_files)} supported source file(s) inspected",
        },
    ]
    if unreadable:
        evidence.append(
            {
                "path": "<bounded inventory>",
                "detail": f"{unreadable} source file(s) were unreadable or over the size limit",
            }
        )
    for label, paths in (
        ("error-code documentation", documented),
        ("error-code regression test", [path for path, _ in tests]),
        ("machine-readable error propagation", [path for path, _ in propagation]),
    ):
        evidence.extend({"path": relative_path(root, path), "detail": label} for path in paths[:4])
    return evidence


def _result(
    *, score: int | None, status: str, message: str, evidence: list[dict[str, str]]
) -> dict[str, Any]:
    return {"score": score, "status": status, "message": message, "evidence": evidence[:16]}
