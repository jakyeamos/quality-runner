from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import REPO_SCAN_SCHEMA
from quality_runner.surfaces import detect_surfaces, quality_commands_from_surfaces

MAX_DISCOVERY_TEXT_BYTES = 1_000_000
MAX_WORKSPACES = 200


def inspect_repo(
    repo_root: Path,
    run_id: str,
    ci_checks: list[dict[str, str | None]] | None = None,
    extra_warnings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    root = _validated_repo_root(repo_root)
    package_json, warnings = _read_package_json(root)
    pyproject, pyproject_warnings = _read_pyproject(root)
    warnings.extend(pyproject_warnings)
    workspaces, workspace_warnings = _workspace_manifests(root)
    warnings.extend(workspace_warnings)
    scripts = _package_scripts(package_json)
    agent_instruction_files = _agent_instruction_files(root)
    ci_files, ci_warnings = _ci_files(root)
    warnings.extend(ci_warnings)
    if extra_warnings:
        warnings.extend(extra_warnings)
    repo_surfaces, ecosystems, generated_code = detect_surfaces(root)

    return {
        "schema": REPO_SCAN_SCHEMA,
        "run_id": run_id,
        "repo_root": str(root),
        "is_git_repo": (root / ".git").exists(),
        "package_manager": _detect_package_manager(root, package_json),
        "languages": _detect_languages(root, package_json, workspaces),
        "ecosystems": ecosystems,
        "workspaces": workspaces,
        "repo_surfaces": repo_surfaces,
        "scripts": scripts,
        "quality_commands": _quality_commands(
            root=root,
            scripts=scripts,
            pyproject=pyproject,
            pre_cr_config=_first_existing(
                root,
                [".pre-cr.json", ".pre-cr.yaml", ".pre-cr.yml", "pre-cr.config.json"],
            ),
            ci_files=ci_files,
            workspaces=workspaces,
        ),
        "generated_code": generated_code,
        "agent_instruction_files": agent_instruction_files,
        "pre_cr_config": _first_existing(
            root,
            [".pre-cr.json", ".pre-cr.yaml", ".pre-cr.yml", "pre-cr.config.json"],
        ),
        "truth_file": _first_existing(root, [".tracker/PROJECT_TRUTH.md"]),
        "quality_contract": _detect_quality_contract(root, scripts, agent_instruction_files),
        "ci_files": ci_files,
        "ci_checks": ci_checks or [],
        "warnings": warnings,
    }


def _validated_repo_root(repo_root: Path) -> Path:
    root = repo_root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"repo root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repo root is not a directory: {root}")
    return root


