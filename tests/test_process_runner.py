from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time

import pytest

from quality_runner.process_runner import (
    LOCAL_COMMAND_ENV_ALLOWLIST,
    local_command_env,
    run_shell_command,
)


def test_local_command_env_uses_allowlist_and_repo_local_caches(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("HOME", "/Users/tester")
    monkeypatch.setenv("TMPDIR", "/tmp/tester")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    monkeypatch.setenv("LC_CTYPE", "UTF-8")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-access-key")
    monkeypatch.setenv("UV_CACHE_DIR", "/inherited/uv-cache")
    monkeypatch.setenv("XDG_CACHE_HOME", "/inherited/xdg-cache")

    env = local_command_env(tmp_path)

    assert set(env) == {*LOCAL_COMMAND_ENV_ALLOWLIST, "UV_CACHE_DIR", "XDG_CACHE_HOME"}
    assert env["PATH"] == "/usr/local/bin:/usr/bin"
    assert env["UV_CACHE_DIR"] == str(tmp_path / ".quality-runner" / "cache" / "uv")
    assert env["XDG_CACHE_HOME"] == str(tmp_path / ".quality-runner" / "cache" / "xdg")
    assert "GITHUB_TOKEN" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env


def test_offline_uv_command_uses_prepared_host_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UV_CACHE_DIR", "/inherited/uv-cache")

    env = local_command_env(tmp_path, command="uv run --offline --locked pytest -q")

    assert env["UV_CACHE_DIR"] == "/inherited/uv-cache"


def test_offline_corepack_command_uses_prepared_host_cache(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    env = local_command_env(
        tmp_path,
        command=(
            "COREPACK_ENABLE_PROJECT_SPEC=0 corepack pnpm install "
            "--offline --frozen-lockfile"
        ),
    )

    assert env["COREPACK_HOME"] == str(home / ".cache" / "node" / "corepack")
    assert env["pnpm_config_cache_dir"] == str(home / "Library" / "Caches" / "pnpm")


def test_local_command_env_prefers_exact_cached_package_manager(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@11.7.0"}), encoding="utf-8"
    )
    package_manager_bin = home / "Library" / "pnpm" / ".tools" / "pnpm" / "11.7.0" / "bin"
    package_manager_bin.mkdir(parents=True)
    (package_manager_bin / "pnpm").write_text("#!/usr/bin/env node\n", encoding="utf-8")

    env = local_command_env(repo)

    assert env["PATH"] == f"{package_manager_bin}:/usr/local/bin:/usr/bin"


def test_local_command_env_shims_corepack_script_cache(tmp_path, monkeypatch) -> None:
    node_bin = tmp_path / "node-bin"
    node_bin.mkdir()
    node = node_bin / "node"
    node.write_text("#!/bin/sh\n", encoding="utf-8")
    node.chmod(0o755)
    monkeypatch.setenv("PATH", str(node_bin))
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@11.9.0"}), encoding="utf-8"
    )
    package_manager_bin = home / ".cache" / "node" / "corepack" / "v1" / "pnpm" / "11.9.0" / "bin"
    package_manager_bin.mkdir(parents=True)
    (package_manager_bin / "pnpm.mjs").write_text("console.log('11.9.0')\n", encoding="utf-8")

    env = local_command_env(repo)

    shim = repo / ".quality-runner" / "cache" / "package-managers" / "bin" / "pnpm"
    assert env["PATH"].split(":", 1)[0] == str(shim.parent)
    assert shim.read_text(encoding="utf-8").startswith("#!/bin/sh\nexec ")


def test_local_command_env_uses_cached_manager_for_unpinned_lockfile(tmp_path, monkeypatch) -> None:
    node_bin = tmp_path / "node-bin"
    node_bin.mkdir()
    node = node_bin / "node"
    node.write_text("#!/bin/sh\n", encoding="utf-8")
    node.chmod(0o755)
    monkeypatch.setenv("PATH", str(node_bin))
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    package_manager_bin = home / ".cache" / "node" / "corepack" / "v1" / "pnpm" / "11.20.0" / "bin"
    package_manager_bin.mkdir(parents=True)
    (package_manager_bin / "pnpm.cjs").write_text("console.log('11.20.0')\n", encoding="utf-8")

    env = local_command_env(repo)

    shim = repo / ".quality-runner" / "cache" / "package-managers" / "bin" / "pnpm"
    assert env["PATH"].split(":", 1)[0] == str(shim.parent)
    assert "11.20.0" in shim.read_text(encoding="utf-8")


def test_command_workspace_selects_nested_lockfile_package_manager(tmp_path, monkeypatch) -> None:
    node_bin = tmp_path / "node-bin"
    node_bin.mkdir()
    node = node_bin / "node"
    node.write_text("#!/bin/sh\n", encoding="utf-8")
    node.chmod(0o755)
    monkeypatch.setenv("PATH", str(node_bin))
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    repo = tmp_path / "repo"
    frontend = repo / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    package_manager_bin = home / ".cache" / "node" / "corepack" / "v1" / "pnpm" / "11.20.0" / "bin"
    package_manager_bin.mkdir(parents=True)
    (package_manager_bin / "pnpm.cjs").write_text("console.log('11.20.0')\n", encoding="utf-8")

    env = local_command_env(repo, command="cd frontend && pnpm run test")

    shim = frontend / ".quality-runner" / "cache" / "package-managers" / "bin" / "pnpm"
    assert env["PATH"].split(":", 1)[0] == str(shim.parent)


def test_copied_pnpm_tree_disables_implicit_dependency_install(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    repo = tmp_path / "repo"
    marker = repo / ".quality-runner" / "copied-dependencies"
    marker.parent.mkdir(parents=True)
    marker.write_text("prepared\n", encoding="utf-8")
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    env = local_command_env(repo, command="pnpm run test")

    assert env["pnpm_config_verify_deps_before_run"] == "false"


def test_timeout_kills_descendant_after_process_group_leader_exits(tmp_path) -> None:
    terminated = tmp_path / "terminated"
    survived = tmp_path / "survived"
    script = f"""
import os
import signal
import time
from pathlib import Path

child = os.fork()
if child:
    os._exit(0)

def record_termination(*_args):
    Path({str(terminated)!r}).write_text("term\\n", encoding="utf-8")
    while True:
        time.sleep(1)

signal.signal(signal.SIGTERM, record_termination)
time.sleep(1.5)
Path({str(survived)!r}).write_text("survived\\n", encoding="utf-8")
"""
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"

    with pytest.raises(subprocess.TimeoutExpired):
        run_shell_command(command, cwd=tmp_path, timeout=1)

    deadline = time.monotonic() + 0.6
    while not terminated.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.7)

    assert terminated.is_file()
    assert not survived.exists()
