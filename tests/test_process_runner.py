from __future__ import annotations

import json

from quality_runner.process_runner import LOCAL_COMMAND_ENV_ALLOWLIST, local_command_env


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
