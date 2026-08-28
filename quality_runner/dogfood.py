from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.config import CONFIG_FILE_NAME
from quality_runner.schema_constants import (
    DOGFOOD_CAPTURE_SCHEMA,
    DOGFOOD_EVENT_SCHEMA,
    DOGFOOD_REPORT_SCHEMA,
)

STATE_ENV = "QUALITY_RUNNER_DOGFOOD_STATE_DIR"
DEFAULT_STATE_DIR = Path("~/.local/state/quality-runner/dogfood")


def state_directory(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    configured = os.environ.get(STATE_ENV)
    return Path(configured).expanduser().resolve() if configured else DEFAULT_STATE_DIR.expanduser()


def record_task_event(
    *,
    repo_root: Path,
    task_id: str,
    action: str,
    payload: dict[str, Any],
    operation_seconds: float,
    state_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Persist an idempotent, content-minimized event without changing task status."""
    started = time.monotonic()
    try:
        root = state_directory(state_dir)
        root.mkdir(parents=True, exist_ok=True)
        key = _privacy_key(root)
        repository = cast(dict[str, Any], payload.get("repository", {}))
        repository_identity = str(repository.get("identity") or _repository_identity(repo_root))
        dimensions = _dimensions(action, payload, operation_seconds)
        event_key = json.dumps(
            {
                "action": action,
                "run": payload.get("run_id") or payload.get("baseline_run_id"),
                "repo": repository_identity,
                "task": task_id,
                "status": payload.get("status"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        event_id = hmac.new(key, event_key.encode(), hashlib.sha256).hexdigest()
        event = {
            "schema": DOGFOOD_EVENT_SCHEMA,
            "event_id": event_id,
            "event_name": f"quality_runner.task.{action.replace('_', '.')}",
            "occurred_at": datetime.now(UTC).isoformat(),
            "repository_id": _private_id(key, repository_identity),
            "task_id": _private_id(key, task_id),
            "quality_runner_version": __version__,
            "dimensions": dimensions,
        }
        inserted = _insert_event(root / "events.sqlite3", event)
        return {
            "schema": DOGFOOD_CAPTURE_SCHEMA,
            "status": "recorded" if inserted else "duplicate",
            "event_id": event_id,
            "capture_seconds": round(time.monotonic() - started, 6),
        }
    except (OSError, sqlite3.Error, ValueError) as error:
        return {
            "schema": DOGFOOD_CAPTURE_SCHEMA,
            "status": "degraded",
            "error": {"code": "dogfood_capture_unavailable", "message": str(error)},
            "capture_seconds": round(time.monotonic() - started, 6),
        }


def dogfood_report(state_dir: str | Path | None = None) -> dict[str, Any]:
    root = state_directory(state_dir)
    database = root / "events.sqlite3"
    if not database.is_file():
        return _empty_report("empty")
    try:
        with sqlite3.connect(database) as connection:
            rows = connection.execute(
                "SELECT occurred_at, event_name, repository_id, task_id, dimensions_json "
                "FROM events ORDER BY occurred_at"
            ).fetchall()
    except sqlite3.Error as error:
        report = _empty_report("degraded")
        report["error"] = {"code": "dogfood_store_unreadable", "message": str(error)}
        return report

    events = [
        {
            "occurred_at": row[0],
            "event_name": row[1],
            "repository_id": row[2],
            "task_id": row[3],
            "dimensions": json.loads(row[4]),
        }
        for row in rows
    ]
    names = Counter(str(item["event_name"]) for item in events)
    durations = [
        float(item["dimensions"]["operation_seconds"])
        for item in events
        if isinstance(item["dimensions"].get("operation_seconds"), (int, float))
    ]
    checks = [
        item for item in events if str(item["event_name"]).endswith(("check", "release.check"))
    ]
    release_checks = [item for item in events if str(item["event_name"]).endswith("release.check")]
    eligible = sum(item["dimensions"].get("release_eligible") is True for item in release_checks)
    tasks = {(item["repository_id"], item["task_id"]) for item in events}
    repositories = {item["repository_id"] for item in events}
    status_counts = Counter(
        str(item["dimensions"]["status"])
        for item in checks
        if isinstance(item["dimensions"].get("status"), str)
    )
    task_timings = _task_timings(events)
    first_feedback = [
        item["first_feedback_seconds"]
        for item in task_timings.values()
        if "first_feedback_seconds" in item
    ]
    release_cycles = [
        item["release_check_seconds"]
        for item in task_timings.values()
        if "release_check_seconds" in item
    ]
    tasks_with_release = sum("release_check_seconds" in item for item in task_timings.values())
    return {
        "schema": DOGFOOD_REPORT_SCHEMA,
        "status": "passed",
        "privacy": {
            "raw_prompts": False,
            "source_paths": False,
            "finding_bodies": False,
            "identifiers": "local_hmac_sha256",
        },
        "coverage": {
            "events": len(events),
            "tasks": len(tasks),
            "repositories": len(repositories),
            "event_counts": dict(sorted(names.items())),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "feedback_loop": {
            "checks": len(checks),
            "release_checks": len(release_checks),
            "tasks_with_release_check": tasks_with_release,
            "task_release_coverage_rate": round(tasks_with_release / len(tasks), 4)
            if tasks
            else None,
            "eligible_release_checks": eligible,
            "release_eligibility_rate": round(eligible / len(release_checks), 4)
            if release_checks
            else None,
            "operation_seconds_p50": _percentile(durations, 0.5),
            "operation_seconds_p95": _percentile(durations, 0.95),
            "time_to_first_feedback_seconds_p50": _percentile(first_feedback, 0.5),
            "time_to_first_feedback_seconds_p95": _percentile(first_feedback, 0.95),
            "task_to_release_check_seconds_p50": _percentile(release_cycles, 0.5),
            "task_to_release_check_seconds_p95": _percentile(release_cycles, 0.95),
            "new_enforced_findings": sum(
                int(item["dimensions"].get("new_enforced_findings", 0)) for item in checks
            ),
            "resolved_findings": sum(
                int(item["dimensions"].get("resolved_findings", 0)) for item in checks
            ),
            "changed_paths": sum(
                int(item["dimensions"].get("changed_path_count", 0)) for item in checks
            ),
            "gate_failures": sum(
                int(item["dimensions"].get("gate_failure_count", 0)) for item in checks
            ),
            "cache_hits": sum(int(item["dimensions"].get("cache_hits", 0)) for item in checks),
            "cache_misses": sum(int(item["dimensions"].get("cache_misses", 0)) for item in checks),
        },
    }


def codex_hook_payload(
    payload: dict[str, Any], *, state_dir: str | Path | None = None
) -> dict[str, Any]:
    cwd = payload.get("cwd")
    session_id = payload.get("session_id")
    event = payload.get("hook_event_name")
    if not isinstance(cwd, str) or not isinstance(session_id, str) or not isinstance(event, str):
        return {"systemMessage": "Quality Runner hook received an invalid lifecycle payload."}
    repo_root = _git_root(Path(cwd))
    if repo_root is None or not (repo_root / CONFIG_FILE_NAME).is_file():
        return {}
    task_id = f"codex-{hashlib.sha256(session_id.encode()).hexdigest()[:24]}"
    from quality_runner.task_prevention import (
        check_task,
        current_task_snapshot,
        load_task_record,
        start_task,
    )

    record_path = repo_root / ".quality-runner" / "tasks" / f"{task_id}.json"
    if event in {"SessionStart", "UserPromptSubmit", "PreToolUse"}:
        if record_path.is_file():
            return {}
        started = time.monotonic()
        result = start_task(repo_root, task_id=task_id, baseline_ref=None, intent_path=None)
        capture = record_task_event(
            repo_root=repo_root,
            task_id=task_id,
            action="start",
            payload=result,
            operation_seconds=time.monotonic() - started,
            state_dir=state_dir,
        )
        result["dogfood_telemetry"] = capture
        if result.get("status") != "started":
            return {"decision": "block", "reason": _hook_failure_reason(result)}
        capture_notice = _capture_notice(capture)
        return {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": (
                    "Quality Runner automatically captured this task baseline. Run fast checks "
                    "at coherent boundaries; the Stop hook enforces the authoritative release check."
                    f"{capture_notice}"
                ),
            }
        }
    if event != "Stop":
        return {}
    if not record_path.is_file():
        return {
            "decision": "block",
            "reason": "Start the enrolled Quality Runner task baseline before completion.",
        }
    record = load_task_record(repo_root, task_id)
    snapshot = current_task_snapshot(repo_root, task_id)
    baseline = snapshot["baseline"]
    current = snapshot["current"]
    if baseline.get("snapshot_digest") == current.get("snapshot_digest"):
        capture = record_task_event(
            repo_root=repo_root,
            task_id=task_id,
            action="stop_unchanged",
            payload={"status": "pass", "repository": current.get("repository", {})},
            operation_seconds=0.0,
            state_dir=state_dir,
        )
        return _capture_system_message(capture)
    last = _last_release_check(repo_root, record, str(current.get("snapshot_digest")))
    if last is not None:
        return {}
    started = time.monotonic()
    result = check_task(repo_root, task_id=task_id, require_release=True)
    capture = record_task_event(
        repo_root=repo_root,
        task_id=task_id,
        action="release_check",
        payload=result,
        operation_seconds=time.monotonic() - started,
        state_dir=state_dir,
    )
    result["dogfood_telemetry"] = capture
    if result.get("release_readiness", {}).get("eligible") is True:
        return _capture_system_message(capture)
    return {"decision": "block", "reason": _hook_failure_reason(result)}


def dogfood_command_payload(args: Any) -> dict[str, Any]:
    if args.dogfood_action == "report":
        return dogfood_report(args.state_dir)
    if args.dogfood_action == "codex-hook":
        try:
            payload = json.load(sys.stdin)
        except (json.JSONDecodeError, OSError) as error:
            return {"systemMessage": f"Quality Runner hook input was unreadable: {error}"}
        if not isinstance(payload, dict):
            return {"systemMessage": "Quality Runner hook input must be a JSON object."}
        return codex_hook_payload(cast(dict[str, Any], payload), state_dir=args.state_dir)
    return {"schema": DOGFOOD_REPORT_SCHEMA, "status": "invalid"}


def _dimensions(action: str, payload: dict[str, Any], operation_seconds: float) -> dict[str, Any]:
    delta = cast(dict[str, Any], payload.get("delta", {}))
    counts = cast(dict[str, Any], delta.get("counts", {}))
    gates = cast(list[dict[str, Any]], payload.get("gate_results", []))
    analysis = cast(dict[str, Any], payload.get("analysis", {}))
    cache = cast(dict[str, Any], analysis.get("cache_summary", {}))
    analyses = cast(dict[str, Any], cache.get("analyses", {}))
    cache_rows = [item for item in analyses.values() if isinstance(item, dict)]
    readiness = cast(dict[str, Any], payload.get("release_readiness", {}))
    return {
        "action": action,
        "status": payload.get("status"),
        "mode": payload.get("mode"),
        "release_enforcement": payload.get("release_enforcement"),
        "release_eligible": readiness.get("eligible"),
        "operation_seconds": round(operation_seconds, 6),
        "analysis_seconds": _nested_number(analysis, "performance", "elapsed_seconds"),
        "changed_path_count": len(cast(list[Any], payload.get("changed_paths", []))),
        "new_enforced_findings": int(counts.get("new_enforced", 0)),
        "persisted_findings": int(counts.get("persisted", 0)),
        "resolved_findings": int(counts.get("resolved", 0)),
        "unknown_findings": int(counts.get("unknown", 0)),
        "gate_count": len(gates),
        "gate_failure_count": sum(item.get("status") != "passed" for item in gates),
        "cache_hits": sum(int(item.get("cache_hits", 0)) for item in cache_rows),
        "cache_misses": sum(int(item.get("cache_misses", 0)) for item in cache_rows),
    }


def _privacy_key(root: Path) -> bytes:
    path = root / "identity.key"
    if path.is_file():
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError("dogfood identity key is invalid")
        return key
    key = secrets.token_bytes(32)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError("dogfood identity key is invalid") from None
        return key
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key)
    return key


def _insert_event(database: Path, event: dict[str, Any]) -> bool:
    with sqlite3.connect(database, timeout=5.0) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "event_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, event_name TEXT NOT NULL, "
            "repository_id TEXT NOT NULL, task_id TEXT NOT NULL, dimensions_json TEXT NOT NULL)"
        )
        cursor = connection.execute(
            "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (
                event["event_id"],
                event["occurred_at"],
                event["event_name"],
                event["repository_id"],
                event["task_id"],
                json.dumps(event["dimensions"], sort_keys=True, separators=(",", ":")),
            ),
        )
        return cursor.rowcount == 1


def _last_release_check(
    repo_root: Path, record: dict[str, Any], digest: str
) -> dict[str, Any] | None:
    for run_id in reversed(cast(list[str], record.get("checks", []))):
        path = repo_root / ".quality-runner" / "runs" / run_id / "task-check.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = payload.get("snapshot", {})
        if (
            payload.get("release_enforcement") == "required"
            and payload.get("release_readiness", {}).get("eligible") is True
            and snapshot.get("snapshot_digest") == digest
        ):
            return cast(dict[str, Any], payload)
    return None


def _git_root(cwd: Path) -> Path | None:
    current = cwd.expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _repository_identity(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    identity = (
        result.stdout.strip() if result.returncode == 0 else str((repo_root / ".git").resolve())
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _private_id(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def _nested_number(payload: dict[str, Any], *keys: str) -> float | None:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return round(ordered[index], 6)


def _task_timings(events: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
    timings: dict[tuple[str, str], dict[str, float]] = {}
    for event in events:
        key = (str(event["repository_id"]), str(event["task_id"]))
        occurred = datetime.fromisoformat(str(event["occurred_at"])).timestamp()
        row = timings.setdefault(key, {})
        name = str(event["event_name"])
        if name.endswith(".start"):
            row.setdefault("started_at", occurred)
            continue
        started_at = row.get("started_at")
        if started_at is None:
            continue
        if name.endswith((".fast.check", ".check", ".release.check")):
            row.setdefault("first_feedback_seconds", max(0.0, occurred - started_at))
        if name.endswith(".release.check"):
            row.setdefault("release_check_seconds", max(0.0, occurred - started_at))
    return timings


def _empty_report(status: str) -> dict[str, Any]:
    return {
        "schema": DOGFOOD_REPORT_SCHEMA,
        "status": status,
        "privacy": {
            "raw_prompts": False,
            "source_paths": False,
            "finding_bodies": False,
            "identifiers": "local_hmac_sha256",
        },
        "coverage": {
            "events": 0,
            "tasks": 0,
            "repositories": 0,
            "event_counts": {},
            "status_counts": {},
        },
        "feedback_loop": {
            "checks": 0,
            "release_checks": 0,
            "tasks_with_release_check": 0,
            "task_release_coverage_rate": None,
            "eligible_release_checks": 0,
            "release_eligibility_rate": None,
            "operation_seconds_p50": None,
            "operation_seconds_p95": None,
            "time_to_first_feedback_seconds_p50": None,
            "time_to_first_feedback_seconds_p95": None,
            "task_to_release_check_seconds_p50": None,
            "task_to_release_check_seconds_p95": None,
            "new_enforced_findings": 0,
            "resolved_findings": 0,
            "changed_paths": 0,
            "gate_failures": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        },
    }


def _hook_failure_reason(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return f"Quality Runner task gate is blocked: {error['message']}"
    return str(
        payload.get("next_action")
        or "Resolve the Quality Runner task blockers and rerun the release check."
    )


def _capture_notice(capture: dict[str, Any]) -> str:
    if capture.get("status") != "degraded":
        return ""
    return " Local dogfood telemetry is degraded; inspect `qr dogfood report --json`."


def _capture_system_message(capture: dict[str, Any]) -> dict[str, str]:
    notice = _capture_notice(capture).strip()
    return {"systemMessage": notice} if notice else {}
