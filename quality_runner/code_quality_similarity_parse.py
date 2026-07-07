from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from quality_runner.code_quality_paths import _is_generated_file, _is_test_file

EXCLUDED_PATH_PARTS = {
    ".quality-runner",
    "build",
    "dist",
    "node_modules",
    "out",
    "target",
    "vendor",
}

_PAIR_HEADER_RE = re.compile(
    r"Similarity:\s*([\d.]+)%.*?(?:Score:\s*([\d.]+)\s*points)?",
    re.IGNORECASE,
)
_CLUSTER_HEADER_RE = re.compile(
    r"Cluster\s+\d+:\s+\d+\s+functions.*?avg similarity\s+([\d.]+)%.*?"
    r"(?:best score\s+([\d.]+))?",
    re.IGNORECASE,
)
_CANDIDATE_RE = re.compile(
    r"^\s*(?P<file>[^\s:]+):(?P<line>\d+)(?:-(?P<end_line>\d+))?\s+(?P<name>\S+)?\s*$"
)
_PYTHON_PAIR_RE = re.compile(
    r"^\s*(?P<file1>[^:]+):(?P<line1>\d+)\s*\|\s*L(?P<start1>\d+)-(?P<end1>\d+)\s+"
    r"function\s+(?P<name1>\S+)\s*<->\s*"
    r"(?P<file2>[^:]+):(?P<line2>\d+)\s*\|\s*L(?P<start2>\d+)-(?P<end2>\d+)\s+"
    r"function\s+(?P<name2>\S+)\s*$"
)
_PYTHON_SIMILARITY_RE = re.compile(r"Similarity:\s*([\d.]+)%", re.IGNORECASE)


def parse_similarity_output(
    stdout: str,
    *,
    source: str,
    threshold: float,
    include_tests: bool,
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    current_header: dict[str, Any] | None = None
    current_candidates: list[dict[str, Any]] = []
    pending_python_pair: list[dict[str, Any]] | None = None

    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        python_pair = _PYTHON_PAIR_RE.match(line)
        if python_pair is not None:
            pending_python_pair = _python_pair_candidates(python_pair.groupdict())
            continue

        if _PYTHON_SIMILARITY_RE.search(line) and pending_python_pair is not None:
            similarity = float(_PYTHON_SIMILARITY_RE.search(line).group(1))  # type: ignore[union-attr]
            cluster = _build_cluster(
                candidates=pending_python_pair,
                source=source,
                threshold=threshold,
                similarity=similarity,
                score=None,
                kind="pair",
            )
            if _cluster_allowed(cluster, include_tests=include_tests):
                clusters.append(cluster)
            pending_python_pair = None
            current_candidates = []
            current_header = None
            continue

        pair_header = _PAIR_HEADER_RE.search(line)
        if pair_header is not None:
            if current_candidates:
                cluster = _finalize_cluster(
                    candidates=current_candidates,
                    header=current_header,
                    source=source,
                    threshold=threshold,
                )
                if cluster is not None and _cluster_allowed(cluster, include_tests=include_tests):
                    clusters.append(cluster)
            current_header = {
                "similarity": float(pair_header.group(1)),
                "score": float(pair_header.group(2)) if pair_header.group(2) else None,
                "kind": "pair",
            }
            current_candidates = []
            continue

        cluster_header = _CLUSTER_HEADER_RE.search(line)
        if cluster_header is not None:
            if current_candidates:
                cluster = _finalize_cluster(
                    candidates=current_candidates,
                    header=current_header,
                    source=source,
                    threshold=threshold,
                )
                if cluster is not None and _cluster_allowed(cluster, include_tests=include_tests):
                    clusters.append(cluster)
            current_header = {
                "similarity": float(cluster_header.group(1)),
                "score": float(cluster_header.group(2)) if cluster_header.group(2) else None,
                "kind": "function",
            }
            current_candidates = []
            continue

        candidate_match = _CANDIDATE_RE.match(line)
        if candidate_match is not None:
            current_candidates.append(_candidate_from_match(candidate_match))
            if (
                current_header is not None
                and current_header.get("kind") == "pair"
                and len(current_candidates) >= 2
            ):
                cluster = _finalize_cluster(
                    candidates=current_candidates[:2],
                    header=current_header,
                    source=source,
                    threshold=threshold,
                )
                if cluster is not None and _cluster_allowed(cluster, include_tests=include_tests):
                    clusters.append(cluster)
                current_candidates = []
                current_header = None
            continue

        if line.strip().startswith("Duplicates in "):
            if current_candidates:
                cluster = _finalize_cluster(
                    candidates=current_candidates,
                    header=current_header,
                    source=source,
                    threshold=threshold,
                )
                if cluster is not None and _cluster_allowed(cluster, include_tests=include_tests):
                    clusters.append(cluster)
            current_candidates = []
            current_header = None

    if current_candidates:
        cluster = _finalize_cluster(
            candidates=current_candidates,
            header=current_header,
            source=source,
            threshold=threshold,
        )
        if cluster is not None and _cluster_allowed(cluster, include_tests=include_tests):
            clusters.append(cluster)

    return clusters


def _candidate_from_match(match: re.Match[str]) -> dict[str, Any]:
    line = int(match.group("line"))
    end_line = int(match.group("end_line")) if match.group("end_line") else line
    line_count = max(end_line - line + 1, 1)
    candidate = {
        "file": _normalize_path(match.group("file")),
        "line": line,
        "end_line": end_line,
        "line_count": line_count,
    }
    name = match.group("name")
    if name:
        candidate["name"] = name
    return candidate


def _python_pair_candidates(groups: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "file": _normalize_path(groups["file1"]),
            "line": int(groups["line1"]),
            "end_line": int(groups["end1"]),
            "line_count": int(groups["end1"]) - int(groups["start1"]) + 1,
            "name": groups["name1"],
        },
        {
            "file": _normalize_path(groups["file2"]),
            "line": int(groups["line2"]),
            "end_line": int(groups["end2"]),
            "line_count": int(groups["end2"]) - int(groups["start2"]) + 1,
            "name": groups["name2"],
        },
    ]


