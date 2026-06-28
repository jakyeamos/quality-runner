from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_SCAN_SCHEMA = "quality-runner-repo-scan-v0.1"


def inspect_repo(repo_root: Path, run_id: str) -> dict[str, Any]:
    root = _validated_repo_root(repo_root)
    package_json, warnings = _read_package_json(root)
    scripts = _package_scripts(package_json)
    agent_instruction_files = _agent_instruction_files(root)

    return {
        "schema": REPO_SCAN_SCHEMA,
        "run_id": run_id,
        "repo_root": str(root),
        "is_git_repo": (root / ".git").exists(),
        "package_manager": _detect_package_manager(root, package_json),
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
        "warnings": warnings,
    }


def _validated_repo_root(repo_root: Path) -> Path:
    root = repo_root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"repo root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repo root is not a directory: {root}")
    return root


def _read_package_json(root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    package_json_path = root / "package.json"
    if not package_json_path.exists():
        return {}, []
    try:
        payload = json.loads(package_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, [
            {
                "code": "invalid_package_json",
                "message": "package.json could not be parsed as JSON",
                "path": "package.json",
            }
        ]
    if not isinstance(payload, dict):
        return {}, [
            {
                "code": "invalid_package_json_shape",
                "message": "package.json must contain a JSON object",
                "path": "package.json",
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


def _has_instruction_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) is not None for term in terms)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
