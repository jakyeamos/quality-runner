from __future__ import annotations

import re
from typing import Any

LEAF_GATE_IDS = (
    "formatter",
    "lint",
    "typecheck",
    "tests",
    "build",
    "dead_code",
    "runtime_smoke",
)
AGGREGATE_SCRIPT_NAMES = {
    "ci",
    "check",
    "verify",
    "pre-pr",
    "prepr",
    "pre-cr",
    "precr",
    "release-preflight",
    "release",
    "release-check",
    "package-dry-run",
    "package:dry-run",
    "dry-run",
}
SCRIPT_REFERENCE_PATTERN = re.compile(r"(?:pnpm|npm|yarn|bun)(?:\s+run)?\s+([A-Za-z0-9_.:-]+)")
LEAF_ALIASES = {
    "formatter": ("format", "fmt", "prettier"),
    "lint": ("lint", "ultracite", "eslint"),
    "typecheck": ("typecheck", "type-check", "check-types", "build:ts", "tsc"),
    "tests": ("test", "tests", "pytest", "vitest"),
    "build": ("build", "compile", "uv build"),
    "dead_code": ("dead-code", "dead_code", "knip", "vulture", "unused"),
    "runtime_smoke": ("smoke", "runtime-smoke", "smoke-test", "doctor"),
}


def analyze_aggregate_coverage(
    *,
    scripts: dict[str, str],
    quality_commands: list[dict[str, str]],
) -> list[dict[str, Any]]:
    aggregate_names = sorted(
        name
        for name in scripts
        if name in AGGREGATE_SCRIPT_NAMES
        or any(token in name for token in ("ci", "verify", "preflight"))
    )
    if not aggregate_names:
        return []
    available_leaf_ids = {
        str(command.get("id")) for command in quality_commands if command.get("id") in LEAF_GATE_IDS
    }
    results: list[dict[str, Any]] = []
    for name in aggregate_names:
        command_text, opaque = _expand_script(name, scripts=scripts, stack=set(), depth=0)
        covered = sorted(_leaf_ids(command_text))
        uncovered = sorted(available_leaf_ids - set(covered))
        results.append(
            {
                "script": name,
                "command": scripts[name],
                "covered_gate_ids": covered,
                "uncovered_gate_ids": uncovered,
                "opaque": opaque,
                "reason": "script expansion was incomplete"
                if opaque
                else "script expansion completed",
            }
        )
    return results


def _expand_script(
    name: str,
    *,
    scripts: dict[str, str],
    stack: set[str],
    depth: int,
) -> tuple[str, bool]:
    if depth > 8 or name in stack:
        return "", True
    command = scripts.get(name)
    if command is None:
        return "", True
    stack.add(name)
    pieces = [command]
    opaque = False
    for referenced in SCRIPT_REFERENCE_PATTERN.findall(command):
        expanded, child_opaque = _expand_script(
            referenced,
            scripts=scripts,
            stack=stack,
            depth=depth + 1,
        )
        if not expanded:
            opaque = True
        pieces.append(expanded)
        opaque = opaque or child_opaque
    stack.remove(name)
    return "\n".join(pieces), opaque


def _leaf_ids(command: str) -> set[str]:
    normalized = command.lower()
    return {
        gate_id
        for gate_id, aliases in LEAF_ALIASES.items()
        if any(alias in normalized for alias in aliases)
    }
