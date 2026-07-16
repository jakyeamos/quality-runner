from __future__ import annotations

import importlib.metadata
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

PACKAGE_NAME = "quality-runner"
SELF_UPDATE_SCHEMA = "quality-runner-self-update-result-v0.1"


def add_update_command(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "self-update",
        help="Update the installed Quality Runner tool from its source",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Local Quality Runner checkout to install in editable mode",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def update_command_payload(source: str | None = None) -> dict[str, Any]:
    source_path, source_error = _resolve_source(source)
    if source_error is not None:
        return {
            "schema": SELF_UPDATE_SCHEMA,
            "status": "blocked",
            "package": PACKAGE_NAME,
            "error": source_error,
        }

    command = _update_command(source_path)
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    except FileNotFoundError:
        return {
            "schema": SELF_UPDATE_SCHEMA,
            "status": "blocked",
            "package": PACKAGE_NAME,
            "command": command,
            "error": "uv is not installed or not available on PATH",
        }
    except subprocess.TimeoutExpired:
        return {
            "schema": SELF_UPDATE_SCHEMA,
            "status": "failed",
            "package": PACKAGE_NAME,
            "command": command,
            "error": "uv update timed out after 120 seconds",
        }

    payload: dict[str, Any] = {
        "schema": SELF_UPDATE_SCHEMA,
        "status": "updated" if result.returncode == 0 else "failed",
        "package": PACKAGE_NAME,
        "command": command,
        "returncode": result.returncode,
    }
    if source_path is not None:
        payload["source"] = str(source_path)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        if detail:
            payload["error"] = detail[-2000:]
    return payload


def _resolve_source(source: str | None) -> tuple[Path | None, str | None]:
    if source is None:
        return _editable_source(), None

    path = Path(source).expanduser().resolve()
    if not path.is_dir():
        return None, f"source directory does not exist: {path}"
    pyproject = path / "pyproject.toml"
    if not pyproject.is_file():
        return None, f"source directory is not a Quality Runner checkout: {path}"
    try:
        with pyproject.open("rb") as stream:
            project_name = tomllib.load(stream).get("project", {}).get("name")
    except (OSError, tomllib.TOMLDecodeError):
        return None, f"source directory has an unreadable pyproject.toml: {path}"
    if project_name != PACKAGE_NAME:
        return None, f"source directory is not a Quality Runner checkout: {path}"
    return path, None


def _editable_source() -> Path | None:
    try:
        distribution = importlib.metadata.distribution(PACKAGE_NAME)
        direct_url = distribution.read_text("direct_url.json")
    except (importlib.metadata.PackageNotFoundError, OSError):
        return None
    if not direct_url:
        return None

    try:
        metadata = json.loads(direct_url)
        if metadata.get("dir_info", {}).get("editable") is not True:
            return None
        parsed = urlparse(str(metadata.get("url", "")))
    except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if parsed.scheme != "file" or not parsed.path:
        return None
    path = Path(unquote(parsed.path)).resolve()
    return path if path.is_dir() and (path / "pyproject.toml").is_file() else None


def _update_command(source: Path | None) -> list[str]:
    if source is not None:
        return ["uv", "tool", "install", "--editable", str(source), "--force"]
    return ["uv", "tool", "upgrade", PACKAGE_NAME]
