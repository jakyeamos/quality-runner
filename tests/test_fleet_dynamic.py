from __future__ import annotations

from pathlib import Path

from quality_runner.fleet import dynamic


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
