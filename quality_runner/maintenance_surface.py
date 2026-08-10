from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.artifacts import write_json, write_text
from quality_runner.config import load_repo_config
from quality_runner.maintenance_surface_diff import (
    WORKTREE_REF,
    changed_files,
    comparison_for,
    dependency_delta,
    diff_patch,
    file_summary,
    line_summary,
    patch_candidates,
)
from quality_runner.maintenance_surface_review import (
    REGRESSION_PROOF_SCHEMA as _REGRESSION_PROOF_SCHEMA,
)
from quality_runner.maintenance_surface_review import (
    contract_evidence,
    observation,
    regression_proof,
    vertical_slice_review,
)

MAINTENANCE_SURFACE_SCHEMA = "quality-runner-maintenance-surface-v0.1"
REGRESSION_PROOF_SCHEMA = _REGRESSION_PROOF_SCHEMA


def maintenance_surface_payload(
    repo_root: Path,
    *,
    base_ref: str = "HEAD",
    head_ref: str = WORKTREE_REF,
    behavior_added: tuple[str, ...] = (),
    behavior_removed: tuple[str, ...] = (),
    consolidated_concepts: tuple[str, ...] = (),
    regression_proof_path: Path | None = None,
    output_path: Path | None = None,
    handoff_output_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    comparison = comparison_for(root, base_ref=base_ref, head_ref=head_ref)
    changes = changed_files(root, comparison)
    patch = diff_patch(root, comparison)
    candidates = patch_candidates(root, patch, changes)
    dependencies = dependency_delta(root, comparison, changes)
    contract = contract_evidence(load_repo_config(root), changes, candidates)
    regression = regression_proof(regression_proof_path)
    removal = vertical_slice_review(root, comparison, changes, patch)
    observations = [*contract["observations"], *removal]
    if regression["status"] in {"invalid", "unavailable"}:
        observations.append(
            observation(
                "regression-proof-" + regression["status"],
                "Regression proof needs review before it can support the change.",
                evidence=[regression.get("reason", regression["status"])],
                confidence="high" if regression["status"] == "invalid" else "medium",
            )
        )

    blocked = bool(contract["invalid_config"] or regression["status"] == "invalid")
    status = "blocked" if blocked else "review_required" if observations else "ready"
    payload: dict[str, Any] = {
        "schema": MAINTENANCE_SURFACE_SCHEMA,
        "status": status,
        "implementation_allowed": False,
        "repository": str(root),
        "provenance": {
            "requested_base": comparison.requested_base,
            "requested_head": comparison.requested_head,
            "base_commit": comparison.base_commit,
            "head_commit": comparison.head_commit,
            "comparison_base_commit": comparison.comparison_base_commit,
            "working_tree": comparison.working_tree,
        },
        "supported_behavior": {
            "added": _unique(behavior_added),
            "removed": _unique(behavior_removed),
        },
        "maintenance_surface_delta": {
            "files": file_summary(changes),
            "lines": line_summary(changes),
            "dependencies": dependencies,
            "public_surface_candidates": candidates["public_surfaces"],
            "flag_or_config_candidates": candidates["flags_or_config"],
            "compatibility_candidates": candidates["compatibility"],
            "concepts_consolidated": _unique(consolidated_concepts),
        },
        "contracts": {
            "status": contract["status"],
            "behavior_owners": contract["behavior_owners"],
            "compatibility": contract["compatibility"],
        },
        "vertical_slice_removal": {
            "status": "review_required" if removal else "no_candidates",
            "observations": removal,
        },
        "regression_proof": regression,
        "observations": observations,
        "limitations": [
            "Counts describe the selected Git comparison; they do not score design quality.",
            "Public, configuration, compatibility, and removal findings are review candidates, not proof.",
            "Concept consolidation and supported behavior are author-declared and remain reviewer-verifiable.",
        ],
    }
    if output_path is not None:
        written = write_json(output_path.expanduser().resolve(), payload)
        payload["output_path"] = str(written)
    if handoff_output_path is not None:
        written = write_text(
            handoff_output_path.expanduser().resolve(), render_maintenance_surface_markdown(payload)
        )
        payload["handoff_output_path"] = str(written)
    return payload


def render_maintenance_surface_markdown(payload: dict[str, Any]) -> str:
    delta = payload["maintenance_surface_delta"]
    lines = delta["lines"]
    file_summary_payload = delta["files"]
    behavior = payload["supported_behavior"]
    rendered = [
        "## Maintenance surface",
        "",
        f"Status: `{payload['status']}`",
        "",
        "### Supported behavior",
        "",
        _markdown_items("Added", behavior["added"]),
        _markdown_items("Removed", behavior["removed"]),
        "",
        "### Change-surface evidence",
        "",
        f"- Files: {file_summary_payload['total']} changed "
        f"({file_summary_payload['added']} added, {file_summary_payload['modified']} modified, "
        f"{file_summary_payload['deleted']} deleted, {file_summary_payload['renamed']} renamed)",
        f"- Production lines: +{lines['production']['added']} / -{lines['production']['removed']}",
        f"- Test lines: +{lines['test']['added']} / -{lines['test']['removed']}",
        f"- Other lines: +{lines['other']['added']} / -{lines['other']['removed']}",
        _markdown_items("New dependencies", [item["name"] for item in delta["dependencies"]]),
        _markdown_items(
            "Public-surface candidates",
            [item["path"] for item in delta["public_surface_candidates"]],
        ),
        _markdown_items(
            "Flag/config candidates", [item["path"] for item in delta["flag_or_config_candidates"]]
        ),
        _markdown_items(
            "Compatibility candidates", [item["path"] for item in delta["compatibility_candidates"]]
        ),
        _markdown_items("Concepts consolidated", delta["concepts_consolidated"]),
        "",
        "### Review evidence",
        "",
        f"- Repository contracts: `{payload['contracts']['status']}`",
        f"- Regression proof: `{payload['regression_proof']['status']}`",
        _markdown_items(
            "Review observations", [item["message"] for item in payload["observations"]]
        ),
        "",
        "<!-- Generated by qr maintenance-surface; verify declared behavior and concepts in review. -->",
        "",
    ]
    return "\n".join(rendered)


def _unique(values: tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _markdown_items(label: str, values: list[str]) -> str:
    rendered = ", ".join(f"`{value}`" for value in values) if values else "none declared"
    return f"- {label}: {rendered}"
