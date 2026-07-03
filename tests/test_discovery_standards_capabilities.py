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
    assert scan["truth_file"] == ".tracker/PROJECT_TRUTH.md"


def test_inspect_repo_detects_python_quality_commands(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    write_python_quality_fixture(tmp_path)

    scan = inspect_repo(tmp_path, run_id="python-scan-001")

    assert scan["package_manager"] is None
    assert scan["languages"] == ["python"]
    commands = {command["id"]: command for command in scan["quality_commands"]}
    assert commands["formatter"] == {
        "id": "formatter",
        "command": "ruff format --check .",
        "source_type": "pyproject",
        "source": "pyproject.toml:tool.ruff",
        "language": "python",
    }
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
        "Maintain .tracker/PROJECT_TRUTH.md after every change.\n",
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="mixed-language-001")

    assert scan["package_manager"] == "yarn"
    assert scan["languages"] == ["javascript", "swift", "go"]
    assert scan["quality_contract"]["required_terms"]["truth_file"] is True
    commands = {command["id"]: command for command in scan["quality_commands"]}
    assert commands["formatter"]["source"] == "package.json:scripts.fmt"
    assert commands["typecheck"]["source"] == "package.json:scripts.check-types"
    assert commands["tests"]["source"] == "package.json:scripts.tests"
    assert commands["runtime_smoke"]["source"] == "package.json:scripts.smoke-test"
    assert commands["pre_pr"]["source"] == "package.json:scripts.prepr"


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
                "      - run: uv run --with vulture vulture . --min-confidence 70",
                "      - run: uv build",
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
    assert commands["dead_code"]["command"] == "uv run --with vulture vulture . --min-confidence 70"
    assert commands["build"]["command"] == "uv build"
    assert commands["runtime_smoke"]["command"] == "quality-runner doctor --json"
    assert commands["pre_pr"]["command"] == "github-actions pull_request quality"


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
        == "cd frontend && ultracite check"
    )
    assert (
        commands[("typecheck", "frontend/package.json:scripts.build:ts")]["command"]
        == "cd frontend && tsc -b tsconfig.project.json"
    )


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
        ".aios",
        ".planning",
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
        "samples",
    ]
    assert scan["workspaces"] == [
        {"path": "app", "kind": "javascript", "manifest": "app/package.json"}
    ]


