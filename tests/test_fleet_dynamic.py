from __future__ import annotations

import subprocess
from pathlib import Path

from quality_runner.fleet import dependencies, dynamic
from quality_runner.fleet.dynamic_scan import (
    quality_commands_from_scan,
    quality_commands_from_worktree,
)


def test_blocked_dynamic_result_becomes_first_class_finding() -> None:
    result = {
        "repo_id": "repo-1",
        "audit_id": "audit-1",
        "as_of": "2026-08-10T00:00:00+00:00",
        "findings": [],
        "dynamic": {
            "status": "blocked",
            "reason": "target branch is behind its configured upstream",
            "target_state": {
                "status": "stale",
                "local_head": "abc",
                "upstream": "origin/dev",
                "upstream_head": "def",
                "ahead": 0,
                "behind": 1,
                "safe_action": "fast_forward_local_target",
            },
        },
    }

    dynamic.apply_dynamic_quality_evidence(result)

    finding = result["findings"][0]
    assert finding["dimension"] == "dynamic_verification"
    assert finding["status"] == "blocked"
    assert finding["priority"] == "P0"
    assert finding["evidence"][1]["safe_action"] == "fast_forward_local_target"
    assert len(finding["provenance_hash"]) == 64


def test_unavailable_dynamic_result_becomes_unknown_finding() -> None:
    result = {
        "repo_id": "repo-1",
        "audit_id": "audit-1",
        "as_of": "2026-08-10T00:00:00+00:00",
        "findings": [],
        "dynamic": {"status": "unavailable", "reason": "runtime missing"},
    }

    dynamic.apply_dynamic_quality_evidence(result)

    finding = result["findings"][0]
    assert finding["status"] == "unknown"
    assert finding["priority"] == "P1"


def test_dynamic_quality_selection_keeps_required_security_capability() -> None:
    commands = [
        {"id": command_id, "command": command_id}
        for command_id in (
            "formatter",
            "lint",
            "typecheck",
            "tests",
            "build",
            "dead_code",
            "dependency_audit",
            "environment_contract",
            "security_secrets_scan",
        )
    ]
    selected = dynamic._quality_commands_from_scan({"scan": {"quality_commands": commands}})
    assert "security_secrets_scan" in {str(item["id"]) for item in selected}


