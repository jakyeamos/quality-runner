from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_user_git_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("git-config")))
