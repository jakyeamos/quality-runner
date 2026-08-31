"""Validation of repository-local WIP records."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast


def _git_text(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def records(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Return valid WIP records and actionable validation errors."""

    validated: list[dict[str, Any]] = []
    errors: list[str] = []
    required = {
        "id",
        "state",
        "source_branch",
        "source_sha",
        "adopted_by",
        "affected_paths",
        "implemented",
        "remaining",
        "activation_default",
        "activation_condition",
        "validation",
        "next_owner",
    }
    for path in sorted((root / ".pronto" / "wip").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"{path}: invalid JSON: {error}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path}: missing fields: object")
            continue
        value = cast(dict[str, Any], value)
        missing = sorted(required - set(value))
        if missing:
            errors.append(f"{path}: missing fields: {', '.join(missing)}")
            continue
        if value["state"] != "in_progress" or value["activation_default"] != "disabled":
            errors.append(f"{path}: WIP must be in_progress and disabled by default")
            continue
        if not isinstance(value["validation"], list) or not value["validation"]:
            errors.append(f"{path}: validation evidence is required")
            continue
        source_sha = value["source_sha"]
        if not isinstance(source_sha, str) or not _git_text(
            root, "rev-parse", "--verify", f"{source_sha}^{{commit}}"
        ):
            errors.append(f"{path}: source_sha is not a resolvable Git commit")
            continue
        if not isinstance(value["id"], str) or not value["id"].startswith("wip/"):
            errors.append(f"{path}: id must use the wip/ prefix")
            continue
        validated.append(
            {"path": str(path), "id": value["id"], "source_sha": source_sha, "status": "valid"}
        )
    return validated, errors
