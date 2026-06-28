from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def artifact_dir(repo_root: Path, run_id: str) -> Path:
    return repo_root.expanduser().resolve() / ".quality-runner" / "runs" / run_id


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
