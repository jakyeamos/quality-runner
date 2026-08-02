from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

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
    if not isinstance(payload, dict):
        return [], [
            {
                "code": "invalid_ci_status_shape",
                "message": f"{relative_path} must contain a checks array",
                "path": relative_path,
            }
        ]

    payload_map = cast(dict[str, Any], payload)
    if not isinstance(payload_map.get("checks"), list):
        return [], [
            {
                "code": "invalid_ci_status_shape",
                "message": f"{relative_path} must contain a checks array",
                "path": relative_path,
            }
        ]
    checks_value = cast(list[object], payload_map["checks"])
    checks: list[dict[str, str | None]] = []
    warnings: list[dict[str, str]] = []
    provenance = {
        **_provenance(payload_map),
        **_provenance(payload_map.get("provenance")),
    }
    for index, raw_item in enumerate(checks_value):
        if not isinstance(raw_item, dict):
            warnings.append(
                {
                    "code": "invalid_ci_status_check",
                    "message": f"{relative_path} checks[{index}] must be an object",
                    "path": relative_path,
                }
            )
            continue
        item = cast(dict[str, Any], raw_item)
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
        check_provenance = {
            **provenance,
            **_provenance(item.get("provenance")),
            **_provenance(item),
        }
        checks.append(
            {
                "name": name,
                "status": _optional_string(item.get("status")),
                "conclusion": _optional_string(item.get("conclusion")),
                "url": _optional_string(item.get("url")),
                "source": relative_path,
                **check_provenance,
            }
        )
    return checks, warnings


def _read_limited(path: Path, max_bytes: int) -> str | None:
    if path.stat().st_size > max_bytes:
        return None
    return path.read_text(encoding="utf-8")


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _provenance(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        return {}
    value_map = cast(dict[str, Any], value)
    result = {
        key: _optional_string(value_map.get(key))
        for key in (
            "head_sha",
            "ref",
            "captured_at",
            "artifact_digest",
            "source_url",
            "quality_runner_version",
        )
        if _optional_string(value_map.get(key)) is not None
    }
    for key in ("workflow_run_id", "run_id", "workflow_id"):
        workflow_run_id = _optional_string(value_map.get(key))
        if workflow_run_id is not None:
            result["workflow_run_id"] = workflow_run_id
            break
    return result


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
