from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def write_text(path: Path, content: str) -> Path:
    target = _prepare_artifact_file(path)
    target.write_text(content, encoding="utf-8")
    return target


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
