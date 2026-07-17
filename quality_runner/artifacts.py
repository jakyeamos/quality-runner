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
            retention_runs=(
                retention_runs if isinstance(retention_runs, int) and retention_runs > 0 else None
            ),
            retention_days=(
                retention_days if isinstance(retention_days, int) and retention_days > 0 else None
            ),
        )

    @property
    def redaction_enabled(self) -> bool:
        return bool(self.redact_patterns)

    @property
    def retention_enabled(self) -> bool:
        return self.retention_runs is not None or self.retention_days is not None


def artifact_dir(repo_root: Path, run_id: str) -> Path:
    """Return a validated artifact path without following existing symlink components."""
    validate_run_id(run_id)
    return _artifact_path(repo_root, run_id)


def prepare_artifact_dir(repo_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    return prepare_directory(repo_root, ".quality-runner", "runs", run_id)


def existing_artifact_dir(repo_root: Path, run_id: str) -> Path:
    """Return an existing run directory without following artifact symlinks."""
    validate_run_id(run_id)
    return existing_directory(repo_root, ".quality-runner", "runs", run_id)


def artifact_text_file(repo_root: Path, run_id: str, filename: str) -> Path:
    """Return a regular file from a validated existing artifact run."""
    return safe_child_file(existing_artifact_dir(repo_root, run_id), filename, require_exists=True)


def artifact_file(repo_root: Path, run_id: str, filename: str) -> Path:
    """Return a checked artifact file path for a validated run without following symlinks."""
    return safe_child_file(artifact_dir(repo_root, run_id), filename)


def artifact_run_ids(repo_root: Path) -> list[str]:
    """List only regular, validated artifact run directories."""
    try:
        runs_dir = existing_directory(repo_root, ".quality-runner", "runs")
    except FileNotFoundError:
        return []
    run_ids: list[str] = []
    for candidate in runs_dir.iterdir():
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        try:
            validate_run_id(candidate.name)
        except ValueError:
            continue
        run_ids.append(candidate.name)
    return run_ids


def prepare_directory(root: Path, *segments: str) -> Path:
    """Create a child directory one checked component at a time."""
    current = root.expanduser().resolve()
    for segment in segments:
        validate_path_segment(segment)
        current = current / segment
        if current.is_symlink():
            raise ValueError("artifact path component must not be a symlink")
        if current.exists():
            if not current.is_dir():
                raise ValueError("artifact path component must be a directory")
        else:
            current.mkdir()
    return current


def prepare_safe_directory(path: Path) -> Path:
    """Create a directory after checking every existing and new path component."""
    target = path.expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    _prepare_directory_tree(target)
    return target


def existing_directory(root: Path, *segments: str) -> Path:
    """Resolve an existing child directory without following its components."""
    current = root.expanduser().resolve()
    for segment in segments:
        validate_path_segment(segment)
        current = current / segment
        if current.is_symlink():
            raise ValueError("artifact path component must not be a symlink")
        if not current.exists():
            raise FileNotFoundError(f"artifact path component does not exist: {current}")
        if not current.is_dir():
            raise ValueError("artifact path component must be a directory")
    return current


def safe_child_file(directory: Path, filename: str, *, require_exists: bool = False) -> Path:
    """Return a non-symlink regular file contained directly in a checked directory."""
    validate_path_segment(filename)
    if directory.is_symlink():
        raise ValueError("artifact path component must not be a symlink")
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"artifact directory does not exist: {directory}")
    path = directory / filename
    if path.is_symlink():
        raise ValueError("artifact file must not be a symlink")
    if require_exists:
        if not path.exists():
            raise FileNotFoundError(f"artifact file does not exist: {path}")
        if not path.is_file():
            raise ValueError("artifact file must be a regular file")
    return path


def write_json(path: Path, payload: Any) -> Path:
    target = _prepare_artifact_file(path)
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target.write_text(_redact_content(target, content), encoding="utf-8")
    return target


def write_text(path: Path, content: str) -> Path:
    target = _prepare_artifact_file(path)
    target.write_text(_redact_content(target, content), encoding="utf-8")
    return target


def append_json_line(path: Path, payload: Any) -> Path:
    target = _prepare_artifact_file(path)
    content = json.dumps(payload, sort_keys=True) + "\n"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(_redact_content(target, content))
    return target


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


def validate_run_id(run_id: str) -> None:
    validate_path_segment(run_id, label="run_id")


def validate_path_segment(value: str, *, label: str = "path segment") -> None:
    path = Path(value)
    separators = {"/", "\\"}

    if (
        not value
        or value in {".", ".."}
        or ":" in value
        or path.is_absolute()
        or any(separator in value for separator in separators)
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{label} must be a non-empty single path segment")


def _artifact_path(repo_root: Path, run_id: str) -> Path:
    current = repo_root.expanduser().resolve()
    for segment in (".quality-runner", "runs", run_id):
        current = current / segment
        if current.is_symlink():
            raise ValueError("artifact path component must not be a symlink")
        if current.exists() and not current.is_dir():
            raise ValueError("artifact path component must be a directory")
    return current


def _validate_run_id(run_id: str) -> None:
    """Backward-compatible private alias for older internal imports."""
    validate_run_id(run_id)


def _prepare_artifact_file(path: Path) -> Path:
    target = path.expanduser()
    _prepare_directory_tree(target.parent)
    if target.is_symlink():
        raise ValueError("artifact file must not be a symlink")
    return target


def _prepare_directory_tree(path: Path) -> None:
    path = path if path.is_absolute() else Path.cwd() / path
    current = Path(path.anchor)
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for segment in parts:
        if segment in {".", ".."}:
            raise ValueError("artifact path must not contain dot path segments")
        current = current / segment
        if current.is_symlink():
            raise ValueError("artifact path component must not be a symlink")
        if current.exists():
            if not current.is_dir():
                raise ValueError("artifact path component must be a directory")
        else:
            current.mkdir()
