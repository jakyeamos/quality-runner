from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_safe_directory, write_json, write_text
from quality_runner.fleet.contracts import FLEET_REPLAY_SCHEMA, digest
from quality_runner.fleet.reporting import plan_markdown, summary_markdown


def write_audit_artifacts(
    *,
    artifact_root: Path,
    inventory: dict[str, Any],
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    standard_report: dict[str, Any] | None = None,
) -> dict[str, str]:
    prepare_safe_directory(artifact_root)
    findings_dir = prepare_safe_directory(artifact_root / "findings")
    plans_dir = prepare_safe_directory(artifact_root / "plans")
    write_json(artifact_root / "inventory.json", inventory)
    write_json(artifact_root / "summary.json", summary)
    write_text(artifact_root / "summary.md", summary_markdown(summary))
    if standard_report is not None:
        write_json(artifact_root / "standard-report.json", standard_report)
    for result in results:
        repo_id = str(result["repo_id"])
        write_json(findings_dir / f"{repo_id}.json", result)
        plan = result.get("plan", {})
        write_json(plans_dir / f"{repo_id}.json", plan)
        write_text(plans_dir / f"{repo_id}.md", plan_markdown(plan))
    replay_manifest = {
        "schema": FLEET_REPLAY_SCHEMA,
        "audit_id": inventory["audit_id"],
        "as_of": inventory["as_of"],
        "inventory_hash": digest(inventory),
        "summary_hash": digest(summary),
        "finding_hashes": {str(result["repo_id"]): digest(result) for result in results},
        "provenance_hash": digest({"inventory": inventory, "summary": summary}),
    }
    write_json(artifact_root / "replay-manifest.json", replay_manifest)
    paths = {
        "inventory_json": str(artifact_root / "inventory.json"),
        "summary_json": str(artifact_root / "summary.json"),
        "summary_md": str(artifact_root / "summary.md"),
        "replay_manifest": str(artifact_root / "replay-manifest.json"),
        "findings_dir": str(findings_dir),
        "plans_dir": str(plans_dir),
    }
    if standard_report is not None:
        paths["standard_report_json"] = str(artifact_root / "standard-report.json")
    return paths
