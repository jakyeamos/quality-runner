from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_user_git_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
