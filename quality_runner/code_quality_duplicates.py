from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from quality_runner.code_quality_paths import _is_javascript_source_file


def _extract_functions(relative_path: str, lines: list[str]) -> list[dict[str, Any]]:
    suffix = relative_path.rsplit(".", maxsplit=1)[-1].lower() if "." in relative_path else ""
    if suffix == "py":
        return _extract_python_functions(relative_path, lines)
    if suffix == "rs":
        return _extract_rust_functions(relative_path, lines)
    if not _is_javascript_source_file(relative_path):
        return []
    return _extract_javascript_functions(relative_path, lines)


def _extract_javascript_functions(relative_path: str, lines: list[str]) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = re.search(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)", line)
        if match is not None:
            functions.append(
                _function_record(
                    relative_path=relative_path,
                    lines=lines,
                    start=index,
                    end=_block_end(lines, index),
                    name=match.group(1),
                    params=match.group(2),
                    normalizer=_normalize_javascript_function,
                )
            )
            continue

        arrow_match = re.search(
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
            r"(?:async\s*)?(?:\(([^)]*)\)|([A-Za-z_$][\w$]*))\s*=>\s*\{",
            line,
        )
        if arrow_match is not None:
            params = arrow_match.group(2) or arrow_match.group(3) or ""
            functions.append(
                _function_record(
                    relative_path=relative_path,
                    lines=lines,
                    start=index,
                    end=_block_end(lines, index),
                    name=arrow_match.group(1),
                    params=params,
                    normalizer=_normalize_javascript_function,
                )
            )
    return functions


def _extract_python_functions(relative_path: str, lines: list[str]) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = re.match(
            r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*:",
            line,
        )
        if match is None:
            continue
        end = _python_block_end(lines, index)
        functions.append(
            _function_record(
                relative_path=relative_path,
                lines=lines,
                start=index,
                end=end,
                name=match.group(1),
                params=match.group(2),
                normalizer=_normalize_python_function,
            )
        )
    return functions


def _extract_rust_functions(relative_path: str, lines: list[str]) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = re.search(
            r"\b(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)[^{]*\{",
            line,
        )
        if match is None:
            continue
        functions.append(
            _function_record(
                relative_path=relative_path,
                lines=lines,
                start=index,
                end=_block_end(lines, index),
                name=match.group(1),
                params=match.group(2),
                normalizer=_normalize_rust_function,
            )
        )
    return functions


def _function_record(
    *,
    relative_path: str,
    lines: list[str],
    start: int,
    end: int,
    name: str,
    params: str,
    normalizer: Callable[[str, str], str],
) -> dict[str, Any]:
    body = "\n".join(lines[start : end + 1])
    normalized = normalizer(body, params)
    return {
        "file": relative_path,
        "line": start + 1,
        "end_line": end + 1,
        "name": name,
        "line_count": end - start + 1,
        "normalized_body": normalized,
    }


def _duplicate_clusters(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for function in functions:
        normalized = str(function["normalized_body"])
        groups.setdefault(normalized, []).append(function)
    clusters = []
    for group in groups.values():
        if len(group) < 2:
            continue
        candidates = sorted(group, key=lambda item: (str(item["file"]), int(item["line"])))
        clusters.append(
            {
                "id": f"DUP-{len(clusters) + 1:03d}",
                "similarity": 100,
                "reason": "normalized-function-body-match",
                "candidates": [
                    {
                        "file": str(item["file"]),
                        "line": int(item["line"]),
                        "name": str(item["name"]),
                        "line_count": int(item["line_count"]),
                    }
                    for item in candidates
                ],
            }
        )
    return clusters


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


def _python_block_end(lines: list[str], start: int) -> int:
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent:
            return index - 1
    return len(lines) - 1


def _normalize_function(body: str, params: str) -> str:
    local_names = {
        match.group(1) for match in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)", body)
    }
    local_names.update(
        name_match.group(1)
        for part in params.split(",")
        if (name_match := re.match(r"\s*([A-Za-z_$][\w$]*)", part))
    )
    normalized = re.sub(r"\bfunction\s+[A-Za-z_$][\w$]*", "function FN", body)
    normalized = re.sub(
        r"\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=",
        "const FN =",
        normalized,
    )
    normalized = re.sub(r"\([^)]*\)", "(ARGS)", normalized, count=1)
    for name in sorted(local_names, key=len, reverse=True):
        normalized = re.sub(rf"\b{re.escape(name)}\b", "LOCAL", normalized)
    return re.sub(r"\s+", "", normalized)


def _normalize_javascript_function(body: str, params: str) -> str:
    return _normalize_function(body, params)


def _normalize_python_function(body: str, params: str) -> str:
    local_names = _parameter_names(params)
    local_names.update(match.group(1) for match in re.finditer(r"\b([A-Za-z_]\w*)\s*=", body))
    normalized = re.sub(r"\b(?:async\s+)?def\s+[A-Za-z_]\w*", "def FN", body)
    for name in sorted(local_names, key=len, reverse=True):
        normalized = re.sub(rf"\b{re.escape(name)}\b", "LOCAL", normalized)
    return re.sub(r"\s+", "", normalized)


def _normalize_rust_function(body: str, params: str) -> str:
    local_names = _parameter_names(params)
    local_names.update(
        match.group(1) for match in re.finditer(r"\blet\s+(?:mut\s+)?([A-Za-z_]\w*)", body)
    )
    normalized = re.sub(r"\bfn\s+[A-Za-z_]\w*", "fn FN", body)
    for name in sorted(local_names, key=len, reverse=True):
        normalized = re.sub(rf"\b{re.escape(name)}\b", "LOCAL", normalized)
    return re.sub(r"\s+", "", normalized)


def _parameter_names(params: str) -> set[str]:
    return {match.group(1) for match in re.finditer(r"(?:mut\s+)?([A-Za-z_]\w*)", params)}
