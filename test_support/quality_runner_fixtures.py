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


def write_python_quality_fixture(repo: Path) -> None:
    (repo / "quality_app").mkdir()
    (repo / "quality_app" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_quality_app.py").write_text(
        "def test_placeholder() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "python-quality-fixture"',
                'version = "0.1.0"',
                'requires-python = ">=3.12"',
                "",
                "[build-system]",
                'requires = ["setuptools>=68"]',
                'build-backend = "setuptools.build_meta"',
                "",
                "[tool.pytest.ini_options]",
                'pythonpath = ["."]',
                "",
                "[tool.ruff]",
                "line-length = 100",
                "",
                "[tool.basedpyright]",
                'include = ["quality_app", "tests"]',
                'typeCheckingMode = "standard"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / ".pre-cr.json").write_text(
        json.dumps(
            {
                "version": 1,
                "testCommand": "python3.14 scripts/run_pytest_with_lcov.py",
                "coveragePaths": [".pre-cr/coverage.lcov"],
                "coverageFormat": "lcov",
                "threshold": 80,
            }
        ),
        encoding="utf-8",
    )
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "\n".join(
            [
                "name: CI",
                "on:",
                "  pull_request:",
                "  push:",
                "    branches: [main]",
                "jobs:",
                "  quality:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - uses: actions/checkout@v4",
                "      - run: uv run --with pytest pytest -q",
                "      - run: uv run --with ruff ruff check .",
                "      - run: uv run --with ruff ruff format --check .",
                "      - run: uv run --with basedpyright basedpyright",
                "      - run: uv run --with vulture vulture . --min-confidence 70",
                "      - run: uv build",
                "      - run: quality-runner doctor --json",
                "",
            ]
        ),
        encoding="utf-8",
    )
