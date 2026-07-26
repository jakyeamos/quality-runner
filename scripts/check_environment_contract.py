#!/usr/bin/env python3
"""Validate Quality Runner's routed environment contract."""

from __future__ import annotations

import json
import math
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

PACKETS = (
    "architecture.md",
    "commands.md",
    "conventions.md",
    "security.md",
    "failure-modes.md",
    "examples.md",
    "done.md",
    "deployment.md",
)
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "pyproject.toml",
    "uv.lock",
    ".pre-cr.json",
    ".github/workflows/ci.yml",
)
REQUIRED_COMMANDS = (
    "uv run --locked pytest -q",
    "uv run --locked ruff check .",
    "uv run --locked ruff format --check .",
    "uv run --locked basedpyright",
    "uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70",
    "uv run --locked pip-audit",
    "uv build",
    "python3 scripts/check_environment_contract.py",
)
MIN_HOOK_TIMEOUT_SECONDS = 360
REVIEW_RE = r"last_reviewed:\s*(\d{4}-\d{2}-\d{2})"
SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
}


def _relative_links(text: str) -> list[str]:
    import re

    return [
        value
        for value in re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", text)
        if not value.startswith(("http://", "https://", "mailto:", "/"))
    ]


def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def check_secret_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if Path(path).name.lower() in SECRET_NAMES]


def _load_pre_cr(root: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads((root / ".pre-cr.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid .pre-cr.json: {error.__class__.__name__}")
        return {}
    if not isinstance(value, dict):
        errors.append(".pre-cr.json must contain an object")
        return {}
    return value


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for relative_path in REQUIRED_FILES:
        if not (root / relative_path).is_file():
            errors.append(f"missing required surface: {relative_path}")

    context_root = root / ".agents" / "context"
    index_path = context_root / "README.md"
    if not index_path.is_file():
        errors.append("missing .agents/context/README.md")
    else:
        index_text = index_path.read_text(encoding="utf-8")
        import re

        match = re.search(REVIEW_RE, index_text)
        if match is None:
            errors.append("context index is missing last_reviewed")
        else:
            try:
                reviewed = date.fromisoformat(match.group(1))
            except ValueError:
                errors.append("context index last_reviewed is not a valid date")
            else:
                if (date.today() - reviewed).days > 35:
                    errors.append(f"context index is stale: {reviewed.isoformat()}")
        for link in _relative_links(index_text):
            target = (index_path.parent / link).resolve()
            if not target.is_file() or root.resolve() not in target.parents:
                errors.append(f"context link does not resolve: {link}")
    for packet in PACKETS:
        if not (context_root / packet).is_file():
            errors.append(f"missing context packet: {packet}")

    pre_cr = _load_pre_cr(root, errors)
    commands = pre_cr.get("qualityCommands", [])
    if not isinstance(commands, list):
        errors.append(".pre-cr.json qualityCommands must be a list")
    else:
        missing = [command for command in REQUIRED_COMMANDS if command not in commands]
        errors.extend(f"missing quality command: {command}" for command in missing)
    hook_timeout = pre_cr.get("hookTimeoutSeconds")
    if (
        isinstance(hook_timeout, bool)
        or not isinstance(hook_timeout, (int, float))
        or not math.isfinite(float(hook_timeout))
        or hook_timeout < MIN_HOOK_TIMEOUT_SECONDS
    ):
        errors.append(
            ".pre-cr.json hookTimeoutSeconds must be at least "
            f"{MIN_HOOK_TIMEOUT_SECONDS} for the traced test contract"
        )
    adapters = pre_cr.get("qualityAdapters", [])
    environment_adapter = next(
        (
            adapter
            for adapter in adapters
            if isinstance(adapter, dict) and adapter.get("name") == "environment-contract"
        ),
        None,
    )
    if environment_adapter is None or environment_adapter.get("required") is not True:
        errors.append("required environment-contract quality adapter is missing")
    elif environment_adapter.get("command") != "python3 scripts/check_environment_contract.py":
        errors.append("environment-contract quality adapter command is incorrect")

    try:
        tracked_paths = _tracked_paths(root)
    except (OSError, subprocess.CalledProcessError):
        errors.append("git tracked-file inspection failed")
    else:
        errors.extend(
            f"secret-looking tracked path: {path}" for path in check_secret_paths(tracked_paths)
        )
    return errors


def main() -> int:
    errors = validate(Path(__file__).resolve().parents[1])
    if errors:
        print("Environment contract failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Environment contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
