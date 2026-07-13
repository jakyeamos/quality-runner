from __future__ import annotations

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