def test_missing_dynamic_command_worktree_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    def missing_worktree(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        del command, cwd, timeout
        raise FileNotFoundError("disposable worktree disappeared")

    monkeypatch.setattr(dynamic, "run_shell_command", missing_worktree)

    result = dynamic._run_dynamic_command(
        {"id": "tests", "command": "python -m pytest"},
        tmp_path / "missing-worktree",
        30,
    )

    assert result["status"] == "unavailable"
    assert result["command_id"] == "tests"


def test_dynamic_command_timeout_has_actionable_reason(monkeypatch, tmp_path: Path) -> None:
    def timed_out(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        del cwd
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(dynamic, "run_shell_command", timed_out)

    result = dynamic._run_dynamic_command(
        {"id": "tests", "command": "python -m pytest"},
        tmp_path,
        30,
    )

    assert result["status"] == "timeout"
    assert result["reason"] == "dynamic quality command exceeded its 30-second timeout"


def test_known_failure_takes_precedence_over_incomplete_command_results() -> None:
    status, reason = dynamic._aggregate_dynamic_status(
        ["blocked", "timeout", "unavailable", "failed"]
    )

    assert status == "failed"
    assert reason == "one or more dynamic quality commands returned a failing result"


def test_policy_excluded_commands_do_not_hide_conclusive_safe_results() -> None:
    status, reason = dynamic._aggregate_dynamic_status(["not_applicable", "passed"])

    assert status == "passed"
    assert reason is None


def test_all_policy_excluded_commands_are_conclusively_not_applicable() -> None:
    status, reason = dynamic._aggregate_dynamic_status(["not_applicable"])

    assert status == "not_applicable"
    assert reason == "all discovered commands were excluded by read-only policy"


def test_dynamic_failure_retains_only_bounded_redacted_output_tail(
    monkeypatch, tmp_path: Path
) -> None:
    def failed(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        del command, cwd, timeout
        return {
            "returncode": 1,
            "stdout": "x" * 5_000,
            "stderr": f"token=super-secret\n{tmp_path}/tests/example.test.ts failed\n",
        }

    monkeypatch.setattr(dynamic, "run_shell_command", failed)

    result = dynamic._run_dynamic_command(
        {
            "id": "tests",
            "command": "pnpm run test",
            "source": "package.json:scripts.test",
        },
        tmp_path,
        30,
    )

    assert result["status"] == "failed"
    assert result["command_source"] == "package.json:scripts.test"
    assert len(result["stdout_tail"]) == 4_000
    assert "super-secret" not in result["stderr_tail"]
    assert "<repo>/tests/example.test.ts failed" in result["stderr_tail"]


def test_dynamic_policy_rejects_discovered_mutating_wrapper() -> None:
    assert not dynamic._safe_dynamic_command(
        {
            "id": "formatter",
            "command": "pnpm run format",
            "mutating_risk": "mutating",
        }
    )


def test_dynamic_gate_timeout_is_bounded_by_cli_ceiling() -> None:
    configured = {"lint": 90, "tests": 600}

    assert dynamic._command_timeout("lint", configured, 300) == 90
    assert dynamic._command_timeout("tests", configured, 300) == 300
    assert dynamic._command_timeout("typecheck", configured, 300) == 300


def test_dynamic_gate_timeouts_load_from_repository_contract(tmp_path: Path) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.gate_timeouts]\nformatter = 60\nlint = 180\ntests = 300\n",
        encoding="utf-8",
    )

    assert dynamic._configured_gate_timeouts(tmp_path) == {
        "formatter": 60,
        "lint": 180,
        "tests": 300,
    }


def test_missing_required_executable_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    def missing_linter(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        del command, cwd, timeout
        return {
            "returncode": 2,
            "stdout": "",
            "stderr": "make: golangci-lint: No such file or directory",
        }

    monkeypatch.setattr(dynamic, "run_shell_command", missing_linter)

    result = dynamic._run_dynamic_command(
        {"id": "lint", "command": "make lint"},
        tmp_path,
        30,
    )

    assert result["status"] == "unavailable"
    assert result["reason"] == (
        "required executable golangci-lint is unavailable in the bounded runtime"
    )


def test_offline_dependency_cache_miss_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    def missing_wheel(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        del command, cwd, timeout
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": (
                "Network connectivity is disabled, but the requested data wasn't found in the cache"
            ),
        }

    monkeypatch.setattr(dynamic, "run_shell_command", missing_wheel)

    result = dynamic._run_dynamic_command(
        {"id": "tests", "command": "uv run --offline --locked pytest -q"},
        tmp_path,
        30,
    )

    assert result["status"] == "unavailable"
    assert result["reason"] == (
        "a locked Python dependency is absent from the bounded offline cache"
    )


def test_local_service_smoke_precondition_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    def refused_service(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        del command, cwd, timeout
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/",
        }

    monkeypatch.setattr(dynamic, "run_shell_command", refused_service)

    result = dynamic._run_dynamic_command(
        {"id": "runtime_smoke", "command": "pnpm run smoke"}, tmp_path, 30
    )

    assert result["status"] == "unavailable"
    assert result["reason"] == (
        "the declared smoke check requires a local service that is not running"
    )


def test_dynamic_dependency_setup_is_locked_offline_and_script_free(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@11.7.0","devDependencies":{"typescript":"5.9.3"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    calls: list[tuple[str, Path, int]] = []

    def fake_runner(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        calls.append((command, cwd, timeout))
        return {"returncode": 0, "stdout": "ready", "stderr": ""}

    monkeypatch.setattr(dynamic, "run_shell_command", fake_runner)

    result = dynamic._prepare_dynamic_dependencies(worktree=tmp_path, timeout_seconds=30)

    assert result["status"] == "passed"
    assert calls == [
        (
            "COREPACK_ENABLE_PROJECT_SPEC=0 corepack pnpm --pm-on-fail=ignore install --offline --frozen-lockfile --frozen-store --ignore-scripts --reporter=append-only",
            tmp_path,
            60,
        )
    ]


def test_dynamic_dependency_setup_copies_protected_checkout_dependencies(tmp_path: Path) -> None:
    source = tmp_path / "source"
    worktree = tmp_path / "worktree"
    (source / "node_modules" / "tool").mkdir(parents=True)
    (source / "node_modules" / "tool" / "index.js").write_text("export {};\n", encoding="utf-8")
    (worktree).mkdir()
    (worktree / "package.json").write_text('{"devDependencies":{"tool":"1.0.0"}}', encoding="utf-8")

    result = dynamic._prepare_dynamic_dependencies(
        worktree=worktree,
        source=source,
        timeout_seconds=30,
    )

    assert result["status"] == "passed"
    assert result["method"] == "copied_from_protected_checkout"
    assert (worktree / "node_modules" / "tool" / "index.js").is_file()


def test_dynamic_dependency_setup_copies_nested_workspace_dependencies(tmp_path: Path) -> None:
    source = tmp_path / "source"
    worktree = tmp_path / "worktree"
    (source / "node_modules" / "root-tool").mkdir(parents=True)
    (source / "packages" / "core" / "node_modules" / "eslint").mkdir(parents=True)
    (source / "packages" / "core" / "node_modules" / "eslint" / "index.js").write_text(
        "export {};\n", encoding="utf-8"
    )
    (worktree / "packages" / "core").mkdir(parents=True)
    (worktree / "package.json").write_text(
        '{"devDependencies":{"root-tool":"1.0.0"}}', encoding="utf-8"
    )
    (worktree / "packages" / "core" / "package.json").write_text(
        '{"scripts":{"lint":"eslint ."}}', encoding="utf-8"
    )

    result = dynamic._prepare_dynamic_dependencies(
        worktree=worktree,
        source=source,
        timeout_seconds=30,
    )

    assert result["status"] == "passed"
    assert (worktree / "packages" / "core" / "node_modules" / "eslint" / "index.js").is_file()


def test_nested_workspace_dependency_links_rebase_to_root_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    worktree = tmp_path / "worktree"
    root_tool = source / "node_modules" / "root-tool"
    root_tool.mkdir(parents=True)
    (root_tool / "index.js").write_text("export {};\n", encoding="utf-8")
    nested_link = source / "client" / "node_modules" / "root-tool"
    nested_link.parent.mkdir(parents=True)
    nested_link.symlink_to(root_tool, target_is_directory=True)
    (worktree / "client").mkdir(parents=True)
    (worktree / "package.json").write_text(
        '{"devDependencies":{"root-tool":"1.0.0"}}', encoding="utf-8"
    )
    (worktree / "client" / "package.json").write_text(
        '{"devDependencies":{"root-tool":"1.0.0"}}', encoding="utf-8"
    )

    result = dynamic._prepare_dynamic_dependencies(
        worktree=worktree,
        source=source,
        timeout_seconds=30,
    )

    assert result["status"] == "passed"
    assert (worktree / "client" / "node_modules" / "root-tool").resolve() == (
        worktree / "node_modules" / "root-tool"
    )


def test_dynamic_dependency_copy_rebases_workspace_links_into_disposable_worktree(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    worktree = tmp_path / "worktree"
    package = source / "packages" / "tool"
    package.mkdir(parents=True)
    (package / "index.js").write_text("export {};\n", encoding="utf-8")
    linked = source / "node_modules" / "tool"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(package, target_is_directory=True)
    (worktree / "packages" / "tool").mkdir(parents=True)
    (worktree / "packages" / "tool" / "index.js").write_text("export {};\n", encoding="utf-8")
    (worktree / "package.json").write_text(
        '{"devDependencies":{"tool":"workspace:*"}}', encoding="utf-8"
    )

    result = dynamic._prepare_dynamic_dependencies(
        worktree=worktree,
        source=source,
        timeout_seconds=30,
    )

    assert result["status"] == "passed"
    assert (worktree / "node_modules" / "tool").resolve() == worktree / "packages" / "tool"


def test_dependency_copy_normalizes_aliased_runtime_parent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    package = source / "packages" / "tool"
    package.mkdir(parents=True)
    (package / "index.js").write_text("export {};\n", encoding="utf-8")
    linked = source / "node_modules" / "tool"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(package, target_is_directory=True)

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    alias = tmp_path / "runtime-alias"
    alias.symlink_to(runtime, target_is_directory=True)
    destination = alias / "worktree" / "node_modules"

    assert dependencies._copy_source_dependencies(source / "node_modules", destination)
    assert (destination / "tool").resolve() == runtime / "worktree" / "packages" / "tool"


def test_dependency_copy_failure_falls_back_to_locked_offline_setup(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    worktree = tmp_path / "worktree"
    (source / "node_modules").mkdir(parents=True)
    worktree.mkdir()
    (worktree / "package.json").write_text(
        '{"packageManager":"pnpm@11.7.0","devDependencies":{"tool":"1.0.0"}}',
        encoding="utf-8",
    )
    (worktree / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(dependencies, "_copy_source_dependencies", lambda *_: False)

    result = dependencies.prepare_dynamic_dependencies(
        worktree=worktree,
        source=source,
        timeout_seconds=30,
        run_command=lambda command, **_: (
            calls.append(command) or {"returncode": 0, "stdout": "", "stderr": ""}
        ),
    )

    assert result["status"] == "passed"
    assert calls == [
        "COREPACK_ENABLE_PROJECT_SPEC=0 corepack pnpm --pm-on-fail=ignore install --offline --frozen-lockfile --frozen-store --ignore-scripts --reporter=append-only"
    ]


def test_existing_dependency_tree_precedes_absolute_local_dependency_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    worktree = tmp_path / "worktree"
    (source / "node_modules" / "tool").mkdir(parents=True)
    (source / "node_modules" / "tool" / "index.js").write_text("export {};\n", encoding="utf-8")
    worktree.mkdir()
    (worktree / "package.json").write_text(
        '{"dependencies":{"tool":"file:/outside/runtime/tool"}}', encoding="utf-8"
    )

    result = dynamic._prepare_dynamic_dependencies(
        worktree=worktree,
        source=source,
        timeout_seconds=30,
    )

    assert result["status"] == "passed"
    assert result["method"] == "copied_from_protected_checkout"


def test_nested_javascript_workspace_dependencies_are_prepared(tmp_path: Path) -> None:
    source = tmp_path / "source"
    worktree = tmp_path / "worktree"
    (source / "frontend" / "node_modules" / "tool").mkdir(parents=True)
    (source / "frontend" / "node_modules" / "tool" / "index.js").write_text(
        "export {};\n", encoding="utf-8"
    )
    (worktree / "frontend").mkdir(parents=True)
    (worktree / "frontend" / "package.json").write_text(
        '{"devDependencies":{"tool":"1.0.0"}}', encoding="utf-8"
    )

    result = dynamic._prepare_dynamic_dependencies(
        worktree=worktree,
        source=source,
        timeout_seconds=30,
    )

    assert result["status"] == "passed"
    assert result["method"] == "nested_workspace_dependency_trees"
    assert result["workspaces"][0]["workspace"] == "frontend"
    assert (worktree / "frontend" / "node_modules" / "tool" / "index.js").is_file()


def test_dynamic_dependency_setup_refuses_unpinned_javascript_environment(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"node --test"},"dependencies":{"tool":"1.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    result = dynamic._prepare_dynamic_dependencies(worktree=tmp_path, timeout_seconds=30)

    assert result["status"] == "unavailable"


def test_dynamic_dependency_setup_honors_audit_timeout_ceiling(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@11.7.0","dependencies":{"tool":"1.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    observed: dict[str, int] = {}

    def successful_setup(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        del command, cwd
        observed["timeout"] = timeout
        return {"returncode": 0, "stdout": "", "stderr": ""}

    result = dependencies.prepare_dynamic_dependencies(
        worktree=tmp_path,
        timeout_seconds=600,
        run_command=successful_setup,
    )

    assert result["status"] == "passed"
    assert observed["timeout"] == 600


def test_dynamic_dependency_setup_copies_documented_sibling_runtime(tmp_path: Path) -> None:
    source = tmp_path / "source" / "companion"
    sibling = tmp_path / "source" / "jakyeamos-agent-skills"
    worktree = tmp_path / "runtime" / "repo"
    (source / "bin").mkdir(parents=True)
    sibling.mkdir(parents=True)
    (source / "bin" / "agent-config.mjs").write_text(
        'path.resolve(companionRoot, "..", "jakyeamos-agent-skills")', encoding="utf-8"
    )
    (sibling / "bin.mjs").write_text("export {};\n", encoding="utf-8")
    worktree.mkdir(parents=True)
    (worktree / "package.json").write_text("{}", encoding="utf-8")

    result = dynamic._prepare_dynamic_dependencies(
        worktree=worktree,
        source=source,
        timeout_seconds=30,
    )

    assert result["status"] == "not_required"
    assert result["documented_sibling_runtime"] == "copied"
    assert (worktree.parent / "jakyeamos-agent-skills" / "bin.mjs").is_file()


def test_documented_archival_repository_is_not_an_unknown_dynamic_result(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Generated library\n\nARCHIVAL NOTICE: retained; do not regenerate.\n",
        encoding="utf-8",
    )

    assert dynamic._documented_archival_repository(tmp_path) is True


def test_documented_deprecated_repository_is_not_dynamically_executed(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Deprecated\n\nRetained for historical provenance.\n\n"
        "## Active repository\n\nUse the active replacement instead.\n",
        encoding="utf-8",
    )

    assert dynamic._documented_deprecated_repository(tmp_path) is True


def test_dynamic_selection_includes_safe_pre_cr_aggregate() -> None:
    repository = {
        "scan": {
            "quality_commands": [{"id": "pre_cr", "command": "python3 scripts/pre_cr_coverage.py"}]
        }
    }

    assert quality_commands_from_scan(repository) == [
        {"id": "pre_cr", "command": "python3 scripts/pre_cr_coverage.py"}
    ]


def test_dynamic_selection_prefers_root_aggregate_per_capability() -> None:
    repository = {
        "scan": {
            "quality_commands": [
                {
                    "id": "lint",
                    "command": "pnpm run lint",
                    "source": "package.json:scripts.lint",
                },
                {
                    "id": "lint",
                    "command": "cd apps/mobile && pnpm run lint",
                    "source": "apps/mobile/package.json:scripts.lint",
                },
                {
                    "id": "tests",
                    "command": "cd apps/mobile && pnpm run test",
                    "source": "apps/mobile/package.json:scripts.test",
                },
                {
                    "id": "tests",
                    "command": "cd packages/api && pnpm run test",
                    "source": "packages/api/package.json:scripts.test",
                },
            ]
        }
    }

    assert quality_commands_from_scan(repository) == [
        {
            "id": "lint",
            "command": "pnpm run lint",
            "source": "package.json:scripts.lint",
        },
        {
            "id": "tests",
            "command": "cd apps/mobile && pnpm run test",
            "source": "apps/mobile/package.json:scripts.test",
        },
        {
            "id": "tests",
            "command": "cd packages/api && pnpm run test",
            "source": "packages/api/package.json:scripts.test",
        },
    ]


def test_dynamic_selection_blocks_unbounded_non_aggregated_workspace_surface() -> None:
    repository = {
        "scan": {
            "quality_commands": [
                {
                    "id": "tests",
                    "command": f"cd packages/p{index} && pnpm run test",
                    "source": f"packages/p{index}/package.json:scripts.test",
                }
                for index in range(9)
            ]
        }
    }

    try:
        quality_commands_from_scan(repository)
    except ValueError as error:
        assert "9 non-aggregated dynamic commands" in str(error)
        assert "root aggregate" in str(error)
    else:
        raise AssertionError("unbounded workspace command selection should fail closed")


def test_dynamic_command_discovery_uses_target_worktree_lock_state(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "target"\nversion = "0.1.0"\n\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
        encoding="utf-8",
    )

    commands, error = quality_commands_from_worktree(tmp_path, run_id="dynamic-target")

    assert error is None
    tests = next(item for item in commands if item["id"] == "tests")
    assert tests["command"] == "python3 -m pytest -q"


def test_read_only_docker_compose_config_is_safe_but_build_is_not() -> None:
    assert dynamic._safe_dynamic_command(
        {"id": "runtime_smoke", "command": "docker compose -f compose.yml config"}
    )
    assert not dynamic._safe_dynamic_command(
        {"id": "runtime_smoke", "command": "docker compose build"}
    )


def test_compatible_checkout_can_donate_locked_dependency_tree(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    default = tmp_path / "attached-target"
    donor = tmp_path / "prepared-checkout"
    for root in (worktree, default, donor):
        root.mkdir()
        (root / "package.json").write_text(
            '{"packageManager":"pnpm@11.9.0","devDependencies":{"vitest":"1.0.0"}}',
            encoding="utf-8",
        )
        (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (donor / "node_modules").mkdir()
    repository = {"checkouts": [{"exists": True, "path": str(donor)}]}

    assert dynamic._dependency_source(repository, worktree=worktree, default=default) == donor


def test_mismatched_lockfile_cannot_donate_dependency_tree(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    default = tmp_path / "attached-target"
    donor = tmp_path / "prepared-checkout"
    for root in (worktree, default, donor):
        root.mkdir()
        (root / "package.json").write_text(
            '{"packageManager":"pnpm@11.9.0","devDependencies":{"vitest":"1.0.0"}}',
            encoding="utf-8",
        )
    (worktree / "pnpm-lock.yaml").write_text("target\n", encoding="utf-8")
    (default / "pnpm-lock.yaml").write_text("default\n", encoding="utf-8")
    (donor / "pnpm-lock.yaml").write_text("different\n", encoding="utf-8")
    (donor / "node_modules").mkdir()
    repository = {"checkouts": [{"exists": True, "path": str(donor)}]}

    assert dynamic._dependency_source(repository, worktree=worktree, default=default) == default
