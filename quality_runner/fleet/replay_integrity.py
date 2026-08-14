from __future__ import annotations

from typing import Any

from quality_runner.fleet.contracts import FLEET_REPLAY_SCHEMA, digest


def replay_manifest_errors(
    *,
    manifest: dict[str, Any],
    inventory: dict[str, Any],
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    expected_findings = {str(finding.get("repo_id", "")): digest(finding) for finding in findings}
    checks = (
        (manifest.get("schema") == FLEET_REPLAY_SCHEMA, "manifest schema mismatch"),
        (manifest.get("audit_id") == inventory.get("audit_id"), "manifest audit_id mismatch"),
        (manifest.get("as_of") == inventory.get("as_of"), "manifest as_of mismatch"),
        (manifest.get("inventory_hash") == digest(inventory), "inventory hash mismatch"),
        (manifest.get("summary_hash") == digest(summary), "summary hash mismatch"),
        (manifest.get("finding_hashes") == expected_findings, "finding hashes mismatch"),
        (
            manifest.get("provenance_hash") == digest({"inventory": inventory, "summary": summary}),
            "provenance hash mismatch",
        ),
    )
    errors.extend(message for valid, message in checks if not valid)
    return errors
