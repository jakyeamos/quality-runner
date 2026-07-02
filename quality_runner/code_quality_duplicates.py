from __future__ import annotations

import re
from typing import Any

from quality_runner.code_quality_paths import _is_javascript_source_file


def _extract_functions(relative_path: str, lines: list[str]) -> list[dict[str, Any]]:
    if not _is_javascript_source_file(relative_path):
        return []
    functions: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = re.search(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)", line)
        if match is None:
            continue
        end = _block_end(lines, index)
        body = "\n".join(lines[index : end + 1])
        normalized = _normalize_function(body, match.group(2))
        if len(normalized) < 30:
            continue
        functions.append(
            {
                "file": relative_path,
                "line": index + 1,
                "name": match.group(1),
                "line_count": end - index + 1,
                "normalized_body": normalized,
            }
        )
    return functions


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
    normalized = re.sub(r"\([^)]*\)", "(ARGS)", normalized, count=1)
    for name in sorted(local_names, key=len, reverse=True):
        normalized = re.sub(rf"\b{re.escape(name)}\b", "LOCAL", normalized)
    return re.sub(r"\s+", "", normalized)
