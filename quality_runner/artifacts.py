from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def artifact_dir(repo_root: Path, run_id: str) -> Path:
    _validate_run_id(run_id)
    return repo_root.expanduser().resolve() / ".quality-runner" / "runs" / run_id


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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
