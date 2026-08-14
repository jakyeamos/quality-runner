from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import relative_path

CHANGE_SURFACE_HOTSPOTS_SCHEMA = "quality-runner-change-surface-hotspots/v1"
_MAX_COMMITS = 240
_MAX_FILES = 500
_MAX_HOTSPOTS = 32
_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
_SKIP_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
_TEST_PATH = re.compile(
    r"(^|/)(?:test|tests|spec|specs|__tests__)(/|$)|(?:^|/)(?:test_|.*[._](?:test|spec)\.)"
)
_HEADER = re.compile(r"^(?P<commit>[0-9a-f]{40})\t(?P<timestamp>\d+)$")
_JS_IMPORT = re.compile(r"(?:from|import\s*\(|require\s*\()\s*[\"'](?P<path>\.?\.?/[^\"']+)[\"']")
_PY_IMPORT = re.compile(r"(?:from|import)\s+(?P<path>\.+[A-Za-z0-9_./]+)")
_STRING_LITERAL = re.compile(
    r"(?P<quote>[\"'])(?P<value>[A-Za-z][A-Za-z0-9 _./:-]{5,72})(?P=quote)"
)


def assess_change_surface_hotspots(root: Path, as_of: str) -> dict[str, Any]:
    """Audit repository-wide change amplification without changing the checkout.

    The audit combines three independent evidence families: version-control
    co-change, local import/reference structure, and repeated literals that
    often indicate an un-tokenized concept. A file is surfaced only when at
    least two families agree, so a single noisy signal cannot become a gate.
    """

    resolved_root = root.expanduser().resolve()
    source_files = _source_files(resolved_root)
    history, history_error = _git_history(resolved_root)
    if history_error:
        return _unavailable(as_of, history_error, source_files)

    source_paths = {relative_path(resolved_root, path) for path in source_files}
    commit_counts: Counter[str] = Counter()
    cochange: dict[str, Counter[str]] = defaultdict(Counter)
    for commit in history:
        files = sorted(
            {
                path
                for path in commit["files"]
                if path in source_paths and not _TEST_PATH.search(path)
            }
        )
        for path in files:
            commit_counts[path] += 1
        for index, left in enumerate(files):
            for right in files[index + 1 :]:
                cochange[left][right] += 1
                cochange[right][left] += 1

    fan_in, fan_out = _dependency_counts(resolved_root, source_files, source_paths)
    repeated_literals = _repeated_literals(resolved_root, source_files)
    families = _hotspot_families(commit_counts, cochange, fan_in, fan_out, repeated_literals)
    hotspots = []
    for path, family_values in families.items():
        if len(family_values) < 2:
            continue
        history_count = commit_counts[path]
        partner_count = len(cochange[path])
        inbound = fan_in[path]
        outbound = fan_out[path]
        literal_count = repeated_literals[path]
        risk = (
            min(history_count, 12) / 3
            + min(partner_count, 10) / 2
            + min(inbound, 8) / 2
            + min(outbound, 8) / 3
            + min(literal_count, 6) / 2
        )
        hotspots.append(
            {
                "path": path,
                "risk_score": round(risk, 3),
                "evidence_families": sorted(family_values),
                "commit_count": history_count,
                "cochange_partner_count": partner_count,
                "fan_in": inbound,
                "fan_out": outbound,
                "repeated_literal_count": literal_count,
            }
        )
    hotspots.sort(key=lambda item: (-float(item["risk_score"]), str(item["path"])))
    hotspots = hotspots[:_MAX_HOTSPOTS]

    enough_history = len(history) >= 10
    if not enough_history:
        score: int | None = 2
        status = "unknown"
        message = f"Change-surface hotspot evidence is unknown: only {len(history)} bounded Git commit(s) were available; at least 10 are needed for a useful co-change signal."
    elif not hotspots:
        score = 4
        status = "maintained"
        message = "No multi-signal change-surface hotspots were found in the bounded audit window."
    elif any(float(item["risk_score"]) >= 8 for item in hotspots):
        score = 2
        status = "attention"
        message = f"{len(hotspots)} multi-signal change-surface hotspot(s) need maintainability review before broadening behavior."
    else:
        score = 3
        status = "validated"
        message = (
            f"{len(hotspots)} bounded change-surface hotspot(s) were identified for planned review."
        )

    evidence = [
        {
            "path": item["path"],
            "detail": (
                f"families={','.join(item['evidence_families'])}; commits={item['commit_count']}; "
                f"co-change partners={item['cochange_partner_count']}; fan-in={item['fan_in']}; "
                f"fan-out={item['fan_out']}; repeated literals={item['repeated_literal_count']}"
            ),
        }
        for item in hotspots[:12]
    ]
    if not evidence:
        evidence = [
            {
                "path": ".",
                "detail": f"bounded history commits={len(history)}; source files={len(source_files)}",
            }
        ]
    return {
        "schema": CHANGE_SURFACE_HOTSPOTS_SCHEMA,
        "as_of": as_of,
        "score": score,
        "status": status,
        "message": message,
        "evidence": evidence,
        "hotspots": hotspots,
        "summary": {
            "source_file_count": len(source_files),
            "history_commit_count": len(history),
            "history_source_commit_count": sum(1 for count in commit_counts.values() if count),
            "multi_signal_hotspot_count": len(hotspots),
            "high_risk_hotspot_count": sum(
                1 for item in hotspots if float(item["risk_score"]) >= 8
            ),
            "evidence_family_counts": dict(
                sorted(
                    Counter(
                        family for item in hotspots for family in item["evidence_families"]
                    ).items()
                )
            ),
        },
        "methodology": {
            "history_window": f"up to {_MAX_COMMITS} commits on the scanned checkout",
            "hotspot_requires": "at least two independent evidence families",
            "families": ["logical_cochange", "structural_coupling", "repeated_concepts"],
            "tokenization_is": "a remediation hypothesis, not a score input",
        },
        "limitations": [
            "Co-change is a maintenance signal, not proof that a design is wrong.",
            "Structural coupling is derived from bounded local imports and does not model runtime or generated dependencies.",
            "Repeated literals are candidates for shared concepts; they are not automatically safe to centralize.",
            "The audit does not modify code, generate abstractions, or replace reviewer judgment about ownership and compatibility.",
        ],
    }


