from __future__ import annotations

import os
import shlex
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

QUALITY_RUNNER_GIT_URL = "git+https://github.com/jakyeamos/quality-runner.git"
QUALITY_RUNNER_PROJECT = "quality-runner"


def current_source_root() -> Path | None:
    configured = os.environ.get("QUALITY_RUNNER_REPO")
    if configured:
        candidate = Path(configured).expanduser().resolve()
        return candidate if _is_quality_runner_checkout(candidate) else None

    candidate = Path(__file__).resolve().parent.parent
    return candidate if _is_quality_runner_checkout(candidate) else None


def current_runner_source() -> str:
    source_root = current_source_root()
    return str(source_root) if source_root else "installed-package"


def current_runner_command(arguments: Sequence[str] = ()) -> list[str]:
    source_root = current_source_root()
    if source_root is not None:
        return ["uv", "run", "--project", str(source_root), QUALITY_RUNNER_PROJECT, *arguments]
    return [sys.executable, "-m", "quality_runner", *arguments]


def latest_runner_command(arguments: Sequence[str] = ()) -> list[str]:
    return [
        "uvx",
        "--refresh",
        "--from",
        QUALITY_RUNNER_GIT_URL,
        QUALITY_RUNNER_PROJECT,
        *arguments,
    ]


def command_text(command: Sequence[str]) -> str:
    return shlex.join(list(command))


def _is_quality_runner_checkout(path: Path) -> bool:
    pyproject_path = path / "pyproject.toml"
    if not path.is_dir() or not pyproject_path.is_file():
        return False
    try:
        with pyproject_path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    project = document.get("project")
    return isinstance(project, dict) and project.get("name") == QUALITY_RUNNER_PROJECT
