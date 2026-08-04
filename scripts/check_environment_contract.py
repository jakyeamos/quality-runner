#!/usr/bin/env python3
"""Validate Quality Runner's routed environment contract.

This checker is deliberately local and deterministic.  It verifies the
repository surfaces that make the project legible to agents, but it never
executes quality commands, contacts providers, or mutates the checkout.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import tomllib
from datetime import date, timedelta
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
    "pyrightconfig.strict.json",
    "uv.lock",
    ".pre-cr.json",
    ".quality-runner.toml",
    ".gitleaks.toml",
    "change-surface-matrix.json",
    "environment-legibility.json",
    ".gitignore",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "scripts/check_environment_contract.py",
    "scripts/check_strict_baseline.py",
)
QUALITY_COMMANDS = (
    "uv run --locked pytest -q",
    "uv run --locked ruff check .",
    "uv run --locked ruff format --check .",
    "uv run --locked basedpyright",
    "uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70",
    "uv run --locked pip-audit",
    "uv build",
    "python3 scripts/check_environment_contract.py",
    "gitleaks detect --source . --no-banner --redact",
)
CI_REQUIRED_COMMANDS = (
    "uses: actions/setup-go@v7.0.0",
    "cache: false",
    "python3 scripts/check_environment_contract.py",
    "uv run --locked basedpyright",
    "uv build",
    "uv run --locked pip-audit",
    "gitleaks detect --source . --no-banner --redact",
    "go install github.com/zricethezav/gitleaks/v8@v8.30.1",
)
REQUIRED_GITIGNORE = (
    ".env",
    ".env.*",
    ".pre-cr/",
    ".quality-runner/",
    "build/",
    "dist/",
)
REQUIRED_QUALITY_GATES = {
    "security_dependency_audit": "uv run --locked pip-audit",
    "environment_contract": "python3 scripts/check_environment_contract.py",
    "security_secrets_scan": "gitleaks detect --source . --no-banner --redact",
}
MIN_HOOK_TIMEOUT_SECONDS = 360
MAX_CONTEXT_AGE = timedelta(days=35)
LEGIBILITY_SCHEMA = "quality-runner-environment-legibility/v1"
LEGIBILITY_DIMENSIONS = {
    "architecture_boundaries",
    "coding_conventions",
    "security_constraints",
    "failure_modes",
    "implementation_examples",
    "definition_of_done",
    "approval_gated_paths",
    "deployment_rollback",
    "context_routing",
    "quality_commands",
}
REVIEW_RE = re.compile(r"last_reviewed:\s*(\d{4}-\d{2}-\d{2})")
SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
}
SECRET_MARKERS = (".env", ".pem", ".key", ".p12", ".pfx", "id_rsa", "id_ed25519", "credentials")
SAFE_SECRET_NAMES = {".env.example", ".env.template"}


def _relative_links(text: str) -> list[str]:
    return [
        value
        for value in re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", text)
        if value and not value.startswith(("http://", "https://", "mailto:", "/", "#"))
    ]


def _tracked_paths(root: Path) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
            text=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def check_secret_paths(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        name = Path(path).name.lower()
        if name in SAFE_SECRET_NAMES:
            continue
        if name in SECRET_NAMES or any(marker in name for marker in SECRET_MARKERS):
            findings.append(path)
    return findings


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


def _load_toml(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        errors.append(f"invalid {label}: {error.__class__.__name__}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} must contain a table")
        return {}
    return value


def _check_context(root: Path, errors: list[str], as_of: date) -> None:
    context_root = root / ".agents" / "context"
    index_path = context_root / "README.md"
    if not index_path.is_file() or index_path.is_symlink():
        errors.append("missing .agents/context/README.md")
    else:
        try:
            index_text = index_path.read_text(encoding="utf-8")
        except OSError:
            errors.append("unable to read .agents/context/README.md")
            index_text = ""
        match = REVIEW_RE.search(index_text)
        if match is None:
            errors.append("context index is missing last_reviewed")
        else:
            try:
                reviewed = date.fromisoformat(match.group(1))
            except ValueError:
                errors.append("context index last_reviewed is not a valid date")
            else:
                age = as_of - reviewed
                if age.days < 0:
                    errors.append("context index freshness date is in the future")
                elif age > MAX_CONTEXT_AGE:
                    errors.append(f"context index is stale: {reviewed.isoformat()}")
        for link in _relative_links(index_text):
            target = (index_path.parent / link).resolve()
            if not target.is_file() or root.resolve() not in target.parents:
                errors.append(f"context link does not resolve: {link}")

    for packet in PACKETS:
        packet_path = context_root / packet
        if not packet_path.is_file():
            errors.append(f"missing context packet: {packet}")
        elif packet_path.is_symlink():
            errors.append(f"symlinked context packet: {packet}")


def _check_pyproject(root: Path, errors: list[str]) -> None:
    config = _load_toml(root / "pyproject.toml", "pyproject.toml", errors)
    tool = config.get("tool")
    if not isinstance(tool, dict):
        errors.append("pyproject.toml is missing [tool]")
        return
    checker = tool.get("basedpyright", tool.get("pyright"))
    if not isinstance(checker, dict) or checker.get("typeCheckingMode") != "standard":
        errors.append("basedpyright must remain at the certified standard repository scope")


def _check_strict_config(root: Path, errors: list[str]) -> None:
    try:
        config = json.loads((root / "pyrightconfig.strict.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid pyrightconfig.strict.json: {error.__class__.__name__}")
        return
    if not isinstance(config, dict) or config.get("typeCheckingMode") != "strict":
        errors.append("pyrightconfig.strict.json must remain the advisory strict configuration")


def _check_pre_cr(root: Path, errors: list[str]) -> None:
    pre_cr = _load_pre_cr(root, errors)
    commands = pre_cr.get("qualityCommands", [])
    if commands != list(QUALITY_COMMANDS):
        errors.append(".pre-cr.json qualityCommands must match the canonical locked ladder")
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


def _check_workflow(path: Path, label: str, errors: list[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for command in CI_REQUIRED_COMMANDS:
        if command not in text:
            errors.append(f"{label} quality workflow is missing: {command}")


def _check_quality_runner(root: Path, errors: list[str]) -> None:
    config = _load_toml(root / ".quality-runner.toml", ".quality-runner.toml", errors)
    quality_runner = config.get("quality_runner")
    gates = quality_runner.get("gates") if isinstance(quality_runner, dict) else None
    if not isinstance(gates, list):
        errors.extend(
            f"missing required Quality Runner gate: {gate_id}" for gate_id in REQUIRED_QUALITY_GATES
        )
        return
    by_id = {
        gate.get("id"): gate
        for gate in gates
        if isinstance(gate, dict) and isinstance(gate.get("id"), str)
    }
    for gate_id, command in REQUIRED_QUALITY_GATES.items():
        gate = by_id.get(gate_id)
        if gate is None:
            errors.append(f"missing required Quality Runner gate: {gate_id}")
            continue
        if (
            gate.get("command") != command
            or gate.get("required") is not True
            or gate.get("severity") != "blocker"
        ):
            errors.append(f"Quality Runner gate is not a required blocker: {gate_id}")


def _check_legibility_contract(root: Path, errors: list[str], as_of: date) -> None:
    path = root / "environment-legibility.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid environment-legibility.json: {error.__class__.__name__}")
        return
    if not isinstance(payload, dict) or payload.get("schema") != LEGIBILITY_SCHEMA:
        errors.append("environment-legibility.json has an invalid schema")
        return
    reviewed_value = payload.get("last_reviewed")
    try:
        reviewed = date.fromisoformat(str(reviewed_value))
    except ValueError:
        errors.append("environment-legibility.json last_reviewed is invalid")
    else:
        age = as_of - reviewed
        if age.days < 0:
            errors.append("environment-legibility.json last_reviewed is in the future")
        elif age > MAX_CONTEXT_AGE:
            errors.append("environment-legibility.json is stale")
    controls = payload.get("controls")
    if not isinstance(controls, list):
        errors.append("environment-legibility.json controls must be a list")
        return
    seen: set[str] = set()
    for control in controls:
        if not isinstance(control, dict):
            errors.append("environment-legibility.json contains a non-object control")
            continue
        dimension = control.get("dimension")
        if not isinstance(dimension, str) or dimension not in LEGIBILITY_DIMENSIONS:
            errors.append(f"environment-legibility.json has an invalid dimension: {dimension}")
            continue
        seen.add(dimension)
        evidence = control.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"legibility control has no evidence: {dimension}")
        else:
            for relative_path in evidence:
                if not isinstance(relative_path, str):
                    errors.append(f"legibility evidence path is not text: {dimension}")
                    continue
                target = (root / relative_path).resolve()
                if root.resolve() not in target.parents or not target.is_file():
                    errors.append(f"legibility evidence does not resolve: {relative_path}")
        validation = control.get("validation")
        if (
            not isinstance(validation, list)
            or not validation
            or not all(isinstance(command, str) and command.strip() for command in validation)
        ):
            errors.append(f"legibility control has no validation commands: {dimension}")
        validation_evidence = control.get("validation_evidence")
        if not isinstance(validation_evidence, list) or not validation_evidence:
            errors.append(f"legibility control has no validation evidence: {dimension}")
        enforcement = control.get("enforcement")
        if not isinstance(enforcement, dict) or enforcement.get("mode") not in {
            "required",
            "routed",
        }:
            errors.append(f"legibility control has no enforcement path: {dimension}")
        elif not isinstance(enforcement.get("gate"), str) or not enforcement.get("gate"):
            errors.append(f"legibility control has no enforcement gate: {dimension}")
    errors.extend(
        f"legibility control is missing: {dimension}"
        for dimension in sorted(LEGIBILITY_DIMENSIONS - seen)
    )


def _check_gitignore(root: Path, errors: list[str]) -> None:
    try:
        lines = {
            line.strip()
            for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError:
        return
    for entry in REQUIRED_GITIGNORE:
        if entry not in lines:
            errors.append(f"missing .gitignore rule: {entry}")


def validate(root: Path, as_of: date | None = None) -> list[str]:
    """Return deterministic environment-contract findings for ``root``."""

    root = root.resolve()
    errors: list[str] = []
    for relative_path in REQUIRED_FILES:
        path = root / relative_path
        if not path.is_file() or path.is_symlink():
            errors.append(f"missing required surface: {relative_path}")

    effective_as_of = as_of or date.today()
    _check_context(root, errors, effective_as_of)
    _check_pyproject(root, errors)
    _check_strict_config(root, errors)
    _check_pre_cr(root, errors)
    _check_workflow(root / ".github/workflows/ci.yml", "CI", errors)
    _check_workflow(root / ".github/workflows/release.yml", "release", errors)
    _check_quality_runner(root, errors)
    _check_legibility_contract(root, errors, effective_as_of)
    _check_gitignore(root, errors)

    tracked_paths = _tracked_paths(root)
    if tracked_paths is None:
        errors.append("git tracked-file inspection failed")
    else:
        errors.extend(
            f"secret-looking tracked path: {path}" for path in check_secret_paths(tracked_paths)
        )
    return sorted(set(errors))


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
