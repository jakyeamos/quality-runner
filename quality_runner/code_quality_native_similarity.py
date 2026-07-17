from __future__ import annotations

import ast
import keyword
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from pathlib import Path

from quality_runner.code_quality_duplicates import _block_end
from quality_runner.code_quality_paths import _is_test_file

NATIVE_SIMILARITY_SCHEMA = "quality-runner-similarity-v0.1"
NATIVE_SIMILARITY_SOURCE = "qr-native"

_SUPPORTED_EXTENSIONS = {".cjs", ".js", ".jsx", ".mjs", ".py", ".rs", ".ts", ".tsx"}
_JAVASCRIPT_EXTENSIONS = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
_BRACED_STARTS = {
    "javascript": re.compile(
        r"^\s*(?:(?:export|default|async)\s+)*function\s+"
        r"(?P<name>[A-Za-z_$][\w$]*)\s*\("
    ),
    "rust": re.compile(
        r"^\s*(?:(?:pub(?:\([^)]*\))?|async|unsafe|extern|const)\s+)*fn\s+"
        r"(?P<name>[A-Za-z_][\w]*)\s*\("
    ),
}
_PYTHON_START = re.compile(r"^(?P<indent>\s*)(?:async\s+)?def\s+(?P<name>[A-Za-z_]\w*)\s*\(")
_TOKEN_RE = re.compile(
    r"//[^\n]*|/\*[\s\S]*?\*/|#[^\n]*|"
    r"'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|"
    r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`|"
    r"\b\d+(?:\.\d+)?\b|[A-Za-z_$][\w$]*|"
    r"===|!==|=>|==|!=|<=|>=|&&|\|\||::|->|\+\+|--|[^\s]"
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")
_PYTHON_KEYWORDS = set(keyword.kwlist) | {"async", "await"}
_JAVASCRIPT_KEYWORDS = {
    "async",
    "await",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "debugger",
    "default",
    "delete",
    "do",
    "else",
    "export",
    "extends",
    "finally",
    "for",
    "from",
    "function",
    "if",
    "import",
    "in",
    "instanceof",
    "let",
    "new",
    "of",
    "return",
    "static",
    "super",
    "switch",
    "this",
    "throw",
    "try",
    "typeof",
    "var",
    "void",
    "while",
    "with",
    "yield",
}
_RUST_KEYWORDS = {
    "as",
    "async",
    "await",
    "break",
    "const",
    "continue",
    "crate",
    "dyn",
    "else",
    "enum",
    "extern",
    "fn",
    "for",
    "if",
    "impl",
    "in",
    "let",
    "loop",
    "match",
    "mod",
    "move",
    "mut",
    "pub",
    "ref",
    "return",
    "self",
    "Self",
    "static",
    "struct",
    "super",
    "trait",
    "type",
    "unsafe",
    "use",
    "where",
    "while",
    "yield",
}


def native_similarity_scan(
    repo_root: Path,
    *,
    scanned_files: Sequence[Mapping[str, object]] | None,
    policy: Mapping[str, object],
    disabled_groups: set[str],
) -> dict[str, object]:
    if "deduplicate" in disabled_groups or policy.get("similarity_enabled") is False:
        return _report(
            status="skipped",
            clusters=[],
            findings=[],
            scanner_status=[{"tool": NATIVE_SIMILARITY_SOURCE, "status": "skipped"}],
        )

    files = list(scanned_files) if scanned_files is not None else _load_files(repo_root)
    include_tests = policy.get("similarity_include_tests") is True
    min_lines = _positive_int(policy.get("similarity_min_lines"), default=8)
    max_pairs = _positive_int(policy.get("similarity_max_pairs"), default=25)
    threshold = _unit_interval(policy.get("similarity_threshold"), default=0.87)
    candidates = _native_candidates(files, include_tests=include_tests, min_lines=min_lines)
    clusters = _similarity_clusters(candidates, threshold=threshold, max_pairs=max_pairs)
    languages = sorted({str(candidate["language"]) for candidate in candidates})
    status = "executed" if languages else "not_applicable"
    return _report(
        status=status,
        clusters=clusters,
        findings=[],
        scanner_status=[
            {
                "tool": NATIVE_SIMILARITY_SOURCE,
                "status": status,
                "candidate_count": len(candidates),
                "languages": languages,
            }
        ],
    )


def validate_similarity_report(report: Mapping[str, object]) -> dict[str, object]:
    required = ("schema", "backend", "status", "clusters", "findings", "scanner_status")
    errors = [field for field in required if field not in report]
    if report.get("schema") != NATIVE_SIMILARITY_SCHEMA:
        errors.append("schema")
    if report.get("backend") != "native":
        errors.append("backend")
    for field in ("clusters", "findings", "scanner_status"):
        if not isinstance(report.get(field), list):
            errors.append(field)
    return {"passed": not errors, "errors": errors}


def _report(
    *,
    status: str,
    clusters: list[dict[str, object]],
    findings: list[dict[str, object]],
    scanner_status: list[dict[str, object]],
) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": NATIVE_SIMILARITY_SCHEMA,
        "backend": "native",
        "status": status,
        "clusters": clusters,
        "findings": findings,
        "scanner_status": scanner_status,
    }
    validation = validate_similarity_report(report)
    if validation["passed"] is not True:
        raise ValueError(f"invalid native similarity report: {validation['errors']}")
    return report


def _native_candidates(
    scanned_files: Sequence[Mapping[str, object]],
    *,
    include_tests: bool,
    min_lines: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for scanned_file in scanned_files:
        path = scanned_file.get("path")
        text = scanned_file.get("text")
        if not isinstance(path, str) or not isinstance(text, str):
            continue
        suffix = _suffix(path)
        if suffix not in _SUPPORTED_EXTENSIONS or (not include_tests and _is_test_file(path)):
            continue
        language = _language_for_suffix(suffix)
        if language == "python":
            extracted = _extract_python_functions(path, text)
        else:
            extracted = _extract_braced_functions(path, text, language)
        for candidate in extracted:
            if _int_value(candidate.get("line_count"), default=0) < min_lines:
                continue
            body = candidate.pop("body")
            if not isinstance(body, str):
                continue
            tokens = _normalize_tokens(body, language)
            if len(tokens) < 12:
                continue
            candidate["tokens"] = tokens
            candidates.append(candidate)
    candidates.sort(key=_candidate_sort_key)
    return candidates


def _extract_python_functions(path: str, text: str) -> list[dict[str, object]]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        return []
    lines = text.splitlines()
    functions: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        start = node.lineno - 1
        end = node.end_lineno or node.lineno
        body = "\n".join(lines[start:end])
        functions.append(
            {
                "file": path,
                "line": node.lineno,
                "end_line": end,
                "name": node.name,
                "line_count": end - start,
                "language": "python",
                "body": body,
            }
        )
    return functions


def _extract_braced_functions(path: str, text: str, language: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    pattern = _BRACED_STARTS[language]
    functions: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        match = pattern.search(line)
        if match is None:
            continue
        end = _block_end(lines, index)
        functions.append(
            {
                "file": path,
                "line": index + 1,
                "end_line": end + 1,
                "name": match.group("name"),
                "line_count": end - index + 1,
                "language": language,
                "body": "\n".join(lines[index : end + 1]),
            }
        )
    return functions


def _similarity_clusters(
    candidates: list[dict[str, object]], *, threshold: float, max_pairs: int
) -> list[dict[str, object]]:
    buckets: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        tokens = candidate["tokens"]
        if isinstance(tokens, list):
            buckets[(str(candidate["language"]), max(1, len(tokens) // 12))].append(candidate)

    matches: list[dict[str, object]] = []
    for (language, band), left_bucket in sorted(buckets.items()):
        for right_band in (band, band + 1):
            right_bucket = buckets.get((language, right_band), [])
            for left_index, left in enumerate(left_bucket):
                start = left_index + 1 if right_band == band else 0
                for right in right_bucket[start:]:
                    score = _token_similarity(left.get("tokens"), right.get("tokens"))
                    if score < threshold:
                        continue
                    matches.append(
                        {
                            "source": NATIVE_SIMILARITY_SOURCE,
                            "kind": "pair",
                            "reason": "normalized-token-shape-match",
                            "similarity": round(score, 6),
                            "score": None,
                            "threshold": threshold,
                            "candidates": [_candidate_ref(left), _candidate_ref(right)],
                        }
                    )

    matches.sort(key=_cluster_sort_key)
    return matches[:max_pairs]


def _token_similarity(left: object, right: object) -> float:
    if not isinstance(left, list) or not isinstance(right, list) or not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _candidate_ref(candidate: Mapping[str, object]) -> dict[str, object]:
    return {
        "file": str(candidate["file"]),
        "line": _int_value(candidate.get("line"), default=0),
        "end_line": _int_value(candidate.get("end_line"), default=0),
        "name": str(candidate["name"]),
        "line_count": _int_value(candidate.get("line_count"), default=0),
    }


def _candidate_sort_key(candidate: Mapping[str, object]) -> tuple[str, int, str]:
    return (
        str(candidate.get("file", "")),
        _int_value(candidate.get("line"), default=0),
        str(candidate.get("name", "")),
    )


def _cluster_sort_key(cluster: Mapping[str, object]) -> tuple[float, str, int, str, int]:
    candidates = cluster.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else {}
    second = candidates[1] if isinstance(candidates, list) and len(candidates) > 1 else {}
    first_map = first if isinstance(first, Mapping) else {}
    second_map = second if isinstance(second, Mapping) else {}
    return (
        -_float_value(cluster.get("similarity"), default=0.0),
        str(first_map.get("file", "")),
        _int_value(first_map.get("line"), default=0),
        str(second_map.get("file", "")),
        _int_value(second_map.get("line"), default=0),
    )


def _normalize_tokens(body: str, language: str) -> list[str]:
    keywords = {
        "python": _PYTHON_KEYWORDS,
        "javascript": _JAVASCRIPT_KEYWORDS,
        "rust": _RUST_KEYWORDS,
    }[language]
    local_ids: dict[str, str] = {}
    normalized: list[str] = []
    previous = ""
    for token in _TOKEN_RE.findall(body):
        if _is_comment(token):
            continue
        if _is_literal(token):
            value = "LITERAL"
        elif _IDENTIFIER_RE.match(token) is not None:
            if token in keywords:
                value = token
            elif previous in {"function", "def", "fn"}:
                value = "FUNCTION"
            elif previous in {".", "::", "->"}:
                value = f"MEMBER:{token}"
            else:
                value = local_ids.setdefault(token, f"ID{len(local_ids)}")
        else:
            value = token
        normalized.append(value)
        previous = token
    return normalized


def _is_comment(token: str) -> bool:
    return token.startswith(("//", "/*", "#"))


def _is_literal(token: str) -> bool:
    return token[:1] in {"'", '"', "`"} or token[:1].isdigit()


def _language_for_suffix(suffix: str) -> str:
    if suffix in _JAVASCRIPT_EXTENSIONS:
        return "javascript"
    if suffix == ".py":
        return "python"
    return "rust"


def _suffix(path: str) -> str:
    dot = path.rfind(".")
    return path[dot:].lower() if dot >= 0 else ""


def _load_files(root: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    excluded_parts = {
        ".git",
        ".quality-runner",
        ".venv",
        "build",
        "dist",
        "node_modules",
        "target",
        "vendor",
    }
    for path in sorted(root.rglob("*")):
        if not path.is_file() or _suffix(path.name) not in _SUPPORTED_EXTENSIONS:
            continue
        if any(part in excluded_parts for part in path.parts):
            continue
        try:
            relative = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        files.append({"path": relative, "text": text})
    return files


def _positive_int(value: object, *, default: int) -> int:
    return value if isinstance(value, int) and value > 0 else default


def _unit_interval(value: object, *, default: float) -> float:
    if isinstance(value, int) and 0 <= value <= 1:
        return float(value)
    if isinstance(value, float) and 0 <= value <= 1:
        return value
    return default


def _int_value(value: object, *, default: int) -> int:
    return value if isinstance(value, int) else default


def _float_value(value: object, *, default: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    return default
