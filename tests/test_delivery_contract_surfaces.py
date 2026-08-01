from __future__ import annotations

import json
from pathlib import Path

from quality_runner.cli import main
from quality_runner.mcp import call_tool


def _fixture(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "main.ts").write_text("export const value: any = {};\n", encoding="utf-8")


def test_cli_contract_prepare_and_preflight_are_public_operations(
    tmp_path: Path,
    capsys,
) -> None:
    _fixture(tmp_path)
    assert (
        main(
            [
                "plan",
                "contract",
                "prepare",
                str(tmp_path),
                "--run-id",
                "cli-contract",
                "--cache-mode",
                "disabled",
                "--json",
            ]
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    contract_path = Path(prepared["contract_path"])
    plan_path = tmp_path / "PLAN.md"
    plan_path.write_text(
        "# Native plan\n\n" + "\n".join(item["id"] for item in prepared["obligations"]),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "plan",
                "preflight",
                str(tmp_path),
                "--contract",
                str(contract_path),
                "--plan-file",
                str(plan_path),
                "--json",
            ]
        )
        == 0
    )
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["status"] == "ready"
    assert preflight["plan_scanned"] is False
    assert preflight["repository_scanned"] is False


def test_mcp_delivery_contract_tool_uses_same_contract_operations(tmp_path: Path) -> None:
    _fixture(tmp_path)
    response = call_tool(
        "quality_runner_delivery_contract",
        {
            "repo_root": str(tmp_path),
            "operation": "prepare",
            "run_id": "mcp-contract",
            "cache_mode": "disabled",
        },
    )
    payload = response["structuredContent"]
    assert payload["schema"] == "quality-runner-delivery-contract-v0.1"
    assert payload["contract_stage"] == "prepare"
