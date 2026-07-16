from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.aggregate_coverage import analyze_aggregate_coverage
from quality_runner.discovery_inputs import (
    _package_scripts,
    _read_package_json,
    _read_pyproject,
    _read_text,
    _workspace_manifests,
)
from quality_runner.discovery_quality import _quality_commands
from quality_runner.intent_docs import discover_intent_docs
from quality_runner.manifest import git_state_for_repo
from quality_runner.scan_exclusions import resolve_scan_exclusions
from quality_runner.schema_constants import REPO_SCAN_SCHEMA
from quality_runner.surfaces import detect_surfaces


def inspect_repo(
    repo_root: Path,
    run_id: str,
    ci_checks: list[dict[str, str | None]] | None = None,
    extra_warnings: list[dict[str, str]] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = _validated_repo_root(repo_root)
    scan_exclusions = resolve_scan_exclusions(config)
    package_json, warnings = _read_package_json(root)
    pyproject, pyproject_warnings = _read_pyproject(root)
    warnings.extend(pyproject_warnings)
    workspaces, workspace_warnings = _workspace_manifests(root, scan_exclusions)
    warnings.extend(workspace_warnings)
    scripts = _package_scripts(package_json)
    agent_instruction_files = _agent_instruction_files(root)
    ci_files, ci_warnings = _ci_files(root)
    warnings.extend(ci_warnings)
    if extra_warnings:
        warnings.extend(extra_warnings)
    repo_surfaces, ecosystems, generated_code = detect_surfaces(
        root, scan_exclusions=scan_exclusions
    )
    pre_cr_config = _first_existing(
        root,
        [".pre-cr.json", ".pre-cr.yaml", ".pre-cr.yml", "pre-cr.config.json"],
    )
    intent_docs = discover_intent_docs(root)
    git = git_state_for_repo(root)
    captured_at = datetime.now(UTC).isoformat()
    branch = git.get("branch")
    provenance = {
        **git,
        "ref": (
            branch
            if isinstance(branch, str) and branch.startswith("refs/")
            else f"refs/heads/{branch}"
            if isinstance(branch, str) and branch and branch != "HEAD"
            else None
        ),
        "quality_runner_version": __version__,
        "captured_at": captured_at,
        "worktree_mode": "in-place",
        "workflow_run_id": run_id,
    }

    quality_commands = _quality_commands(
        root=root,
        package_json=package_json,
        scripts=scripts,
        pyproject=pyproject,
        pre_cr_config=pre_cr_config,
        ci_files=ci_files,
        workspaces=workspaces,
        scan_exclusions=scan_exclusions,
    )
    return {
        "schema": REPO_SCAN_SCHEMA,
        "run_id": run_id,
        "repo_root": str(root),
        "git_provenance": provenance,
        "provenance": provenance,
        "is_git_repo": (root / ".git").exists(),
        "package_manager": _detect_package_manager(root, package_json),
        "languages": _detect_languages(root, package_json, workspaces),
        "ecosystems": ecosystems,
        "workspaces": workspaces,
        "scan_exclusions": scan_exclusions,
        "repo_surfaces": repo_surfaces,
        "scripts": scripts,
        "quality_commands": quality_commands,
        "aggregate_coverage": analyze_aggregate_coverage(
            scripts=scripts,
            quality_commands=quality_commands,
        ),
        "generated_code": generated_code,
        "intent_docs": intent_docs,
        "agent_instruction_files": agent_instruction_files,
        "pre_cr_config": pre_cr_config,
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
    if (root / "Cargo.toml").exists():
        languages.add("rust")
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
        or "dead-code" in scripts
        or "audit:dead-code" in scripts,
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
