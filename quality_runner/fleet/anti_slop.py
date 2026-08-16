from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner.artifacts import write_json
from quality_runner.fleet.anti_slop_support import (
    ANTI_SLOP_DETECTOR,
    ANTI_SLOP_DETECTOR_SCHEMA,
    ANTI_SLOP_FORMATS,
    ANTI_SLOP_PACKAGE,
    ANTI_SLOP_PRESET,
    ANTI_SLOP_SOURCE_SHA,
    ANTI_SLOP_VERSION,
    JS_TS_SUFFIXES,
    SKIPPED_DIRECTORIES,
    _blocked_result,
    _cache_path,
    _git_output,
    _hash_value,
    _iso_timestamp,
    _parse_output,
    _producer_enabled_rules,
    _read_cached_result,
    _validate_producer,
    anti_slop_cache_key,
    merge_anti_slop_scan,
)

CommandRunner = Callable[[Sequence[str], Path, int], subprocess.CompletedProcess[str]]
Clock = Callable[[], datetime]

__all__ = [
    "ANTI_SLOP_DETECTOR",
    "ANTI_SLOP_DETECTOR_SCHEMA",
    "ANTI_SLOP_FORMATS",
    "ANTI_SLOP_PACKAGE",
    "ANTI_SLOP_PRESET",
    "ANTI_SLOP_SOURCE_SHA",
    "ANTI_SLOP_VERSION",
    "anti_slop_cache_key",
    "merge_anti_slop_scan",
    "run_anti_slop_detector",
]


