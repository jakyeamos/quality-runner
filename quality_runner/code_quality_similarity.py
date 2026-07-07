from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import _is_generated_file, _is_test_file

DEFAULT_SIMILARITY_ENABLED = True
DEFAULT_SIMILARITY_THRESHOLD = 0.87
DEFAULT_SIMILARITY_MIN_LINES = 8
DEFAULT_SIMILARITY_MAX_PAIRS = 25
DEFAULT_SIMILARITY_TIMEOUT_SECONDS = 30
DEFAULT_SIMILARITY_INCLUDE_TESTS = False

SIMILARITY_CLUSTER_ID_PREFIX = "SIM"
RULE_ID_CLUSTER = "semantic-similarity-cluster"
RULE_ID_PAIR = "semantic-similarity-pair"

TS_EXTENSIONS = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
PY_EXTENSIONS = {".py"}
RS_EXTENSIONS = {".rs"}

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


def semantic_similarity_scan(
    repo_root: Path,
    *,
    policy: dict[str, Any],
    disabled_groups: set[str],
) -> dict[str, Any]:
    if "deduplicate" in disabled_groups or not policy.get("similarity_enabled", True):
        return _skipped_result(repo_root, reason="disabled")

    tools = _select_tools(repo_root)
    if not tools:
        return {"clusters": [], "findings": [], "scanner_status": []}

    threshold = float(policy["similarity_threshold"])
    min_lines = int(policy["similarity_min_lines"])
    max_pairs = int(policy["similarity_max_pairs"])
    timeout = int(policy["similarity_timeout_seconds"])
    include_tests = bool(policy["similarity_include_tests"])

    clusters: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    scanner_status: list[dict[str, Any]] = []

    for tool, _language in tools:
        binary = shutil.which(tool)
        if binary is None:
            scanner_status.append(_status_entry(tool=tool, status="missing"))
            continue

        command = _build_command(
            binary=binary,
            repo_root=repo_root,
            tool=tool,
            threshold=threshold,
            min_lines=min_lines,
            include_tests=include_tests,
        )
        try:
            completed = subprocess.run(
                command,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            scanner_status.append(
                _status_entry(
                    tool=tool,
                    status="failed",
                    command=command,
                    exit_code=None,
                    stderr_tail=_tail(error.stderr),
                    stdout_tail=_tail(error.stdout),
                )
            )
            continue

        status = "executed" if completed.returncode == 0 else "failed"
        scanner_status.append(
            _status_entry(
                tool=tool,
                status=status,
                command=command,
                exit_code=completed.returncode,
                stderr_tail=_tail(completed.stderr),
                stdout_tail=_tail(completed.stdout),
            )
        )
        if status != "executed":
            continue

        parsed = _parse_output(
            completed.stdout,
            source=tool,
            threshold=threshold,
            include_tests=include_tests,
        )
        clusters.extend(parsed)
        if len(clusters) >= max_pairs:
            clusters = clusters[:max_pairs]
            break

    clusters = clusters[:max_pairs]
    for index, cluster in enumerate(clusters, start=1):
        cluster["id"] = f"{SIMILARITY_CLUSTER_ID_PREFIX}-{index:03d}"
        findings.append(_cluster_finding(cluster, source=str(cluster.get("source", ""))))

    return {
        "clusters": clusters,
        "findings": findings,
        "scanner_status": scanner_status,
    }


def _skipped_result(repo_root: Path, *, reason: str) -> dict[str, Any]:
    tools = [tool for tool, _ in _select_tools(repo_root)]
    status = "skipped" if reason == "disabled" else "missing"
    return {
        "clusters": [],
        "findings": [],
        "scanner_status": [_status_entry(tool=tool, status=status) for tool in tools],
    }


def _select_tools(repo_root: Path) -> list[tuple[str, str]]:
    extensions = _repo_extensions(repo_root)
    tools: list[tuple[str, str]] = []
    if extensions & TS_EXTENSIONS:
        tools.append(("similarity-ts", "typescript"))
    if extensions & PY_EXTENSIONS:
        tools.append(("similarity-py", "python"))
    if extensions & RS_EXTENSIONS:
        tools.append(("similarity-rs", "rust"))
    return tools


def _repo_extensions(repo_root: Path) -> set[str]:
    found: set[str] = set()
    for _current_root, dir_names, file_names in os.walk(repo_root):
        dir_names[:] = [
            name
            for name in dir_names
            if name not in EXCLUDED_PATH_PARTS and not name.startswith(".git")
        ]
        for file_name in file_names:
            suffix = Path(file_name).suffix.lower()
            if suffix:
                found.add(suffix)
            if found >= TS_EXTENSIONS | PY_EXTENSIONS | RS_EXTENSIONS:
                return found
    return found


def _build_command(
    *,
    binary: str,
    repo_root: Path,
    tool: str,
    threshold: float,
    min_lines: int,
    include_tests: bool,
) -> list[str]:
    command = [binary, str(repo_root), "--threshold", str(threshold), "--min-lines", str(min_lines)]
    if tool == "similarity-ts":
        command.extend(
            [
                "--cross-file",
                "--exclude",
                ".quality-runner",
                "--exclude",
                "node_modules",
                "--exclude",
                "dist",
                "--exclude",
                "build",
            ]
        )
    elif tool == "similarity-rs" and not include_tests:
        command.append("--skip-test")
    return command


def _parse_output(
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
    filtered = [candidate for candidate in candidates if not _should_skip_path(str(candidate["file"]))]
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


def _cluster_finding(cluster: dict[str, Any], *, source: str) -> dict[str, Any]:
    candidates = cluster["candidates"]
    first = candidates[0]
    similarity = float(cluster.get("similarity", 0.0))
    similarity_pct = similarity if similarity > 1 else similarity * 100
    avg_lines = sum(int(item.get("line_count", 1)) for item in candidates) / len(candidates)
    rule_id = RULE_ID_PAIR if str(cluster.get("kind")) == "pair" else RULE_ID_CLUSTER
    pair_summary = " <-> ".join(
        _candidate_label(item) for item in candidates[:2]
    )
    if len(candidates) > 2:
        pair_summary = f"{pair_summary} (+{len(candidates) - 2} more)"
    score_text = ""
    if cluster.get("score") is not None:
        score_text = f", score {cluster['score']}"
    evidence = (
        f"{source} found {similarity_pct:.2f}% similarity across {len(candidates)} functions"
        f"{score_text}: {pair_summary}"
    )
    severity = "warning" if similarity_pct >= 90.0 and avg_lines >= 8 else "observation"
    if similarity_pct >= 95.0:
        confidence = "high"
    elif similarity_pct >= float(cluster.get("threshold", DEFAULT_SIMILARITY_THRESHOLD)) * 100:
        confidence = "medium"
    else:
        confidence = "medium"
    finding = _finding(
        category="deduplicate",
        severity=severity,
        confidence=confidence,
        file=str(first["file"]),
        line=int(first["line"]),
        rule_id=rule_id,
        evidence=evidence,
        expected_improvement=(
            "Extract shared logic only when the call sites share domain semantics; "
            "otherwise document why the similarity is intentional."
        ),
        risk="Similar logic can drift across bug fixes and create inconsistent behavior.",
        verification=(
            "Rerun Quality Runner and the relevant similarity scanner; confirm this cluster "
            "is fixed, accepted, or intentionally duplicated."
        ),
        remediation_bucket="duplicate consolidation and helper extraction",
    )
    finding["fingerprint"] = _stable_similarity_fingerprint(rule_id, candidates, similarity_pct)
    return finding


def _candidate_label(candidate: dict[str, Any]) -> str:
    file_path = str(candidate["file"])
    line = int(candidate["line"])
    end_line = int(candidate.get("end_line", line))
    name = candidate.get("name")
    if name:
        return f"{file_path}:{line}-{end_line} {name}"
    return f"{file_path}:{line}-{end_line}"


def _stable_similarity_fingerprint(
    rule_id: str,
    candidates: list[dict[str, Any]],
    similarity_pct: float,
) -> str:
    parts = []
    for candidate in sorted(candidates, key=lambda item: (str(item.get("file", "")), str(item.get("name", "")))):
        parts.append(
            f"{candidate.get('file', '')}:{candidate.get('name', '')}"
        )
    normalized = " ".join(parts)
    payload = f"{rule_id}:{normalized}:{round(similarity_pct, 2)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _normalize_path(path: str) -> str:
    return path.strip().lstrip("./")


def _status_entry(
    *,
    tool: str,
    status: str,
    command: list[str] | None = None,
    exit_code: int | None = None,
    stderr_tail: str = "",
    stdout_tail: str = "",
) -> dict[str, Any]:
    entry: dict[str, Any] = {"tool": tool, "status": status}
    if command is not None:
        entry["command"] = command
    if exit_code is not None:
        entry["exit_code"] = exit_code
    if stderr_tail:
        entry["stderr_tail"] = stderr_tail
    if stdout_tail:
        entry["stdout_tail"] = stdout_tail
    return entry


def _tail(value: str | bytes | None, *, limit: int = 500) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    if len(text) <= limit:
        return text
    return text[-limit:]
