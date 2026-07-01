from __future__ import annotations

import json
from pathlib import Path

MAX_CI_STATUS_BYTES = 1_000_000


def load_ci_status(
    repo_root: Path,
    ci_status_json: Path | None,
) -> tuple[list[dict[str, str | None]], list[dict[str, str]]]:
    if ci_status_json is None:
        return [], []

    root = repo_root.expanduser().resolve()
    path = ci_status_json.expanduser().resolve()
    relative_path = _display_path(root, path)
    if not _is_inside(root, path):
        return [], [
            {
                "code": "ci_status_outside_repo",
                "message": f"{relative_path} is outside the repository and was skipped",
                "path": relative_path,
            }
        ]
    if path.is_symlink():
        return [], [
            {
                "code": "skipped_symlinked_ci_status",
                "message": f"{relative_path} is a symlink and was skipped",
                "path": relative_path,
            }
        ]
    try:
        text = _read_limited(path, MAX_CI_STATUS_BYTES)
    except OSError:
        return [], [
            {
                "code": "missing_ci_status_json",
                "message": f"{relative_path} could not be read",
                "path": relative_path,
            }
        ]
    if text is None:
        return [], [
            {
                "code": "ci_status_json_too_large",
                "message": f"{relative_path} exceeds the local CI status size limit",
                "path": relative_path,
            }
        ]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [], [
            {
                "code": "invalid_ci_status_json",
                "message": f"{relative_path} could not be parsed as JSON",
                "path": relative_path,
            }
        ]
    if not isinstance(payload, dict) or not isinstance(payload.get("checks"), list):
        return [], [
            {
                "code": "invalid_ci_status_shape",
                "message": f"{relative_path} must contain a checks array",
                "path": relative_path,
            }
        ]

    checks: list[dict[str, str | None]] = []
    warnings: list[dict[str, str]] = []
    for index, item in enumerate(payload["checks"]):
        if not isinstance(item, dict):
            warnings.append(
                {
                    "code": "invalid_ci_status_check",
                    "message": f"{relative_path} checks[{index}] must be an object",
                    "path": relative_path,
                }
            )
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            warnings.append(
                {
                    "code": "invalid_ci_status_check",
                    "message": f"{relative_path} checks[{index}] must include a name",
                    "path": relative_path,
                }
            )
            continue
        checks.append(
            {
                "name": name,
                "status": _optional_string(item.get("status")),
                "conclusion": _optional_string(item.get("conclusion")),
                "url": _optional_string(item.get("url")),
                "source": relative_path,
            }
        )
    return checks, warnings


def _read_limited(path: Path, max_bytes: int) -> str | None:
    if path.stat().st_size > max_bytes:
        return None
    return path.read_text(encoding="utf-8")


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
