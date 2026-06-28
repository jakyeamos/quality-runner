from __future__ import annotations

from pathlib import Path
from typing import Any

STANDARDS_PACKET_SCHEMA = "quality-runner-standards-packet-v0.1"
SUPPORTED_PROFILES = {"jakyeamos"}


def compile_standards(repo_root: Path, scan: dict[str, Any], profile: str) -> dict[str, Any]:
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"unsupported standards profile: {profile}")

    return {
        "schema": STANDARDS_PACKET_SCHEMA,
        "profile": profile,
        "repo_root": str(repo_root.expanduser().resolve()),
        "sources": _sources(scan, profile),
        "requirements": _requirements(scan),
    }


def _sources(scan: dict[str, Any], profile: str) -> list[dict[str, str]]:
    sources = [{"type": "profile", "path": f"profile:{profile}"}]

    instruction_files = scan.get("agent_instruction_files")
    if isinstance(instruction_files, list):
        for path in instruction_files:
            if isinstance(path, str) and path:
                sources.append({"type": "agent_instructions", "path": path})

    truth_file = scan.get("truth_file")
    if isinstance(truth_file, str) and truth_file:
        sources.append({"type": "truth_file", "path": truth_file})

    return sources


def _requirements(scan: dict[str, Any]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = [
        {
            "id": "use_pnpm",
            "level": "hard",
            "description": "Use pnpm for JavaScript dependency management and scripts.",
        },
        {
            "id": "quality_ladder",
            "level": "hard",
            "description": "Run lint, type checking, tests, and dead-code checks before completion.",
        },
        {
            "id": "truth_file_current",
            "level": "hard",
            "description": "Maintain .tracker/PROJECT_TRUTH.md when the repo has a truth file.",
        },
        {
            "id": "audit_and_plan_only",
            "level": "hard",
            "description": "Report quality findings and remediation plans without applying changes.",
        },
    ]

    if scan.get("package_manager") not in {"pnpm", None}:
        requirements.append(
            {
                "id": "package_manager_mismatch",
                "level": "warning",
                "description": "Detected package manager does not match the jakyeamos pnpm standard.",
            }
        )

    return requirements