def test_inspect_repo_caps_workspace_inventory_with_warning(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    for index in range(205):
        workspace = tmp_path / f"packages/package-{index:03d}"
        workspace.mkdir(parents=True)
        (workspace / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest run"}}),
            encoding="utf-8",
        )

    scan = inspect_repo(tmp_path, run_id="workspace-cap-001")

    assert len(scan["workspaces"]) == 200
    assert {
        "code": "workspace_scan_limit_reached",
        "message": "workspace discovery reached the 200 workspace limit",
        "path": "workspaces",
    } in scan["warnings"]


def test_inspect_repo_detects_mature_repo_surfaces_and_promotes_quality_commands(
    tmp_path: Path,
) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "Makefile").write_text(
        "\n".join(
            [
                "lint:",
                "\truff check .",
                "test:",
                "\tpytest -q",
                "build:",
                "\tuv build",
                "smoke:",
                "\tquality-runner doctor --json",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text("FROM python:3.14-slim\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    terraform_dir = tmp_path / "infra" / "terraform"
    terraform_dir.mkdir(parents=True)
    (terraform_dir / "main.tf").write_text("terraform {}\n", encoding="utf-8")
    migration_dir = tmp_path / "alembic" / "versions"
    migration_dir.mkdir(parents=True)
    (migration_dir / "001_create_users.py").write_text("revision = '001'\n", encoding="utf-8")
    (tmp_path / "openapi.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")
    proto_dir = tmp_path / "proto"
    proto_dir.mkdir()
    (proto_dir / "service.proto").write_text('syntax = "proto3";\n', encoding="utf-8")
    generated_dir = tmp_path / "src" / "generated"
    generated_dir.mkdir(parents=True)
    (generated_dir / "client.py").write_text("# generated by fixture\n", encoding="utf-8")
    (tmp_path / "turbo.json").write_text('{"tasks":{"lint":{},"test":{}}}\n', encoding="utf-8")
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - packages/*\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="mature-scan-001")

    surfaces = {surface["id"]: surface for surface in scan["repo_surfaces"]}
    assert {"makefile", "dockerfile", "docker_compose", "terraform", "db_migrations"}.issubset(
        surfaces
    )
    assert {"openapi_contract", "protobuf_contract", "generated_code", "turborepo"}.issubset(
        surfaces
    )
    assert "make" in scan["ecosystems"]
    assert "terraform" in scan["ecosystems"]
    assert scan["generated_code"] == [{"path": "src/generated", "evidence": "generated directory"}]
    commands = {
        (command["id"], command["source_type"]): command for command in scan["quality_commands"]
    }
    assert commands[("lint", "make_target")] == {
        "id": "lint",
        "command": "make lint",
        "source_type": "make_target",
        "source": "Makefile:lint",
        "language": "make",
    }
    assert commands[("formatter", "terraform")] == {
        "id": "formatter",
        "command": "terraform fmt -check",
        "source_type": "terraform",
        "source": "infra/terraform",
        "language": "terraform",
    }
    assert commands[("runtime_smoke", "make_target")]["command"] == "make smoke"


def test_inspect_repo_skips_symlinked_workflow_directory_and_caps_huge_reads(
    tmp_path: Path,
) -> None:
    from quality_runner.discovery import inspect_repo

    external = tmp_path.parent / f"{tmp_path.name}-external-workflows"
    external.mkdir()
    (external / "ci.yml").write_text("run: pytest -q\n", encoding="utf-8")
    workflow_parent = tmp_path / ".github"
    workflow_parent.mkdir()
    (workflow_parent / "workflows").symlink_to(external, target_is_directory=True)

    scan = inspect_repo(tmp_path, run_id="symlink-workflow-001")

    assert scan["ci_files"] == []
    assert scan["quality_commands"] == []
    assert {
        "code": "skipped_symlinked_ci_path",
        "message": ".github/workflows is a symlink and was skipped",
        "path": ".github/workflows",
    } in scan["warnings"]


def test_inspect_repo_ignores_oversized_workflow_files(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    workflow_root = tmp_path / ".github" / "workflows"
    workflow_root.mkdir(parents=True)
    (workflow_root / "ci.yml").write_text(
        "run: pytest -q\n" + ("#" * 1_000_001),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="huge-workflow-001")

    assert scan["ci_files"] == [".github/workflows"]
    assert scan["quality_commands"] == []


def test_package_json_warnings_propagate_to_standards_and_capabilities(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="invalid-package-002")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    expected_warning = {
        "code": "invalid_package_json",
        "message": "package.json could not be parsed as JSON",
        "path": "package.json",
    }
    assert expected_warning in packet["warnings"]
    assert expected_warning in capability_map["warnings"]


def test_inspect_repo_expands_home_before_validating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from quality_runner.discovery import inspect_repo

    home = tmp_path / "home"
    repo = home / "repo"
    repo.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    scan = inspect_repo(Path("~/repo"), run_id="home-001")

    assert scan["repo_root"] == str(repo.resolve())


def test_inspect_repo_rejects_missing_repo_root(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    missing_root = tmp_path / "missing"

    try:
        inspect_repo(missing_root, run_id="missing-001")
    except FileNotFoundError as error:
        assert str(error) == f"repo root does not exist: {missing_root}"
    else:
        raise AssertionError("inspect_repo accepted a missing repo root")


def test_inspect_repo_rejects_file_repo_root(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    file_root = tmp_path / "not-a-directory"
    file_root.write_text("content", encoding="utf-8")

    try:
        inspect_repo(file_root, run_id="file-001")
    except NotADirectoryError as error:
        assert str(error) == f"repo root is not a directory: {file_root}"
    else:
        raise AssertionError("inspect_repo accepted a file repo root")


def test_compile_standards_preserves_profile_and_local_provenance(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    write_js_fixture(tmp_path)
    scan = inspect_repo(tmp_path, run_id="scan-001")

    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    assert packet["schema"] == "quality-runner-standards-packet-v0.1"
    assert packet["profile"] == "default"
    sources = {source["path"] for source in packet["sources"]}
    assert "AGENTS.md" in sources
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "use_pnpm" in requirement_ids
    assert "truth_file_current" in requirement_ids


def test_compile_standards_rejects_unsupported_profiles(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="scan-001")

    try:
        compile_standards(repo_root=tmp_path, scan=scan, profile="someone-else")
    except ValueError as error:
        assert str(error) == "unsupported standards profile: someone-else"
    else:
        raise AssertionError("compile_standards accepted an unsupported profile")


def test_compile_standards_handles_malformed_package_manager() -> None:
    from quality_runner.standards import compile_standards

    packet = compile_standards(
        repo_root=Path("/tmp"),
        scan={"package_manager": []},
        profile="default",
    )

    assert {
        "code": "invalid_package_manager",
        "message": "scan package_manager must be a string or null",
        "path": "package_manager",
    } in packet["warnings"]
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "package_manager_mismatch" in requirement_ids


def test_detect_capabilities_includes_standards_warnings() -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.standards import compile_standards

    scan = {"package_manager": []}
    packet = compile_standards(repo_root=Path("/tmp"), scan=scan, profile="default")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert {
        "code": "invalid_package_manager",
        "message": "scan package_manager must be a string or null",
        "path": "package_manager",
    } in capability_map["warnings"]


def test_detect_capabilities_records_missing_expected_surfaces(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="empty-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["schema"] == "quality-runner-capability-map-v0.1"
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "lint" in missing_ids
    assert "tests" in missing_ids
    assert "truth_file" not in missing_ids


def test_detect_capabilities_accepts_python_quality_commands(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    write_python_quality_fixture(tmp_path)
    scan = inspect_repo(tmp_path, run_id="python-capabilities-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    available = {item["id"]: item for item in capability_map["available"]}
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert {
        "formatter",
        "lint",
        "typecheck",
        "tests",
        "build",
        "dead_code",
        "runtime_smoke",
        "pre_pr",
        "pre_cr",
    }.issubset(available)
    assert "truth_file" not in missing_ids
    assert available["lint"] == {
        "id": "lint",
        "type": "command",
        "source": "pyproject.toml:tool.ruff",
        "command": "ruff check .",
        "language": "python",
        "verification_state": {
            "discovery": "command-discovered",
            "execution": "not-run",
            "result": "unknown",
        },
    }


def test_detect_capabilities_records_pre_cr_script_with_stable_id(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"pre-cr": "pre-cr"}}),
        encoding="utf-8",
    )
    scan = inspect_repo(tmp_path, run_id="pre-cr-script-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    available_ids = {item["id"] for item in capability_map["available"]}
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "pre_cr" in available_ids
    assert "pre_cr" not in missing_ids
    assert "pre_pr" in missing_ids


def test_detect_capabilities_accepts_recommended_dead_code_script_name(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"audit:dead-code": "knip --production"}}),
        encoding="utf-8",
    )
    scan = inspect_repo(tmp_path, run_id="dead-code-script-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    available = {item["id"]: item for item in capability_map["available"]}
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert available["dead_code"]["source"] == "package.json:scripts.audit:dead-code"
    assert "dead_code" not in missing_ids


def test_detect_capabilities_records_pre_cr_config_with_stable_id(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / ".pre-cr.json").write_text("{}", encoding="utf-8")
    scan = inspect_repo(tmp_path, run_id="pre-cr-config-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    available_ids = {item["id"] for item in capability_map["available"]}
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "pre_cr" in available_ids
    assert "pre_cr" not in missing_ids


def test_detect_capabilities_treats_malformed_scripts_as_missing() -> None:
    from quality_runner.capabilities import detect_capabilities

    capability_map = detect_capabilities(
        scan={"schema": "quality-runner-repo-scan-v0.1", "scripts": "not-a-dict"},
        standards_packet={"profile": "default"},
    )

    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "lint" in missing_ids
    assert "tests" in missing_ids


def test_detect_capabilities_ignores_malformed_quality_commands_and_requires_truth_policy(
    tmp_path: Path,
) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "AGENTS.md").write_text(
        "Maintain project truth before completion.\n",
        encoding="utf-8",
    )
    scan = inspect_repo(tmp_path, run_id="malformed-quality-command-001")
    scan["quality_commands"] = [
        "invalid",
        {"id": "lint", "command": "ruff check .", "source": "pyproject.toml:tool.ruff"},
    ]
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    missing = {item["id"]: item for item in capability_map["missing"]}
    assert missing["lint"] == {
        "id": "lint",
        "type": "command",
        "reason": "no quality command found for lint",
        "language": "unknown",
        "required_by": "profile",
    }
    assert missing["truth_file"] == {
        "id": "truth_file",
        "type": "file",
        "reason": "no project truth file found",
        "language": "unknown",
        "required_by": "profile",
    }
