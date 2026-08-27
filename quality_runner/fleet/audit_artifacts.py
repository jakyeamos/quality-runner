from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import prepare_safe_directory, write_json, write_text
from quality_runner.fleet.contracts import (
    FLEET_FINDING_SCHEMA,
    FLEET_REPLAY_SCHEMA,
    FLEET_REPORT_SCHEMA,
    canonical_json,
    digest,
    public_projection,
)
from quality_runner.fleet.replay_integrity import replay_manifest_errors
from quality_runner.fleet.reporting import plan_markdown, report_markdown, summary_markdown
from quality_runner.fleet.summary import build_fleet_summary

DEFAULT_FLEET_ROOT = Path("~/.quality-runner/fleet-audit")


def fleet_show_payload(
    *, repo_id: str, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = resolve_artifact_root(output_dir, audit_id)
    path = artifact_root / "findings" / f"{repo_id}.json"
    payload = read_json(path)
    return {
        "schema": FLEET_FINDING_SCHEMA,
        "status": "found",
        "audit_id": artifact_root.name,
        "repo_id": repo_id,
        "finding": payload,
        "plan": payload.get("plan"),
        "private": True,
    }


def fleet_replay_payload(
    *, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = resolve_artifact_root(output_dir, audit_id)
    inventory = read_json(artifact_root / "inventory.json")
    summary = read_json(artifact_root / "summary.json")
    manifest = read_json(artifact_root / "replay-manifest.json")
    findings_root = artifact_root / "findings"
    results = [read_json(path) for path in sorted(findings_root.glob("*.json"))]
    rebuilt = build_fleet_summary(
        audit_id=str(inventory["audit_id"]),
        as_of=str(inventory["as_of"]),
        repositories=results,
        dynamic=bool(inventory.get("dynamic_policy", {}).get("enabled", False)),
        changed_only=bool(inventory.get("dynamic_policy", {}).get("changed_only", True)),
        standard=inventory.get("standard"),
        population_coverage=cast(dict[str, Any], inventory.get("population_coverage", {})),
    )
    manifest_errors = replay_manifest_errors(
        manifest=manifest, inventory=inventory, summary=summary, findings=results
    )
    deterministic = canonical_json(rebuilt) == canonical_json(summary) and not manifest_errors
    return {
        "schema": FLEET_REPLAY_SCHEMA,
        "status": "passed" if deterministic else "failed",
        "audit_id": inventory.get("audit_id"),
        "deterministic": deterministic,
        "manifest_valid": not manifest_errors,
        "manifest_errors": manifest_errors,
        "source_summary_hash": digest(summary),
        "replayed_summary_hash": digest(rebuilt),
        "repository_count": len(results),
        "artifact_root": str(artifact_root),
        "implementation_allowed": False,
    }


def fleet_report_payload(
    *, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    artifact_root = resolve_artifact_root(output_dir, audit_id)
    summary = read_json(artifact_root / "summary.json")
    projection = public_projection(summary)
    report = {
        "schema": FLEET_REPORT_SCHEMA,
        "status": "review_required",
        "audit_id": summary.get("audit_id"),
        "as_of": summary.get("as_of"),
        "summary": projection,
        "methodology": summary.get("methodology"),
        "privacy": projection.get("privacy"),
        "publication": {"manual_review_required": True, "published": False},
    }
    standard = summary.get("standard")
    if isinstance(standard, str) and standard:
        standard_report_path = artifact_root / "standard-report.json"
        if standard_report_path.is_file():
            report["standard"] = standard
            report["standard_report"] = read_json(standard_report_path)
            report["publication"]["canonical_maturity_feed"] = "not_applicable"
    paths = {
        "report_json": str(write_json(artifact_root / "report.json", report)),
        "report_md": str(write_text(artifact_root / "report.md", report_markdown(report))),
    }
    return {**report, "artifact_root": str(artifact_root), "artifact_paths": paths}


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


def artifact_root(output_dir: Path | None, audit_id: str, *, local: bool = False) -> Path:
    if output_dir is not None:
        base = output_dir.expanduser().resolve()
        return base if base.name == audit_id else base / audit_id
    base = DEFAULT_FLEET_ROOT.expanduser().resolve()
    return base / (f"local/{audit_id}" if local else audit_id)


def resolve_artifact_root(output_dir: Path | None, audit_id: str | None) -> Path:
    if output_dir is not None:
        candidate = output_dir.expanduser().resolve()
        if (candidate / "inventory.json").is_file():
            return candidate
        if audit_id:
            return candidate / audit_id
        return _latest_audit(candidate)
    base = DEFAULT_FLEET_ROOT.expanduser().resolve()
    if audit_id:
        direct = base / audit_id
        if direct.is_dir():
            return direct
        local = base / "local" / audit_id
        if local.is_dir():
            return local
    return _latest_audit(base)


def _latest_audit(root: Path) -> Path:
    candidates = [path for path in root.glob("**/inventory.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no fleet audit artifacts found under {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime).parent


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
