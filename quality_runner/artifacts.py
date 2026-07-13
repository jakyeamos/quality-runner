from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REDACTION_REPLACEMENT = "[REDACTED]"


@dataclass(frozen=True)
class ArtifactPolicy:
    redact_patterns: tuple[str, ...] = ()
    redact_replacement: str = DEFAULT_REDACTION_REPLACEMENT
    retention_runs: int | None = None
    retention_days: int | None = None

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ArtifactPolicy:
        section = config.get("artifacts")
        if not isinstance(section, dict):
            return cls()
        patterns = section.get("redact_patterns")
        replacement = section.get("redact_replacement")
        retention_runs = section.get("retention_runs")
        retention_days = section.get("retention_days")
        return cls(
            redact_patterns=tuple(item for item in patterns if isinstance(item, str) and item)
            if isinstance(patterns, list)
            else (),
            redact_replacement=(
                replacement
                if isinstance(replacement, str) and replacement
                else DEFAULT_REDACTION_REPLACEMENT
            ),
            retention_runs=retention_runs
            if isinstance(retention_runs, int) and retention_runs > 0
            else None,
            retention_days=retention_days
            if isinstance(retention_days, int) and retention_days > 0
            else None,
        )

    @property
    def redaction_enabled(self) -> bool:
        return bool(self.redact_patterns)

    @property
    def retention_enabled(self) -> bool:
        return self.retention_runs is not None or self.retention_days is not None


def artifact_dir(repo_root: Path, run_id: str) -> Path:
    _validate_run_id(run_id)
    return repo_root.expanduser().resolve() / ".quality-runner" / "runs" / run_id


def prepare_artifact_dir(repo_root: Path, run_id: str) -> Path:
    run_dir = artifact_dir(repo_root, run_id)
    root = repo_root.expanduser().resolve()
    current = root
    for segment in (".quality-runner", "runs", run_id):
        current = current / segment
        if current.is_symlink():
            raise ValueError("artifact path component must not be a symlink")
        if current.exists():
            if not current.is_dir():
                raise ValueError("artifact path component must be a directory")
        else:
            current.mkdir()
    return run_dir


def write_json(path: Path, payload: Any) -> Path:
    _prepare_artifact_file(path)
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(_redact_content(path, content), encoding="utf-8")
    return path


def write_text(path: Path, content: str) -> Path:
    _prepare_artifact_file(path)
    path.write_text(_redact_content(path, content), encoding="utf-8")
    return path


def append_json_line(path: Path, payload: Any) -> Path:
    _prepare_artifact_file(path)
    content = json.dumps(payload, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_redact_content(path, content))
    return path


def cleanup_artifacts(
    repo_root: Path,
    *,
    config: dict[str, Any] | None = None,
    apply: bool = True,
    preserve_run_ids: set[str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    policy = ArtifactPolicy.from_config(config or _load_repo_config(root))
    runs_dir = root / ".quality-runner" / "runs"
    result: dict[str, Any] = {
        "status": "disabled" if not policy.retention_enabled else "ready",
        "retention_runs": policy.retention_runs,
        "retention_days": policy.retention_days,
        "deleted_run_ids": [],
        "would_delete_run_ids": [],
        "preserved_run_ids": sorted(preserve_run_ids or set()),
        "skipped_entries": [],
    }
    if not policy.retention_enabled:
        return result
    if not runs_dir.exists():
        result["status"] = "no-runs"
        return result
    if runs_dir.is_symlink() or not runs_dir.is_dir():
        result["status"] = "blocked"
        result["skipped_entries"] = [str(runs_dir)]
        return result

    current_time = now if now is not None else _current_time()
    preserved = preserve_run_ids or set()
    entries = [entry for entry in runs_dir.iterdir() if entry.is_dir() and not entry.is_symlink()]
    entries.sort(key=lambda entry: (entry.stat().st_mtime_ns, entry.name), reverse=True)
    retained_by_count = (
        {entry.name for entry in entries[: policy.retention_runs]}
        if policy.retention_runs is not None
        else set()
    )
    cutoff = (
        current_time - policy.retention_days * 24 * 60 * 60
        if policy.retention_days is not None
        else None
    )
    for index, entry in enumerate(entries):
        if entry.name in preserved or entry.name in retained_by_count:
            continue
        expired_by_count = policy.retention_runs is not None and index >= policy.retention_runs
        expired_by_age = cutoff is not None and entry.stat().st_mtime < cutoff
        if not expired_by_count and not expired_by_age:
            continue
        resolved_entry = entry.resolve()
        if resolved_entry.parent != runs_dir.resolve():
            result["skipped_entries"].append(str(entry))
            continue
        result["would_delete_run_ids"].append(entry.name)
        if apply:
            shutil.rmtree(entry)
            result["deleted_run_ids"].append(entry.name)
    if not apply:
        result["status"] = "dry-run"
    elif result["deleted_run_ids"]:
        result["status"] = "pruned"
    else:
        result["status"] = "retained"
    return result


def _redact_content(path: Path, content: str) -> str:
    policy = _policy_for_artifact_path(path)
    if not policy.redaction_enabled:
        return content
    redacted = content
    for pattern in policy.redact_patterns:
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue
        redacted = compiled.sub(lambda _match: policy.redact_replacement, redacted)
    return redacted


def _policy_for_artifact_path(path: Path) -> ArtifactPolicy:
    absolute = path.expanduser().absolute()
    candidate = absolute.parent
    for parent in (candidate, *candidate.parents):
        if parent.name in {"runs", "gate-runs"} and parent.parent.name == ".quality-runner":
            return ArtifactPolicy.from_config(_load_repo_config(parent.parent.parent))
    return ArtifactPolicy()


def _load_repo_config(repo_root: Path) -> dict[str, Any]:
    from quality_runner.config import load_repo_config

    return load_repo_config(repo_root)


def _current_time() -> float:
    from time import time

    return time()


def _validate_run_id(run_id: str) -> None:
    path = Path(run_id)
    separators = {"/", "\\"}

    if (
        not run_id
        or run_id in {".", ".."}
        or ":" in run_id
        or path.is_absolute()
        or any(separator in run_id for separator in separators)
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise ValueError("run_id must be a non-empty single path segment")


def _prepare_artifact_file(path: Path) -> None:
    if path.parent.is_symlink():
        raise ValueError("artifact file must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("artifact file must not be a symlink")
