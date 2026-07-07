from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.code_quality_duplicates import _duplicate_clusters
from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import _verification_for_path
from quality_runner.code_quality_similarity_parse import parse_similarity_output

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


def similarity_policy_defaults(policy: dict[str, Any]) -> dict[str, Any]:
    similarity_enabled = policy.get("similarity_enabled")
    similarity_threshold = policy.get("similarity_threshold")
    similarity_min_lines = policy.get("similarity_min_lines")
    similarity_max_pairs = policy.get("similarity_max_pairs")
    similarity_timeout_seconds = policy.get("similarity_timeout_seconds")
    similarity_include_tests = policy.get("similarity_include_tests")
    return {
        "similarity_enabled": similarity_enabled
        if isinstance(similarity_enabled, bool)
        else DEFAULT_SIMILARITY_ENABLED,
        "similarity_threshold": similarity_threshold
        if isinstance(similarity_threshold, (int, float)) and 0 <= float(similarity_threshold) <= 1
        else DEFAULT_SIMILARITY_THRESHOLD,
        "similarity_min_lines": similarity_min_lines
        if isinstance(similarity_min_lines, int) and similarity_min_lines > 0
        else DEFAULT_SIMILARITY_MIN_LINES,
        "similarity_max_pairs": similarity_max_pairs
        if isinstance(similarity_max_pairs, int) and similarity_max_pairs > 0
        else DEFAULT_SIMILARITY_MAX_PAIRS,
        "similarity_timeout_seconds": similarity_timeout_seconds
        if isinstance(similarity_timeout_seconds, int) and similarity_timeout_seconds > 0
        else DEFAULT_SIMILARITY_TIMEOUT_SECONDS,
        "similarity_include_tests": similarity_include_tests
        if isinstance(similarity_include_tests, bool)
        else DEFAULT_SIMILARITY_INCLUDE_TESTS,
    }


def collect_deduplicate_scan(
    repo_root: Path,
    *,
    extracted_functions: list[dict[str, Any]],
    policy: dict[str, Any],
    disabled_groups: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, dict[str, str]]:
    if "deduplicate" in disabled_groups:
        return [], [], 0, {}

    duplicate_clusters = _duplicate_clusters(extracted_functions)
    findings: list[dict[str, Any]] = []
    for cluster in duplicate_clusters:
        first = cluster["candidates"][0]
        findings.append(
            _finding(
                category="deduplicate",
                severity="warning",
                confidence="medium",
                file=first["file"],
                line=first["line"],
                rule_id="near-duplicate-function",
                evidence=f"{cluster['id']} spans {len(cluster['candidates'])} functions.",
                expected_improvement=(
                    "Extract a shared helper only when the call sites share domain semantics."
                ),
                risk="Near-duplicate logic can drift across fixes.",
                verification=_verification_for_path(first["file"]),
                remediation_bucket="duplicate consolidation and helper extraction",
            )
        )

    similarity_result = semantic_similarity_scan(
        repo_root,
        policy=policy,
        disabled_groups=disabled_groups,
    )
    duplicate_clusters.extend(similarity_result["clusters"])
    findings.extend(similarity_result["findings"])
    semantic_similarity_tools = {
        str(entry["tool"]): str(entry["status"])
        for entry in similarity_result["scanner_status"]
        if isinstance(entry, dict) and isinstance(entry.get("tool"), str)
    }
    return (
        duplicate_clusters,
        findings,
        len(similarity_result["clusters"]),
        semantic_similarity_tools,
    )


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

        parsed = parse_similarity_output(
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


def _cluster_finding(cluster: dict[str, Any], *, source: str) -> dict[str, Any]:
    candidates = cluster["candidates"]
    first = candidates[0]
    similarity = float(cluster.get("similarity", 0.0))
    similarity_pct = similarity if similarity > 1 else similarity * 100
    avg_lines = sum(int(item.get("line_count", 1)) for item in candidates) / len(candidates)
    rule_id = RULE_ID_PAIR if str(cluster.get("kind")) == "pair" else RULE_ID_CLUSTER
    pair_summary = " <-> ".join(_candidate_label(item) for item in candidates[:2])
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
    for candidate in sorted(
        candidates, key=lambda item: (str(item.get("file", "")), str(item.get("name", "")))
    ):
        parts.append(f"{candidate.get('file', '')}:{candidate.get('name', '')}")
    normalized = " ".join(parts)
    payload = f"{rule_id}:{normalized}:{round(similarity_pct, 2)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


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
