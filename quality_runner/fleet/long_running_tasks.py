from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import MAX_DOCUMENT_BYTES, relative_path

ANNOTATION = re.compile(
    r"^[ \t]*(?:#|//|/\*+|\*)[ \t]*quality-runner:\s*long-running-task"
    r"(?:\s+id[=:]([\w.-]+))?",
    re.I | re.M,
)
WORKFLOW_TIMEOUT = re.compile(r"timeout-minutes\s*:\s*(\d+)", re.I)
COMMAND_TIMEOUT = re.compile(
    r"(?:^|\s)(?:timeout\s+|--timeout(?:-seconds)?(?:=|\s+))(\d+)(?:\s|$)", re.I
)
MIN_WORKFLOW_MINUTES = 5
MIN_COMMAND_SECONDS = 300
MAX_SOURCE_FILES = 240

HEARTBEAT_MARKERS = re.compile(
    r"heartbeat|progress|processed|completed|percent[_ -]?complete|current[_ -]?phase",
    re.I,
)
DIAGNOSTIC_MARKERS = re.compile(
    r"elapsed|started[_ -]?at|updated[_ -]?at|last[_ -]?progress|stalled|"
    r"\b(?:eta|phase|status|total)\b",
    re.I,
)
BOUND_MARKERS = re.compile(
    r"timeout|deadline|max[_ -]?(?:items|pages|attempts|seconds)|\blimit\b|batch[_ -]?size|chunk[_ -]?size|concurren|cancel",
    re.I,
)
EFFICIENCY_MARKERS = re.compile(
    r"cache|memo|incremental|checkpoint|cursor|materiali[sz]e|precompute|single[_ -]?pass|deduplicat|\breuse\b|\bbatch\b|\bchunk\b",
    re.I,
)

IGNORED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "vendor",
    ".quality-runner",
}
SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".rb",
    ".sh",
    ".bash",
    ".zsh",
    ".yml",
    ".yaml",
}


def assess_long_running_tasks(root: Path) -> dict[str, dict[str, Any]]:
    candidates = _discover_candidates(root)
    if not candidates:
        return {
            dimension: {
                "score": None,
                "status": "not_applicable",
                "applicability": "not_applicable",
                "message": (
                    "No long-running task was identified from an explicit Quality Runner "
                    "annotation or a concrete timeout declaration. Task names alone do not qualify."
                ),
                "evidence": [],
            }
            for dimension in (
                "long_running_task_observability",
                "long_running_task_optimization",
            )
        }

    return {
        "long_running_task_observability": _assessment(
            candidates,
            first="heartbeat",
            second="diagnostics",
            label="heartbeat and diagnostic",
        ),
        "long_running_task_optimization": _assessment(
            candidates,
            first="bounded",
            second="efficiency",
            label="boundedness and optimization",
        ),
    }


def _assessment(
    candidates: list[dict[str, Any]], *, first: str, second: str, label: str
) -> dict[str, Any]:
    scores = [
        4 if item[first] and item[second] else 2 if item[first] or item[second] else 0
        for item in candidates
    ]
    score = min(scores)
    status = "maintained" if score == 4 else "partial" if score == 2 else "missing"
    deficient = [
        item for item, item_score in zip(candidates, scores, strict=True) if item_score < 4
    ]
    message = (
        f"All {len(candidates)} identified long-running task(s) expose {label} evidence."
        if not deficient
        else f"{len(deficient)} of {len(candidates)} identified long-running task(s) lack complete {label} evidence."
    )
    return {
        "score": score,
        "status": status,
        "applicability": "applicable",
        "message": message,
        "evidence": [
            {
                "path": str(item["path"]),
                "detail": (
                    f"{item['qualification']}; {first}={'present' if item[first] else 'missing'}; "
                    f"{second}={'present' if item[second] else 'missing'}"
                ),
            }
            for item in candidates[:12]
        ],
    }


def _discover_candidates(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in _source_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in ANNOTATION.finditer(text):
            window = _window(text, match.start())
            candidates.append(
                _candidate(
                    root,
                    path,
                    window,
                    f"explicit long-running-task annotation{f' ({match.group(1)})' if match.group(1) else ''}",
                )
            )
        if _is_workflow(path):
            for match in WORKFLOW_TIMEOUT.finditer(text):
                minutes = int(match.group(1))
                if minutes >= MIN_WORKFLOW_MINUTES:
                    candidates.append(
                        _candidate(
                            root,
                            path,
                            _window(text, match.start()),
                            f"workflow timeout-minutes={minutes}",
                        )
                    )
        if path.name in {"package.json", "Makefile", "makefile"}:
            for match in COMMAND_TIMEOUT.finditer(text):
                seconds = int(match.group(1))
                if seconds >= MIN_COMMAND_SECONDS:
                    candidates.append(
                        _candidate(
                            root,
                            path,
                            _window(text, match.start()),
                            f"command timeout={seconds}s",
                        )
                    )
    return _deduplicate(candidates)


def _candidate(root: Path, path: Path, text: str, qualification: str) -> dict[str, Any]:
    return {
        "path": relative_path(root, path),
        "qualification": qualification,
        "heartbeat": bool(HEARTBEAT_MARKERS.search(text)),
        "diagnostics": bool(DIAGNOSTIC_MARKERS.search(text)),
        "bounded": bool(BOUND_MARKERS.search(text)),
        "efficiency": bool(EFFICIENCY_MARKERS.search(text)),
    }


def _source_files(root: Path) -> list[Path]:
    preferred = [root / "package.json", root / "Makefile", root / "makefile"]
    selected = [path for path in preferred if path.is_file()]
    for path in sorted(root.rglob("*")):
        if len(selected) >= MAX_SOURCE_FILES:
            break
        if not path.is_file() or any(
            part in IGNORED_PARTS for part in path.relative_to(root).parts
        ):
            continue
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_DOCUMENT_BYTES:
                continue
        except OSError:
            continue
        if path not in selected:
            selected.append(path)
    return selected


def _window(text: str, offset: int, radius: int = 1800) -> str:
    return text[max(0, offset - radius) : min(len(text), offset + radius)]


def _is_workflow(path: Path) -> bool:
    parts = path.parts
    return ".github" in parts and "workflows" in parts and path.suffix.lower() in {".yml", ".yaml"}


def _deduplicate(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in candidates:
        key = json.dumps([item["path"], item["qualification"]], sort_keys=True)
        unique[key] = item
    return [unique[key] for key in sorted(unique)]
