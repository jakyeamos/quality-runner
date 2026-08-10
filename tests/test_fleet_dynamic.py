from __future__ import annotations

from pathlib import Path

from quality_runner.fleet import dependencies, dynamic


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
            "pnpm install --offline --frozen-lockfile --ignore-scripts --reporter=append-only",
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
        "pnpm install --offline --frozen-lockfile --ignore-scripts --reporter=append-only"
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


def test_dynamic_selection_includes_safe_pre_cr_aggregate() -> None:
    repository = {
        "scan": {
            "quality_commands": [{"id": "pre_cr", "command": "python3 scripts/pre_cr_coverage.py"}]
        }
    }

    assert dynamic._quality_commands_from_scan(repository) == [
        {"id": "pre_cr", "command": "python3 scripts/pre_cr_coverage.py"}
    ]


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