def _unavailable(as_of: str, reason: str, source_files: list[Path]) -> dict[str, Any]:
    return {
        "schema": CHANGE_SURFACE_HOTSPOTS_SCHEMA,
        "as_of": as_of,
        "score": 2,
        "status": "unknown",
        "message": f"Change-surface hotspot evidence is unavailable: {reason}",
        "evidence": [{"path": ".", "detail": reason}],
        "hotspots": [],
        "summary": {
            "source_file_count": len(source_files),
            "history_commit_count": 0,
            "history_source_commit_count": 0,
            "multi_signal_hotspot_count": 0,
            "high_risk_hotspot_count": 0,
            "evidence_family_counts": {},
        },
        "methodology": {
            "history_window": f"up to {_MAX_COMMITS} commits on the scanned checkout",
            "hotspot_requires": "at least two independent evidence families",
            "families": ["logical_cochange", "structural_coupling", "repeated_concepts"],
            "tokenization_is": "a remediation hypothesis, not a score input",
        },
        "limitations": ["Git history was unavailable, so no maintainability verdict is claimed."],
    }


def _git_history(root: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--max-count={_MAX_COMMITS}",
                "--format=%H%x09%ct",
                "--name-only",
                "--no-renames",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return [], str(error)
    history: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in result.stdout.splitlines():
        header = _HEADER.match(line.strip())
        if header:
            if current is not None:
                history.append(current)
            current = {
                "commit": header.group("commit"),
                "timestamp": int(header.group("timestamp")),
                "files": [],
            }
            continue
        if current is not None and line.strip():
            current["files"].append(line.strip())
    if current is not None:
        history.append(current)
    return history, None


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    try:
        candidates = root.rglob("*")
    except OSError:
        return files
    for path in candidates:
        if len(files) >= _MAX_FILES:
            break
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in _SKIP_DIRECTORIES for part in parts):
            continue
        files.append(path)
    return sorted(files)


def _dependency_counts(
    root: Path, files: list[Path], source_paths: set[str]
) -> tuple[Counter[str], Counter[str]]:
    fan_in: Counter[str] = Counter()
    fan_out: Counter[str] = Counter()
    for path in files:
        relative = relative_path(root, path)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        imports = [match.group("path") for match in _JS_IMPORT.finditer(content)]
        imports.extend(match.group("path") for match in _PY_IMPORT.finditer(content))
        targets = {
            target
            for target in (_resolve_import(root, path, raw, source_paths) for raw in imports)
            if target
        }
        fan_out[relative] = len(targets)
        for target in targets:
            fan_in[target] += 1
    return fan_in, fan_out


def _resolve_import(root: Path, source: Path, raw: str, source_paths: set[str]) -> str | None:
    if raw.startswith("./") or raw.startswith("../"):
        candidate = (source.parent / raw).resolve()
    elif raw.startswith("."):
        dots = len(raw) - len(raw.lstrip("."))
        module = raw[dots:].replace(".", "/")
        base = source.parent
        for _ in range(max(dots - 1, 0)):
            base = base.parent
        candidate = (base / module).resolve()
    else:
        return None
    candidates = [candidate]
    if candidate.suffix == "":
        candidates.extend(candidate.with_suffix(suffix) for suffix in sorted(_SOURCE_SUFFIXES))
        candidates.extend(candidate / f"index{suffix}" for suffix in sorted(_SOURCE_SUFFIXES))
    for value in candidates:
        try:
            relative = value.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative in source_paths and value != source:
            return relative
    return None


def _repeated_literals(root: Path, files: list[Path]) -> Counter[str]:
    occurrences: dict[str, set[str]] = defaultdict(set)
    ignored = {"return", "true", "false", "null", "undefined", "error", "warning", "info"}
    for path in files:
        relative = relative_path(root, path)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _STRING_LITERAL.finditer(content):
            value = match.group("value").strip().lower()
            if value in ignored or value.startswith(("http", "/", "./", "../")):
                continue
            occurrences[value].add(relative)
    repeated: Counter[str] = Counter()
    for files_for_value in occurrences.values():
        if len(files_for_value) < 2:
            continue
        for path in files_for_value:
            repeated[path] += 1
    return repeated


def _hotspot_families(
    commit_counts: Counter[str],
    cochange: dict[str, Counter[str]],
    fan_in: Counter[str],
    fan_out: Counter[str],
    repeated_literals: Counter[str],
) -> dict[str, set[str]]:
    paths = set(commit_counts) | set(cochange) | set(fan_in) | set(fan_out) | set(repeated_literals)
    result: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        if commit_counts[path] >= 3:
            result[path].add("logical_cochange")
        if len(cochange[path]) >= 2:
            result[path].add("logical_cochange")
        if fan_in[path] >= 2 or fan_out[path] >= 3:
            result[path].add("structural_coupling")
        if repeated_literals[path] >= 1:
            result[path].add("repeated_concepts")
    return result
