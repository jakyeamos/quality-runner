from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from quality_runner.discovery_inputs import (
    _package_scripts,
    _read_package_json,
    _read_pyproject,
    _read_text,
)
from quality_runner.surfaces import quality_commands_from_surfaces


def _quality_commands(
    *,
    root: Path,
    scripts: dict[str, str],
    pyproject: dict[str, Any],
    pre_cr_config: str | None,
    ci_files: list[str],
    workspaces: list[dict[str, str]],
) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = [
        *(_javascript_quality_commands(scripts, manifest_path="package.json")),
        *(_python_pyproject_quality_commands(pyproject, manifest_path="pyproject.toml")),
        *(_workspace_quality_commands(root, workspaces)),
        *(_pre_cr_quality_commands(root, pre_cr_config)),
        *(quality_commands_from_surfaces(root)),
    ]
    existing_ids = {command["id"] for command in commands}
    commands.extend(_ci_quality_commands(root=root, ci_files=ci_files, existing_ids=existing_ids))
    return commands


def _javascript_quality_commands(
    scripts: dict[str, str],
    *,
    manifest_path: str,
) -> list[dict[str, str]]:
    script_capabilities = {
        "formatter": ("format", "fmt", "prettier"),
        "lint": ("lint", "check"),
        "typecheck": ("typecheck", "type-check", "check-types", "build:ts"),
        "tests": ("test", "tests"),
        "build": ("build",),
        "dead_code": ("dead-code", "dead_code", "knip", "vulture", "unused"),
        "runtime_smoke": ("smoke", "runtime-smoke", "smoke-test"),
        "pre_pr": ("pre-pr", "prepr"),
        "pre_cr": ("pre-cr", "precr", "pre-cr:run"),
    }
    commands: list[dict[str, str]] = []
    workspace_path = _workspace_path_from_manifest(manifest_path)
    for capability_id, script_names in script_capabilities.items():
        for script_name in script_names:
            command = scripts.get(script_name)
            if command and _script_matches_capability(capability_id, script_name, command):
                commands.append(
                    _quality_command(
                        capability_id=capability_id,
                        command=_workspace_command(workspace_path, command),
                        source_type="package_script",
                        source=f"{manifest_path}:scripts.{script_name}",
                        language="javascript",
                    )
                )
                break
    return commands


def _script_matches_capability(capability_id: str, script_name: str, command: str) -> bool:
    command_lower = command.lower()
    if capability_id == "lint" and script_name == "check":
        return "lint" in command_lower or "ultracite" in command_lower
    if capability_id == "typecheck":
        return "tsc" in command_lower or "type" in command_lower
    return True


def _python_pyproject_quality_commands(
    pyproject: dict[str, Any],
    *,
    manifest_path: str,
) -> list[dict[str, str]]:
    tool = pyproject.get("tool")
    commands: list[dict[str, str]] = []
    workspace_path = _workspace_path_from_manifest(manifest_path)
    if isinstance(tool, dict):
        if isinstance(tool.get("ruff"), dict):
            commands.extend(
                [
                    _quality_command(
                        capability_id="formatter",
                        command=_workspace_command(workspace_path, "ruff format --check ."),
                        source_type="pyproject",
                        source=f"{manifest_path}:tool.ruff",
                        language="python",
                    ),
                    _quality_command(
                        capability_id="lint",
                        command=_workspace_command(workspace_path, "ruff check ."),
                        source_type="pyproject",
                        source=f"{manifest_path}:tool.ruff",
                        language="python",
                    ),
                ]
            )
        if isinstance(tool.get("basedpyright"), dict):
            commands.append(
                _quality_command(
                    capability_id="typecheck",
                    command=_workspace_command(workspace_path, "basedpyright"),
                    source_type="pyproject",
                    source=f"{manifest_path}:tool.basedpyright",
                    language="python",
                )
            )
        elif isinstance(tool.get("mypy"), dict):
            commands.append(
                _quality_command(
                    capability_id="typecheck",
                    command=_workspace_command(workspace_path, "mypy ."),
                    source_type="pyproject",
                    source=f"{manifest_path}:tool.mypy",
                    language="python",
                )
            )
        elif isinstance(tool.get("ty"), dict):
            commands.append(
                _quality_command(
                    capability_id="typecheck",
                    command=_workspace_command(workspace_path, "ty check"),
                    source_type="pyproject",
                    source=f"{manifest_path}:tool.ty",
                    language="python",
                )
            )
        pytest_section = tool.get("pytest")
        if isinstance(pytest_section, dict) and isinstance(pytest_section.get("ini_options"), dict):
            commands.append(
                _quality_command(
                    capability_id="tests",
                    command=_workspace_command(workspace_path, "pytest -q"),
                    source_type="pyproject",
                    source=f"{manifest_path}:tool.pytest.ini_options",
                    language="python",
                )
            )
    if isinstance(pyproject.get("build-system"), dict):
        commands.append(
            _quality_command(
                capability_id="build",
                command=_workspace_command(workspace_path, "uv build"),
                source_type="pyproject",
                source=f"{manifest_path}:build-system",
                language="python",
            )
        )
    return commands


