from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner.fleet.behavior_contract import MAX_FILE_BYTES


def target(repository: dict[str, Any], root: Path) -> dict[str, str | None]:
    selected = object_value(repository.get("target_branch"))
    return {
        "branch": string_value(selected.get("branch")) or git_one(root, "branch", "--show-current"),
        "commit": string_value(selected.get("head")) or git_one(root, "rev-parse", "HEAD"),
    }


def read_object(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return {}, f"file exceeds {MAX_FILE_BYTES} bytes"
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, f"could not read valid JSON: {error}"
    return (value, None) if isinstance(value, dict) else ({}, "JSON root must be an object")


def git_lines(root: Path, *args: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, check=False, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


def git_one(root: Path, *args: str) -> str | None:
    return next(iter(git_lines(root, *args)), None)


def is_ancestor(root: Path, ancestor: str, target_commit: str) -> bool:
    try:
        return (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", ancestor, target_commit],
                cwd=root,
                check=False,
                capture_output=True,
                timeout=10,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def porcelain_path(line: str) -> str:
    value = line[3:].strip() if len(line) > 3 else ""
    return value.split(" -> ", maxsplit=1)[-1]


def gap(kind: str, message: str, **identity: str) -> dict[str, Any]:
    return {"kind": kind, "message": message, **identity}


def string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def object_values(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def object_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def future_timestamp(value: object, as_of: str) -> bool:
    parsed = iso_timestamp(value)
    observed = iso_timestamp(as_of)
    return bool(parsed and observed and parsed > observed)


def receipt_evidence_errors(
    result: dict[str, Any], producer_id: str | None, index: int
) -> list[str]:
    evidence = object_values(result.get("evidence"))
    level = result.get("verification_level")
    label = f"results[{index}]"
    if producer_id == "quality-runner":
        if level == "independent":
            return [f"{label} quality-runner cannot issue independent verification"]
        if level == "direct_surface":
            direct = [item for item in evidence if item.get("kind") == "direct_surface"]
            traces = [item for item in evidence if item.get("kind") == "edge_trace"]
            if len(direct) != 1 or len(traces) != 1:
                return [
                    f"{label} quality-runner direct_surface evidence requires one surface observation and one edge trace"
                ]
            trace = traces[0]
            if (
                trace.get("schema") != "quality-runner-edge-trace/v1"
                or not string_value(trace.get("environment"))
                or not string_value(trace.get("surface"))
                or not string_values(trace.get("categories"))
                or not isinstance(trace.get("trace_sha256"), str)
                or len(trace["trace_sha256"]) != 64
            ):
                return [f"{label} edge trace summary is incomplete"]
        elif result.get("status") == "passed":
            commands = [item for item in evidence if item.get("kind") == "bounded_command"]
            if level not in {"source", "automated"} or not commands:
                return [f"{label} quality-runner pass requires bounded command evidence"]
            command = commands[0]
            argv = string_values(command.get("argv"))
            hashes = [command.get("stdout_sha256"), command.get("stderr_sha256")]
            if not argv or command.get("exit_code") != 0:
                return [f"{label} bounded command must contain argv and exit_code 0"]
            if not all(isinstance(value, str) and len(value) == 64 for value in hashes):
                return [f"{label} bounded command must contain output SHA-256 digests"]
    if result.get("status") != "passed":
        return []
    if level == "direct_surface" and not any(
        item.get("kind") == "direct_surface"
        and string_value(item.get("surface"))
        and string_value(item.get("observation"))
        for item in evidence
    ):
        return [f"{label} direct_surface pass requires a surface and observation"]
    if level == "independent" and not any(
        item.get("kind") == "independent_review"
        and string_value(item.get("reviewer"))
        and string_value(item.get("observation"))
        for item in evidence
    ):
        return [f"{label} independent pass requires reviewer and observation evidence"]
    return []