def _finalize_cluster(
    *,
    candidates: list[dict[str, Any]],
    header: dict[str, Any] | None,
    source: str,
    threshold: float,
) -> dict[str, Any] | None:
    if len(candidates) < 2:
        return None
    similarity = float(header["similarity"]) if header and "similarity" in header else 0.0
    score = header.get("score") if header else None
    kind = str(header.get("kind", "function")) if header else "function"
    return _build_cluster(
        candidates=candidates,
        source=source,
        threshold=threshold,
        similarity=similarity,
        score=score,
        kind=kind,
    )


def _build_cluster(
    *,
    candidates: list[dict[str, Any]],
    source: str,
    threshold: float,
    similarity: float,
    score: float | None,
    kind: str,
) -> dict[str, Any]:
    filtered = [
        candidate for candidate in candidates if not _should_skip_path(str(candidate["file"]))
    ]
    if len(filtered) < 2:
        return {
            "id": "",
            "source": source,
            "kind": kind,
            "reason": "ast-semantic-similarity",
            "similarity": similarity,
            "score": score,
            "threshold": threshold,
            "candidates": filtered,
            "suggested_disposition": "review-for-shared-abstraction",
        }
    return {
        "id": "",
        "source": source,
        "kind": kind,
        "reason": "ast-semantic-similarity",
        "similarity": similarity,
        "score": score,
        "threshold": threshold,
        "candidates": sorted(filtered, key=lambda item: (str(item["file"]), int(item["line"]))),
        "suggested_disposition": "review-for-shared-abstraction",
    }


def _cluster_allowed(cluster: dict[str, Any], *, include_tests: bool) -> bool:
    candidates = cluster.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        return False
    for candidate in candidates:
        file_path = str(candidate.get("file", ""))
        if _should_skip_path(file_path):
            return False
        if not include_tests and _is_test_file(file_path):
            return False
    return True


def _should_skip_path(relative_path: str) -> bool:
    normalized = relative_path.strip("/")
    if not normalized or _is_generated_file(normalized):
        return True
    parts = Path(normalized).parts
    return any(part in EXCLUDED_PATH_PARTS for part in parts)


def _normalize_path(path: str) -> str:
    return path.strip().lstrip("./")
