"""CLI and MCP adapters for retained, model-refreshable audit evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.model_audit.contracts import load_json, text
from quality_runner.model_audit.reporting import fleet_report, report
from quality_runner.model_audit.workflow import prepare, record, verify


def add_model_audit_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "model-audit", help="Prepare, verify and compare refreshable model audits"
    )
    actions = parser.add_subparsers(dest="model_audit_action", required=True)
    for action in ("prepare", "record", "verify", "report", "fleet"):
        command = actions.add_parser(action)
        command.add_argument("--json", action="store_true", help="Emit canonical JSON")
        if action == "fleet":
            command.add_argument(
                "--selection", required=True, help="Explicit local repo/run selection JSON"
            )
            continue
        command.add_argument("repo_path")
        command.add_argument("--run-id", required=True)
        if action == "prepare":
            command.add_argument("--profile", required=True, help="Saved audit profile JSON")
            command.add_argument(
                "--reviewer", required=True, help="Declared model/harness/budget JSON"
            )
            command.add_argument("--baseline-run-id", help="Prior audit lineage to retain")
            command.add_argument(
                "--reuse-inputs-from",
                help="Use this run's retained snapshot for a controlled comparison",
            )
        if action == "record":
            command.add_argument(
                "--response", required=True, help="Bound Fresh Review response in the run directory"
            )
        if action == "verify":
            command.add_argument(
                "--verification",
                required=True,
                help="Independent verification receipt in the run directory",
            )


def model_audit_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    action = text(arguments.get("action"), "action")
    if action == "fleet":
        return fleet_report(load_json(Path(text(arguments.get("selection"), "selection"))))
    repo = Path(text(arguments.get("repo_path"), "repo_path")).expanduser().resolve(strict=True)
    run_id = text(arguments.get("run_id"), "run_id")
    if action == "prepare":
        return prepare(
            repo,
            run_id,
            profile=load_json(Path(text(arguments.get("profile"), "profile"))),
            reviewer=load_json(Path(text(arguments.get("reviewer"), "reviewer"))),
            baseline_run_id=arguments.get("baseline_run_id"),
            reuse_inputs_from=arguments.get("reuse_inputs_from"),
        )
    if action == "record":
        return record(repo, run_id, Path(text(arguments.get("response"), "response")))
    if action == "verify":
        return verify(repo, run_id, Path(text(arguments.get("verification"), "verification")))
    if action == "report":
        return report(repo, run_id)
    raise ValueError("unsupported model audit action")


def model_audit_mcp_tool() -> dict[str, Any]:
    properties: dict[str, Any] = {
        key: {"type": "string"}
        for key in (
            "repo_path",
            "run_id",
            "profile",
            "reviewer",
            "baseline_run_id",
            "reuse_inputs_from",
            "response",
            "verification",
            "selection",
        )
    }
    properties["action"] = {"enum": ["prepare", "record", "verify", "report", "fleet"]}
    return {
        "name": "quality_runner_model_audit",
        "description": "Prepare local fresh-review inputs, import separate verification, and compare model audits. Never calls providers or executes fixes.",
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": ["action"],
            "additionalProperties": False,
        },
    }
