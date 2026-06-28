from __future__ import annotations

import json
from pathlib import Path


def write_js_fixture(repo: Path) -> None:
    (repo / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "test": "vitest run",
                    "build": "vite build",
                    "dead-code": "knip",
                    "pre-cr": "pre-cr",
                }
            }
        ),
        encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text(
        "Always use pnpm. Full lint, typecheck, tests, and dead-code scans are required.\n",
        encoding="utf-8",
    )
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (repo / ".pre-cr.json").write_text("{}", encoding="utf-8")
    (repo / ".tracker").mkdir()
    (repo / ".tracker" / "PROJECT_TRUTH.md").write_text(
        "---\nprojectName: Fixture\n---\n",
        encoding="utf-8",
    )


def write_complete_js_fixture(repo: Path) -> None:
    (repo / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "format": "prettier --check .",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "test": "vitest run",
                    "build": "vite build",
                    "dead-code": "knip",
                    "smoke": "playwright test smoke",
                    "pre-pr": "pre-cr",
                    "pre-cr": "pre-cr",
                }
            }
        ),
        encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text(
        "Always use pnpm. Full lint, typecheck, tests, and dead-code scans are required.\n",
        encoding="utf-8",
    )
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (repo / ".tracker").mkdir()
    (repo / ".tracker" / "PROJECT_TRUTH.md").write_text(
        "---\nprojectName: Complete Fixture\n---\n",
        encoding="utf-8",
    )