def _read_package_json(
    root: Path, path: str = "package.json"
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    package_json_path = root / path
    if not package_json_path.exists():
        return {}, []
    try:
        payload = json.loads(package_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, [
            {
                "code": "invalid_package_json",
                "message": f"{path} could not be parsed as JSON",
                "path": path,
            }
        ]
    if not isinstance(payload, dict):
        return {}, [
            {
                "code": "invalid_package_json_shape",
                "message": f"{path} must contain a JSON object",
                "path": path,
            }
        ]
    return payload, []


def _read_pyproject(
    root: Path, path: str = "pyproject.toml"
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    pyproject_path = root / path
    if not pyproject_path.exists():
        return {}, []
    try:
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}, [
            {
                "code": "invalid_pyproject_toml",
                "message": f"{path} could not be parsed as TOML",
                "path": path,
            }
        ]
    if not isinstance(payload, dict):
        return {}, [
            {
                "code": "invalid_pyproject_toml_shape",
                "message": f"{path} must contain a TOML table",
                "path": path,
            }
        ]
    return payload, []


def _package_scripts(package_json: dict[str, Any]) -> dict[str, str]:
    scripts = package_json.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {
        str(name): command
        for name, command in scripts.items()
        if isinstance(name, str) and isinstance(command, str) and command
    }


def _workspace_manifests(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    manifests: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    for manifest_name, kind in (
        ("pyproject.toml", "python"),
        ("package.json", "javascript"),
        ("Cargo.toml", "rust"),
        ("go.mod", "go"),
    ):
        for manifest in sorted(root.rglob(manifest_name)):
            if manifest.parent == root or not _scan_path_allowed(root, manifest):
                continue
            relative_manifest = manifest.relative_to(root).as_posix()
            if relative_manifest in seen_paths:
                continue
            seen_paths.add(relative_manifest)
            workspace_path = manifest.parent.relative_to(root).as_posix()
            manifests.append(
                {
                    "path": workspace_path,
                    "kind": kind,
                    "manifest": relative_manifest,
                }
            )

            if manifest_name == "pyproject.toml":
                _, manifest_warnings = _read_pyproject(root, relative_manifest)
                warnings.extend(manifest_warnings)
            elif manifest_name == "package.json":
                _, manifest_warnings = _read_package_json(root, relative_manifest)
                warnings.extend(manifest_warnings)

    manifests.sort(key=lambda workspace: (workspace["path"], workspace["manifest"]))
    if len(manifests) > MAX_WORKSPACES:
        manifests = manifests[:MAX_WORKSPACES]
        warnings.append(
            {
                "code": "workspace_scan_limit_reached",
                "message": f"workspace discovery reached the {MAX_WORKSPACES} workspace limit",
                "path": "workspaces",
            }
        )
    return manifests, warnings


def _agent_instruction_files(root: Path) -> list[str]:
    candidates = ["AGENTS.md", "CLAUDE.md", ".cursor/rules", ".github/copilot-instructions.md"]
    return [candidate for candidate in candidates if (root / candidate).exists()]


def _detect_package_manager(
    root: Path,
    package_json: dict[str, Any],
) -> str | None:
    package_manager = package_json.get("packageManager")
    if isinstance(package_manager, str) and package_manager:
        return package_manager.split("@", maxsplit=1)[0]

    lockfile_managers = (
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
        ("bun.lockb", "bun"),
        ("bun.lock", "bun"),
    )
    for lockfile, manager in lockfile_managers:
        if (root / lockfile).exists():
            return manager

    return None


def _detect_languages(
    root: Path,
    package_json: dict[str, Any],
    workspaces: list[dict[str, str]],
) -> list[str]:
    languages: set[str] = set()
    if package_json:
        languages.add("javascript")
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        languages.add("python")
    if (root / "Package.swift").exists():
        languages.add("swift")
    if (root / "go.mod").exists():
        languages.add("go")
    for workspace in workspaces:
        kind = workspace.get("kind")
        if kind == "javascript":
            languages.add("javascript")
        elif kind == "python":
            languages.add("python")
        elif kind in {"swift", "go", "rust"}:
            languages.add(kind)
    ordered = ["javascript", "python", "swift", "go", "rust"]
    return [language for language in ordered if language in languages]


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


def _first_existing(root: Path, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if (root / candidate).exists():
            return candidate
    return None


def _workspace_path_from_manifest(manifest_path: str) -> str:
    parent = Path(manifest_path).parent.as_posix()
    return "" if parent == "." else parent


def _workspace_command(workspace_path: str, command: str) -> str:
    if not workspace_path:
        return command
    return f"cd {workspace_path} && {command}"


def _detect_quality_contract(
    root: Path,
    scripts: dict[str, str],
    agent_instruction_files: list[str],
) -> dict[str, Any]:
    instruction_text = "\n".join(
        _read_text(root / path).lower() for path in agent_instruction_files
    )
    required_terms = {
        "lint": _has_instruction_term(instruction_text, ("lint", "linting")) or "lint" in scripts,
        "typecheck": _has_instruction_term(
            instruction_text,
            ("typecheck", "type-check", "type checking", "typechecking"),
        )
        or "typecheck" in scripts,
        "tests": _has_instruction_term(
            instruction_text,
            ("test", "tests", "testing", "test suite"),
        )
        or "test" in scripts
        or "tests" in scripts,
        "dead_code": _has_instruction_term(
            instruction_text,
            ("dead-code", "dead code", "dead-code scans", "dead code scans"),
        )
        or "dead-code" in scripts,
        "truth_file": _has_instruction_term(
            instruction_text,
            ("project_truth.md", "project truth", ".tracker/project_truth.md"),
        ),
    }
    return {
        "declared": any(required_terms.values()),
        "required_terms": required_terms,
    }


def _ci_files(root: Path) -> tuple[list[str], list[dict[str, str]]]:
    candidates = [
        ".github/workflows",
        ".gitlab-ci.yml",
        "circle.yml",
        ".circleci/config.yml",
        "azure-pipelines.yml",
    ]
    files: list[str] = []
    warnings: list[dict[str, str]] = []
    for candidate in candidates:
        path = root / candidate
        if not path.exists():
            continue
        if path.is_symlink():
            warnings.append(
                {
                    "code": "skipped_symlinked_ci_path",
                    "message": f"{candidate} is a symlink and was skipped",
                    "path": candidate,
                }
            )
            continue
        files.append(candidate)
    return files, warnings


def _has_instruction_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) is not None for term in terms)


def _read_text(path: Path) -> str:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_DISCOVERY_TEXT_BYTES:
            return ""
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _scan_path_allowed(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    blocked = {
        ".git",
        ".quality-runner",
        ".venv",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
    }
    return not path.is_symlink() and not any(part in blocked for part in relative.parts)
