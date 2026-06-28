from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_SCAN_SCHEMA = "quality-runner-repo-scan-v0.1"


def inspect_repo(repo_root: Path, run_id: str) -> dict[str, Any]:
    _validate_repo_root(repo_root)
    root = repo_root.expanduser().resolve()
    package_json = _read_package_json(root)
    scripts = _package_scripts(package_json)
    agent_instruction_files = _agent_instruction_files(root)

    return {
        "schema": REPO_SCAN_SCHEMA,
        "run_id": run_id,
        "repo_root": str(root),
        "is_git_repo": (root / ".git").exists(),
        "package_manager": _detect_package_manager(root, package_json, agent_instruction_files),
        "languages": _detect_languages(root, package_json),
        "scripts": scripts,
        "agent_instruction_files": agent_instruction_files,
        "pre_cr_config": _first_existing(
            root,
            [".pre-cr.json", ".pre-cr.yaml", ".pre-cr.yml", "pre-cr.config.json"],
        ),
        "truth_file": _first_existing(root, [".tracker/PROJECT_TRUTH.md"]),
        "quality_contract": _detect_quality_contract(root, scripts, agent_instruction_files),
        "ci_files": _ci_files(root),
    }


def _validate_repo_root(repo_root: Path) -> None:
    if not repo_root.exists():
        raise FileNotFoundError(f"repo root does not exist: {repo_root}")
    if not repo_root.is_dir():
        raise NotADirectoryError(f"repo root is not a directory: {repo_root}")


def _read_package_json(root: Path) -> dict[str, Any]:
    package_json_path = root / "package.json"
    if not package_json_path.exists():
        return {}
    try:
        payload = json.loads(package_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _package_scripts(package_json: dict[str, Any]) -> dict[str, str]:
    scripts = package_json.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {
        str(name): command
        for name, command in scripts.items()
        if isinstance(name, str) and isinstance(command, str) and command
    }


def _agent_instruction_files(root: Path) -> list[str]:
    candidates = ["AGENTS.md", "CLAUDE.md", ".cursor/rules", ".github/copilot-instructions.md"]
    return [candidate for candidate in candidates if (root / candidate).exists()]


def _detect_package_manager(
    root: Path,
    package_json: dict[str, Any],
    agent_instruction_files: list[str],
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

    for instruction_file in agent_instruction_files:
        text = _read_text(root / instruction_file).lower()
        if "pnpm" in text:
            return "pnpm"
        if "yarn" in text:
            return "yarn"
        if "npm" in text:
            return "npm"

    if package_json:
        return "npm"
    return None


def _detect_languages(root: Path, package_json: dict[str, Any]) -> list[str]:
    languages: list[str] = []
    if package_json:
        languages.append("javascript")
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        languages.append("python")
    if (root / "Package.swift").exists():
        languages.append("swift")
    if (root / "go.mod").exists():
        languages.append("go")
    return languages


def _first_existing(root: Path, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if (root / candidate).exists():
            return candidate
    return None


def _detect_quality_contract(
    root: Path,
    scripts: dict[str, str],
    agent_instruction_files: list[str],
) -> dict[str, Any]:
    instruction_text = "\n".join(
        _read_text(root / path).lower() for path in agent_instruction_files
    )
    required_terms = {
        "lint": "lint" in instruction_text or "lint" in scripts,
        "typecheck": "typecheck" in instruction_text or "typecheck" in scripts,
        "tests": "test" in instruction_text or "test" in scripts,
        "dead_code": "dead-code" in instruction_text or "dead-code" in scripts,
    }
    return {
        "declared": any(required_terms.values()),
        "required_terms": required_terms,
    }


def _ci_files(root: Path) -> list[str]:
    candidates = [
        ".github/workflows",
        ".gitlab-ci.yml",
        "circle.yml",
        ".circleci/config.yml",
        "azure-pipelines.yml",
    ]
    return [candidate for candidate in candidates if (root / candidate).exists()]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
