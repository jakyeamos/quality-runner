from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    _prepare_artifact_file(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, content: str) -> Path:
    _prepare_artifact_file(path)
    path.write_text(content, encoding="utf-8")
    return path


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
