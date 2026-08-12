from __future__ import annotations

import json
from pathlib import Path

from test_support.quality_runner_fixtures import write_js_fixture, write_python_quality_fixture


def test_inspect_repo_detects_js_quality_surfaces(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    write_js_fixture(tmp_path)

    scan = inspect_repo(tmp_path, run_id="scan-001")

    assert scan["schema"] == "quality-runner-repo-scan-v0.1"
    assert scan["package_manager"] == "pnpm"
    assert scan["languages"] == ["javascript"]
    assert scan["scripts"]["lint"] == "eslint ."
    assert scan["pre_cr_config"] == ".pre-cr.json"
    assert "state_file" not in scan


def test_inspect_repo_detects_python_quality_commands(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    write_python_quality_fixture(tmp_path)

    scan = inspect_repo(tmp_path, run_id="python-scan-001")

    assert scan["package_manager"] is None
    assert scan["languages"] == ["python"]
    commands = {command["id"]: command for command in scan["quality_commands"]}
    assert commands["formatter"]["command"] == "uv run --with ruff ruff format --check ."
    assert commands["formatter"]["source_type"] == "github_workflow"
    assert commands["lint"]["command"] == "ruff check ."
    assert commands["typecheck"]["source"] == "pyproject.toml:tool.basedpyright"
    assert commands["tests"]["source"] == "pyproject.toml:tool.pytest.ini_options"
    assert commands["dead_code"]["command"] == "uv run --with vulture vulture . --min-confidence 70"
    assert commands["build"]["command"] == "uv build"
    assert commands["runtime_smoke"]["command"] == "quality-runner doctor --json"
    assert commands["pre_pr"]["source"] == ".github/workflows"
    assert commands["pre_cr"] == {
        "id": "pre_cr",
        "command": "python3.14 scripts/run_pytest_with_lcov.py",
        "source_type": "pre_cr_config",
        "source": ".pre-cr.json:testCommand",
        "language": "python",
    }


def test_inspect_repo_does_not_infer_package_manager_from_policy_text(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Always use pnpm.\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="policy-only-001")

    assert scan["package_manager"] is None


def test_compile_standards_does_not_warn_for_unknown_package_manager(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="unknown-package-manager-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    assert scan["package_manager"] is None
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "package_manager_mismatch" not in requirement_ids


def test_compile_standards_respects_configured_package_manager_policy(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "bun@1.3.12", "scripts": {"test": "bun test"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'allowed_package_managers = ["bun"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="bun-policy-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    assert scan["package_manager"] == "bun"
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "package_manager_mismatch" not in requirement_ids


def test_inspect_repo_does_not_mark_tests_required_from_latest(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "AGENTS.md").write_text("Use the latest stable toolchain.\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="latest-001")

    assert scan["quality_contract"]["required_terms"]["tests"] is False


def test_inspect_repo_warns_on_invalid_package_json(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="invalid-package-001")

    assert scan["scripts"] == {}
    assert scan["warnings"] == [
        {
            "code": "invalid_package_json",
            "message": "package.json could not be parsed as JSON",
            "path": "package.json",
        }
    ]


def test_inspect_repo_warns_on_invalid_package_json_shape(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text("[]", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="invalid-package-shape-001")

    assert scan["scripts"] == {}
    assert scan["warnings"] == [
        {
            "code": "invalid_package_json_shape",
            "message": "package.json must contain a JSON object",
            "path": "package.json",
        }
    ]


def test_inspect_repo_detects_lockfile_languages_and_truth_policy(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "yarn@4.0.0",
                "scripts": {
                    "fmt": "prettier --check .",
                    "check-types": "tsc --noEmit",
                    "tests": "vitest run",
                    "smoke-test": "playwright test smoke",
                    "prepr": "pre-cr",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Package.swift").write_text("// swift\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/fixture\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Maintain stable planning notes after every change.\n",
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="mixed-language-001")

    assert scan["package_manager"] == "yarn"
    assert scan["languages"] == ["javascript", "swift", "go"]
    assert "state_file" not in scan["quality_contract"]["required_terms"]
    commands = {command["id"]: command for command in scan["quality_commands"]}
    assert commands["formatter"]["source"] == "package.json:scripts.fmt"
    assert commands["typecheck"]["source"] == "package.json:scripts.check-types"
    assert commands["tests"]["source"] == "package.json:scripts.tests"
    assert commands["runtime_smoke"]["source"] == "package.json:scripts.smoke-test"
    assert commands["pre_pr"]["source"] == "package.json:scripts.prepr"
    assert commands["tests"]["language"] == "javascript"


def test_inspect_repo_prefers_read_only_format_check_script(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@11.20.0",
                "scripts": {
                    "format": "prettier --write .",
                    "format:check": "prettier --check .",
                },
            }
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="format-check-preference")
    formatter = next(item for item in scan["quality_commands"] if item["id"] == "formatter")

    assert formatter["command"] == "pnpm run format:check"
    assert formatter["source"] == "package.json:scripts.format:check"
    assert "mutating_risk" not in formatter


def test_inspect_repo_detects_swift_package_test_gate(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "Package.swift").write_text("// swift-tools-version: 6.0\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="swift-package-001")

    assert {
        "id": "tests",
        "command": "swift test",
        "source_type": "swift_package",
        "source": "Package.swift",
        "language": "swift",
    } in scan["quality_commands"]


def test_locked_python_project_commands_use_offline_uv_environment(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "locked-python"',
                'version = "0.1.0"',
                "",
                "[project.optional-dependencies]",
                'dev = ["pytest", "ruff"]',
                "",
                "[tool.pytest.ini_options]",
                'testpaths = ["tests"]',
                "",
                "[tool.ruff]",
                "line-length = 100",
                "",
                "[tool.ruff.format]",
                'quote-style = "double"',
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="locked-python-001")
    commands = {command["id"]: command["command"] for command in scan["quality_commands"]}

    assert commands["formatter"] == ("uv run --offline --locked --extra dev ruff format --check .")
    assert commands["lint"] == "uv run --offline --locked --extra dev ruff check ."
    assert commands["tests"] == "uv run --offline --locked --extra dev pytest -q"


def test_inspect_repo_warns_on_invalid_pyproject_toml(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="invalid-pyproject-001")

    assert scan["quality_commands"] == []
    assert {
        "code": "invalid_pyproject_toml",
        "message": "pyproject.toml could not be parsed as TOML",
        "path": "pyproject.toml",
    } in scan["warnings"]


def test_inspect_repo_detects_yaml_pre_cr_config_without_test_command(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / ".pre-cr.yml").write_text("version: 1\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="yaml-pre-cr-001")

    assert {
        "id": "pre_cr",
        "command": "pre-cr run --workspace .",
        "source_type": "pre_cr_config",
        "source": ".pre-cr.yml",
        "language": "unknown",
    } in scan["quality_commands"]


def test_inspect_repo_detects_json_pre_cr_config_without_test_command(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / ".pre-cr.json").write_text("{}", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="json-pre-cr-default-001")

    assert {
        "id": "pre_cr",
        "command": "pre-cr run --workspace .",
        "source_type": "pre_cr_config",
        "source": ".pre-cr.json",
        "language": "unknown",
    } in scan["quality_commands"]


def test_inspect_repo_detects_invalid_json_pre_cr_config_as_default_command(
    tmp_path: Path,
) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / ".pre-cr.json").write_text("{not-json", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="json-pre-cr-invalid-001")

    assert {
        "id": "pre_cr",
        "command": "pre-cr run --workspace .",
        "source_type": "pre_cr_config",
        "source": ".pre-cr.json",
        "language": "unknown",
    } in scan["quality_commands"]


def test_inspect_repo_detects_ci_only_python_commands(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "ci-only-python"',
                'version = "0.1.0"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    workflow_root = tmp_path / ".github" / "workflows"
    workflow_root.mkdir(parents=True)
    (workflow_root / "ci.yaml").write_text(
        "\n".join(
            [
                "name: CI",
                "on:",
                "  pull_request:",
                "jobs:",
                "  quality:",
                "    steps:",
                "      - run: uv run --with pytest pytest -q",
                "      - run: uv run --with ruff ruff check .",
                "      - run: uv run --with ruff ruff format --check .",
                "      - run: uv run --with basedpyright basedpyright",
                "      - run: uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70",
                "      - run: uv build",
                "      - run: quality-runner release-smoke --json",
                "      - run: quality-runner doctor --json",
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="ci-only-python-001")

    commands = {command["id"]: command for command in scan["quality_commands"]}
    assert commands["lint"]["source_type"] == "github_workflow"
    assert commands["formatter"]["source"] == ".github/workflows"
    assert commands["typecheck"]["command"] == "uv run --with basedpyright basedpyright"
    assert commands["tests"]["command"] == "uv run --with pytest pytest -q"
    assert (
        commands["dead_code"]["command"]
        == "uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70"
    )
    assert commands["build"]["command"] == "uv build"
    assert commands["package_consumer_smoke"]["command"] == "quality-runner release-smoke --json"
    assert commands["runtime_smoke"]["command"] == "quality-runner doctor --json"
    assert commands["pre_pr"]["command"] == "github-actions pull_request quality"


def test_ci_python_commands_are_offline_and_locked_when_uv_lock_exists(
    tmp_path: Path,
) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "locked-ci"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  quality:\n    steps:\n"
        "      - run: uv run --with basedpyright basedpyright\n"
        "      - run: uv run --with vulture vulture package tests --min-confidence 70\n",
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="locked-ci-001")
    commands = {command["id"]: command["command"] for command in scan["quality_commands"]}

    assert commands["typecheck"] == "uv run --offline --locked basedpyright"
    assert commands["dead_code"] == (
        "uv run --offline --locked vulture package tests --min-confidence 70"
    )


def test_inspect_repo_detects_nested_workspaces_and_quality_aliases(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "backend"',
                'version = "0.1.0"',
                "",
                "[build-system]",
                'requires = ["hatchling"]',
                'build-backend = "hatchling.build"',
                "",
                "[tool.pytest.ini_options]",
                'pythonpath = ["."]',
                "",
                "[tool.ruff]",
                "line-length = 100",
                "",
                "[tool.mypy]",
                "strict = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "check": "ultracite check",
                    "build:ts": "tsc -b tsconfig.project.json",
                    "test": "vitest run",
                },
            }
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="nested-workspaces-001")

    assert scan["languages"] == ["javascript", "python"]
    assert scan["workspaces"] == [
        {"path": "backend", "kind": "python", "manifest": "backend/pyproject.toml"},
        {"path": "frontend", "kind": "javascript", "manifest": "frontend/package.json"},
    ]
    commands = {(command["id"], command["source"]): command for command in scan["quality_commands"]}
    assert commands[("lint", "backend/pyproject.toml:tool.ruff")] == {
        "id": "lint",
        "command": "cd backend && ruff check .",
        "source_type": "pyproject",
        "source": "backend/pyproject.toml:tool.ruff",
        "language": "python",
    }
    assert (
        commands[("typecheck", "backend/pyproject.toml:tool.mypy")]["command"]
        == "cd backend && mypy ."
    )
    assert (
        commands[("lint", "frontend/package.json:scripts.check")]["command"]
        == "cd frontend && pnpm run check"
    )
    assert (
        commands[("typecheck", "frontend/package.json:scripts.build:ts")]["command"]
        == "cd frontend && pnpm run build:ts"
    )


def test_nested_javascript_workspace_uses_its_own_lockfile_package_manager(
    tmp_path: Path,
) -> None:
    from quality_runner.discovery import inspect_repo

    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    (dashboard / "package.json").write_text(
        json.dumps({"scripts": {"build": "next build", "typecheck": "tsc --noEmit"}}),
        encoding="utf-8",
    )
    (dashboard / "package-lock.json").write_text("{}\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="nested-npm-workspace")

    commands = {(command["id"], command["source"]): command for command in scan["quality_commands"]}
    assert (
        commands[("build", "dashboard/package.json:scripts.build")]["command"]
        == "cd dashboard && " + "n" + "pm run build"
    )
    assert (
        commands[("typecheck", "dashboard/package.json:scripts.typecheck")]["command"]
        == "cd dashboard && " + "n" + "pm run typecheck"
    )


def test_nested_javascript_workspace_inherits_root_package_manager(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@11.9.0", "scripts": {}}),
        encoding="utf-8",
    )
    workspace = tmp_path / "apps" / "web"
    workspace.mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint .", "test": "vitest run"}}),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="nested-root-package-manager")
    commands = {(item["id"], item["source"]): item["command"] for item in scan["quality_commands"]}

    assert commands[("lint", "apps/web/package.json:scripts.lint")] == (
        "cd apps/web && pnpm run lint"
    )
    assert commands[("tests", "apps/web/package.json:scripts.test")] == (
        "cd apps/web && pnpm run test"
    )


def test_ci_setup_step_is_not_misclassified_as_typecheck(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  quality:\n    steps:\n"
        "      - run: python -m pip install ruff==1.0 basedpyright==1.0\n"
        "      - run: basedpyright\n",
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="ci-setup-filter")
    commands = {item["id"]: item["command"] for item in scan["quality_commands"]}

    assert commands["typecheck"] == "basedpyright"


def test_inspect_repo_discovery_prunes_excluded_trees_before_recursive_walk(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from pathlib import Path as PathClass

    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "node_modules" / "fixture" / "package.json").parent.mkdir(parents=True)
    (tmp_path / "node_modules" / "fixture" / "package.json").write_text(
        json.dumps({"scripts": {"test": "should-not-be-read"}}),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "sample" / "pyproject.toml").parent.mkdir(parents=True)
    (tmp_path / "docs" / "sample" / "pyproject.toml").write_text(
        '[project]\nname = "docs-sample"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    def fail_rglob(self: PathClass, pattern: str):  # noqa: ANN001
        raise AssertionError(f"discovery should not call Path.rglob({pattern!r})")

    monkeypatch.setattr(PathClass, "rglob", fail_rglob)

    scan = inspect_repo(tmp_path, run_id="pruned-discovery-001")

    assert scan["workspaces"] == []
    assert scan["quality_commands"][0]["source"] == "package.json:scripts.test"


def test_inspect_repo_prunes_gitignored_untracked_directories(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / ".gitignore").write_text("ignored-workspaces/\n", encoding="utf-8")
    (tmp_path / "app" / "package.json").parent.mkdir(parents=True)
    (tmp_path / "app" / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "ignored-workspaces" / "demo" / "package.json").parent.mkdir(parents=True)
    (tmp_path / "ignored-workspaces" / "demo" / "package.json").write_text(
        json.dumps({"scripts": {"test": "should-not-be-read"}}),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="gitignore-prune-001")

    assert scan["workspaces"] == [
        {"path": "app", "kind": "javascript", "manifest": "app/package.json"}
    ]


def test_inspect_repo_excludes_default_fixture_corpus_vendor_and_docs_paths(
    tmp_path: Path,
) -> None:
    from quality_runner.discovery import inspect_repo

    app = tmp_path / "app"
    app.mkdir()
    (app / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "fixtures" / "corpus" / "sample").mkdir(parents=True)
    (tmp_path / "fixtures" / "corpus" / "sample" / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "snippet").mkdir(parents=True)
    (tmp_path / "docs" / "snippet" / "pyproject.toml").write_text(
        '[project]\nname = "snippet"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "vendor" / "examples" / "go").mkdir(parents=True)
    (tmp_path / "vendor" / "examples" / "go" / "go.mod").write_text(
        "module example.com/vendored\n",
        encoding="utf-8",
    )
    claude_worktree = tmp_path / ".claude" / "worktrees" / "feature-copy"
    claude_worktree.mkdir(parents=True)
    (claude_worktree / "package.json").write_text(
        json.dumps({"scripts": {"test": "should-not-be-read"}}),
        encoding="utf-8",
    )
    codex_worktree = tmp_path / ".codex" / "worktrees" / "feature-copy"
    codex_worktree.mkdir(parents=True)
    (codex_worktree / "package.json").write_text(
        json.dumps({"scripts": {"test": "should-not-be-read"}}),
        encoding="utf-8",
    )
    for agent_dir in (".aider", ".continue", ".cursor"):
        agent_path = tmp_path / agent_dir / "scratch"
        agent_path.mkdir(parents=True)
        (agent_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "should-not-be-read"}}),
            encoding="utf-8",
        )
    terraform_dir = tmp_path / "infra" / "terraform"
    terraform_dir.mkdir(parents=True)
    (terraform_dir / "main.tf").write_text("terraform {}\n", encoding="utf-8")
    docs_terraform = tmp_path / "docs" / "terraform"
    docs_terraform.mkdir(parents=True)
    (docs_terraform / "main.tf").write_text("terraform {}\n", encoding="utf-8")
    proto_dir = tmp_path / "proto"
    proto_dir.mkdir()
    (proto_dir / "service.proto").write_text('syntax = "proto3";\n', encoding="utf-8")
    (tmp_path / "fixtures" / "corpus" / "service.proto").write_text(
        'syntax = "proto3";\n',
        encoding="utf-8",
    )
    generated_dir = tmp_path / "src" / "generated"
    generated_dir.mkdir(parents=True)
    (generated_dir / "client.py").write_text("# generated client\n", encoding="utf-8")
    fixture_generated_dir = tmp_path / "fixtures" / "corpus" / "src" / "generated"
    fixture_generated_dir.mkdir(parents=True)
    (fixture_generated_dir / "client.py").write_text(
        "# generated fixture client\n",
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="scan-exclusions-001")

    assert scan["workspaces"] == [
        {"path": "app", "kind": "javascript", "manifest": "app/package.json"}
    ]
    surface_paths = {surface["path"] for surface in scan["repo_surfaces"]}
    assert "infra/terraform" in surface_paths
    assert "proto/service.proto" in surface_paths
    assert "src/generated" in surface_paths
    assert all(not path.startswith(("docs/", "fixtures/", "vendor/")) for path in surface_paths)
    assert all(
        not path.startswith(
            (".claude/worktrees/", ".codex/worktrees/", ".aider/", ".continue/", ".cursor/")
        )
        for path in surface_paths
    )
    assert scan["generated_code"] == [{"path": "src/generated", "evidence": "generated directory"}]


def test_workflow_applies_configured_scan_exclusions(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    app = tmp_path / "app"
    app.mkdir()
    (app / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    sample = tmp_path / "samples" / "demo"
    sample.mkdir(parents=True)
    (sample / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'scan_exclusions = ["samples"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = inspect_payload(tmp_path, run_id="configured-scan-exclusions")
    scan = json.loads(Path(payload["artifact_paths"]["repo_scan_json"]).read_text())

    assert scan["scan_exclusions"] == [
        ".claude/worktrees/**",
        ".codex/worktrees/**",
        ".aider",
        ".aios",
        ".continue",
        ".cursor",
        ".planning",
        ".design-sync/previews/**",
        ".superpowers",
        ".tracker",
        "docs",
        "fixtures",
        "corpus",
        "generated-corpus",
        "generated-corpora",
        "vendor",
        "vendors",
        "vendored",
        "third_party",
        ".cache",
        ".local",
        ".mypy_cache",
        ".next",
        ".nuxt",
        ".parcel-cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svelte-kit",
        ".turbo",
        ".uv-cache",
        ".vercel",
        ".vite",
        "coverage",
        "htmlcov",
        "out",
        "playwright-report",
        "test-results",
        "artifact/**",
        "artifacts/**",
        "checkpoints/**",
        "data/**",
        "figures/**",
        "logs/**",
        "notebooks/**",
        "output/**",
        "outputs/**",
        "plots/**",
        "reports/**",
        "staging/**",
        "samples",
    ]
    assert scan["workspaces"] == [
        {"path": "app", "kind": "javascript", "manifest": "app/package.json"}
    ]