def _workspace_quality_commands(
    root: Path,
    workspaces: list[dict[str, str]],
) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    for workspace in workspaces:
        manifest = workspace.get("manifest")
        kind = workspace.get("kind")
        if not isinstance(manifest, str) or not isinstance(kind, str):
            continue
        if kind == "python":
            pyproject, _ = _read_pyproject(root, manifest)
            commands.extend(_python_pyproject_quality_commands(pyproject, manifest_path=manifest))
        elif kind == "javascript":
            package_json, _ = _read_package_json(root, manifest)
            commands.extend(
                _javascript_quality_commands(
                    _package_scripts(package_json),
                    manifest_path=manifest,
                )
            )
    return commands


def _pre_cr_quality_commands(root: Path, pre_cr_config: str | None) -> list[dict[str, str]]:
    if pre_cr_config is None:
        return []
    config_path = root / pre_cr_config
    if config_path.suffix != ".json":
        return [
            _quality_command(
                capability_id="pre_cr",
                command="pre-cr run --workspace .",
                source_type="pre_cr_config",
                source=pre_cr_config,
                language="unknown",
            )
        ]
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        command = "pre-cr run --workspace ."
    else:
        test_command = payload.get("testCommand") if isinstance(payload, dict) else None
        command = (
            test_command
            if isinstance(test_command, str) and test_command
            else "pre-cr run --workspace ."
        )
    return [
        _quality_command(
            capability_id="pre_cr",
            command=command,
            source_type="pre_cr_config",
            source=f"{pre_cr_config}:testCommand"
            if command != "pre-cr run --workspace ."
            else pre_cr_config,
            language="python" if "pytest" in command or "python" in command else "unknown",
        )
    ]


def _ci_quality_commands(
    *,
    root: Path,
    ci_files: list[str],
    existing_ids: set[str],
) -> list[dict[str, str]]:
    if ".github/workflows" not in ci_files:
        return []
    workflow_root = root / ".github" / "workflows"
    if not workflow_root.exists():
        return []
    text = "\n".join(
        _read_text(path)
        for path in sorted(workflow_root.iterdir())
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )
    commands: list[dict[str, str]] = []
    ci_patterns = [
        ("lint", "ruff check", "uv run --with ruff ruff check .", "python"),
        ("formatter", "ruff format --check", "uv run --with ruff ruff format --check .", "python"),
        ("typecheck", "basedpyright", "uv run --with basedpyright basedpyright", "python"),
        ("tests", "pytest", "uv run --with pytest pytest -q", "python"),
        ("dead_code", "vulture", "uv run --with vulture vulture . --min-confidence 70", "python"),
        ("build", "uv build", "uv build", "python"),
        ("runtime_smoke", "quality-runner doctor --json", "quality-runner doctor --json", "python"),
        ("lint", "pnpm lint", "pnpm lint", "javascript"),
        ("lint", "ultracite check", "pnpm check", "javascript"),
        ("typecheck", "pnpm typecheck", "pnpm typecheck", "javascript"),
        ("typecheck", "tsc -b", "pnpm build:ts", "javascript"),
        ("tests", "pnpm test", "pnpm test", "javascript"),
        ("build", "pnpm build", "pnpm build", "javascript"),
        ("pre_cr", "prek run", "uv run prek run", "python"),
    ]
    for capability_id, needle, command, language in ci_patterns:
        if capability_id in existing_ids or needle not in text:
            continue
        commands.append(
            _quality_command(
                capability_id=capability_id,
                command=command,
                source_type="github_workflow",
                source=".github/workflows",
                language=language,
            )
        )
    if "pre_pr" not in existing_ids and re.search(r"\bpull_request\b", text):
        commands.append(
            _quality_command(
                capability_id="pre_pr",
                command="github-actions pull_request quality",
                source_type="github_workflow",
                source=".github/workflows",
                language="unknown",
            )
        )
    return commands


def _quality_command(
    *,
    capability_id: str,
    command: str,
    source_type: str,
    source: str,
    language: str,
) -> dict[str, str]:
    return {
        "id": capability_id,
        "command": command,
        "source_type": source_type,
        "source": source,
        "language": language,
    }


def _workspace_path_from_manifest(manifest_path: str) -> str:
    parent = Path(manifest_path).parent.as_posix()
    return "" if parent == "." else parent


def _workspace_command(workspace_path: str, command: str) -> str:
    if not workspace_path:
        return command
    return f"cd {workspace_path} && {command}"