def run_anti_slop_detector(
    *,
    target_root: Path,
    target_sha: str,
    qr_version: str,
    anti_slop_root: Path,
    preset: str = ANTI_SLOP_PRESET,
    output_format: str = "json",
    timeout_seconds: int = 600,
    cache_root: Path | None = None,
    command_runner: CommandRunner | None = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Run the pinned Anti-Slop producer and return a fail-closed evidence receipt."""
    if preset != ANTI_SLOP_PRESET:
        raise ValueError(f"unsupported anti-slop preset: {preset}")
    if output_format not in ANTI_SLOP_FORMATS:
        raise ValueError(f"unsupported anti-slop output format: {output_format}")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    root = target_root.expanduser().resolve()
    producer_root = anti_slop_root.expanduser().resolve()
    now = clock or (lambda: datetime.now(UTC))
    scan_time = _iso_timestamp(now())
    configuration = {
        "files": ["."],
        "format": output_format,
        "ignores": [".next", "build", "coverage", "dist", "node_modules"],
        "mode": "audit",
        "preset": preset,
    }
    configuration_hash = _hash_value(configuration)
    base = {
        "schema": ANTI_SLOP_DETECTOR_SCHEMA,
        "detector": ANTI_SLOP_DETECTOR,
        "applicable": False,
        "status": "blocked",
        "target_sha": target_sha,
        "qr_version": qr_version,
        "producer": {
            "name": ANTI_SLOP_PACKAGE,
            "version": ANTI_SLOP_VERSION,
            "source_sha": ANTI_SLOP_SOURCE_SHA,
        },
        "ruleset_hash": "unavailable",
        "configuration_hash": configuration_hash,
        "enabled_rules": [],
        "scan_time": scan_time,
        "cache_key": "unavailable",
        "finding_count": 0,
        "overlap_count": 0,
        "relations": [],
        "refresh_required": True,
    }

    compatibility = _js_ts_compatibility(root)
    if not compatibility["compatible"]:
        return {
            "status": "not_applicable",
            "receipt": {
                **base,
                "status": "not_applicable",
                "applicable": False,
                "command_result": {"status": "not_run", "reason": compatibility["reason"]},
                "compatibility": compatibility,
                "refresh_required": False,
            },
            "findings": [],
        }
    base["applicable"] = True
    base["compatibility"] = compatibility

    target_head = _git_output(root, "rev-parse", "HEAD")
    if target_head != target_sha:
        return _blocked_result(
            base,
            f"target SHA mismatch: expected {target_sha}, observed {target_head or 'unavailable'}",
            command_result={"status": "not_run", "reason": "target SHA mismatch"},
        )
    source_error = _validate_producer(producer_root)
    if source_error is not None:
        return _blocked_result(
            base,
            source_error,
            command_result={"status": "not_run", "reason": source_error},
        )

    node = shutil.which("node")
    if node is None:
        return _blocked_result(
            base,
            "required node executable is unavailable",
            command_result={"status": "not_run", "reason": "node executable is unavailable"},
        )
    enabled_rules, ruleset_resolution = _producer_enabled_rules(
        producer_root, node, preset, timeout_seconds
    )
    if enabled_rules is None:
        return _blocked_result(
            base,
            "anti-slop producer did not expose a valid enabled-rule set",
            command_result={"status": "failed", **ruleset_resolution},
        )
    ruleset_hash = _hash_value({"preset": preset, "enabled_rules": enabled_rules})
    cache_key = anti_slop_cache_key(
        target_sha=target_sha,
        qr_version=qr_version,
        ruleset_hash=ruleset_hash,
        configuration_hash=configuration_hash,
    )
    base.update(
        {
            "ruleset_hash": ruleset_hash,
            "enabled_rules": enabled_rules,
            "cache_key": f"sha256:{cache_key}",
            "ruleset_resolution": ruleset_resolution,
        }
    )
    cache_path = _cache_path(cache_root, cache_key)
    cached = _read_cached_result(cache_path, base)
    if cached is not None:
        cached_receipt = dict(cached["receipt"])
        cached_receipt["command_result"] = {
            **dict(cached_receipt.get("command_result") or {}),
            "status": "cached",
            "cache_path": str(cache_path),
        }
        cached_receipt["cache_hit"] = True
        cached_receipt["refresh_required"] = False
        return {"status": "passed", "receipt": cached_receipt, "findings": cached["findings"]}

    command = [
        node,
        str(producer_root / "bin" / "anti-slop.mjs"),
        "check",
        ".",
        "--mode",
        "audit",
        "--format",
        output_format,
        "--preset",
        preset,
    ]
    runner = command_runner or _run_command
    try:
        completed = runner(command, root, timeout_seconds)
    except Exception as error:  # the detector boundary must never look like a clean scan
        return _blocked_result(
            base,
            f"anti-slop execution failed: {type(error).__name__}: {error}",
            command_result={"status": "failed", "reason": str(error)},
        )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    command_result = {
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "format": output_format,
        "command": [
            "node",
            "bin/anti-slop.mjs",
            "check",
            ".",
            "--mode",
            "audit",
            "--format",
            output_format,
            "--preset",
            preset,
        ],
        "stdout_sha256": _sha256(stdout.encode("utf-8")),
        "stderr_sha256": _sha256(stderr.encode("utf-8")),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr_bytes": len(stderr.encode("utf-8")),
    }
    if completed.returncode != 0:
        return _blocked_result(
            base, "anti-slop command returned a failure", command_result=command_result
        )
    try:
        parsed_findings = _parse_output(stdout, output_format, root)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        return _blocked_result(
            base,
            f"anti-slop output is malformed: {error}",
            command_result={**command_result, "status": "failed", "reason": "malformed output"},
        )
    receipt = {
        **base,
        "status": "passed",
        "command_result": command_result,
        "finding_count": len(parsed_findings),
        "refresh_required": False,
    }
    result = {"status": "passed", "receipt": receipt, "findings": parsed_findings}
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(cache_path, result)
    return result


def _js_ts_compatibility(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        return {"compatible": False, "reason": "target repository is unavailable", "file_count": 0}
    count = 0
    for _current, directories, files in os.walk(root):
        directories[:] = sorted(
            directory for directory in directories if directory not in SKIPPED_DIRECTORIES
        )
        count += sum(Path(name).suffix.lower() in JS_TS_SUFFIXES for name in files)
        if count:
            return {
                "compatible": True,
                "reason": "JavaScript or TypeScript sources detected",
                "file_count": count,
            }
    return {
        "compatible": False,
        "reason": "no JavaScript or TypeScript sources detected",
        "file_count": 0,
    }


def _sha256(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _run_command(
    command: Sequence[str], cwd: Path, timeout_seconds: int
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else error.stderr or ""
        return subprocess.CompletedProcess(
            list(command), 124, stdout=stdout, stderr=stderr or "anti-slop detector timed out"
        )
