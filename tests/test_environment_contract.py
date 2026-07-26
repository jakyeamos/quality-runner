from __future__ import annotations

import json
from pathlib import Path

from scripts.check_environment_contract import check_secret_paths, validate


def test_current_repository_environment_contract_passes() -> None:
    root = Path(__file__).resolve().parents[1]

    assert validate(root) == []


def test_environment_contract_requires_quality_adapter(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in (
        "AGENTS.md",
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "pyproject.toml",
        "uv.lock",
        ".github/workflows/ci.yml",
    ):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((root / relative_path).read_text(encoding="utf-8"), encoding="utf-8")
    context = tmp_path / ".agents" / "context"
    context.mkdir(parents=True)
    for relative_path in (
        "README.md",
        "architecture.md",
        "commands.md",
        "conventions.md",
        "security.md",
        "failure-modes.md",
        "examples.md",
        "done.md",
        "deployment.md",
    ):
        (context / relative_path).write_text(
            (root / ".agents" / "context" / relative_path).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    config = json.loads((root / ".pre-cr.json").read_text(encoding="utf-8"))
    config["qualityAdapters"] = []
    (tmp_path / ".pre-cr.json").write_text(json.dumps(config), encoding="utf-8")

    errors = validate(tmp_path)

    assert "required environment-contract quality adapter is missing" in errors


def test_secret_path_helper_rejects_sensitive_names() -> None:
    assert check_secret_paths(["safe/example.txt", ".env", "keys/id_rsa"]) == [
        ".env",
        "keys/id_rsa",
    ]
