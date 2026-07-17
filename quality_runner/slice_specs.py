from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from quality_runner.artifacts import (
    artifact_text_file,
    existing_artifact_dir,
    prepare_directory,
    safe_child_file,
    validate_path_segment,
    write_text,
)
from quality_runner.intent_docs import intent_docs_markdown_lines


def render_slice_spec_markdown(
    slice_item: dict[str, Any],
    *,
    run_id: str | None = None,
    intent_docs: list[dict[str, str]] | None = None,
) -> str:
    lines = [
        f"# Slice Spec: {slice_item.get('id')}",
        "",
        f"- Run: {run_id or 'unknown'}",
        f"- Title: {slice_item.get('title')}",
        f"- Priority: {slice_item.get('priority')}",
        "",
        "## Why this matters",
        "",
        str(slice_item.get("impact") or "Review the linked finding summaries."),
        "",
        "## Current state",
        "",
    ]
    lines.extend(_evidence_sections(slice_item.get("findings")))
    lines.extend(["", "## Commands needed", ""])
    lines.extend(_markdown_items(slice_item.get("verification_gates"), prefix="command"))
    lines.extend(["", "## In scope", ""])
    lines.extend(_scope_items(slice_item.get("scope"), field="in_scope"))
    lines.extend(["", "## Out of scope", ""])
    lines.extend(_scope_items(slice_item.get("scope"), field="out_of_scope"))
    lines.extend(["", "## Ordered steps", ""])
    lines.extend(_numbered_items(slice_item.get("actions")))
    lines.extend(["", "## Per-step verification", ""])
    lines.extend(_numbered_items(slice_item.get("verification_gates")))
    lines.extend(["", "## Done criteria", ""])
    lines.append("- Listed verification gates pass.")
    lines.append("- Linked finding fingerprints are cleared or dispositioned with evidence.")
    lines.append("- `quality-runner refresh` no longer reports the targeted finding family.")
    lines.extend(["", "## STOP conditions", ""])
    lines.extend(_markdown_items(slice_item.get("stop_conditions")))
    planned_at = slice_item.get("planned_at")
    if isinstance(planned_at, dict):
        lines.extend(["", "## Planned-at git state", ""])
        for key in ("head", "branch", "dirty"):
            value = planned_at.get(key)
            if value is not None:
                lines.append(f"- {key}: {value}")
        drift_check = slice_item.get("drift_check")
        if isinstance(drift_check, dict):
            command = drift_check.get("command")
            if isinstance(command, str) and command:
                lines.append(f"- drift check: `{command}`")
    leverage = slice_item.get("leverage")
    if isinstance(leverage, dict):
        lines.extend(["", "## Leverage", ""])
        rank = leverage.get("rank")
        explanation = leverage.get("explanation")
        if rank is not None:
            lines.append(f"- rank: {rank}")
        if isinstance(explanation, str) and explanation:
            lines.append(f"- {explanation}")
    lines.extend(intent_docs_markdown_lines(intent_docs or []))
    lines.extend(["", "## Maintenance notes", ""])
    lines.append("- QR does not apply fixes; export evidence if the repo state drifts.")
    lines.append("- Prefer accepted dispositions over silent ignores for intentional tradeoffs.")
    return "\n".join(lines).rstrip() + "\n"


def write_slice_specs(
    run_dir: Path,
    slices: list[dict[str, Any]],
    *,
    run_id: str | None,
    intent_docs: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ValueError("slice spec run directory must be a regular directory")
    specs_dir = prepare_directory(run_dir, "slice-specs")
    paths: dict[str, str] = {}
    for slice_item in slices:
        if not isinstance(slice_item, dict):
            continue
        slice_id = slice_item.get("id")
        if not isinstance(slice_id, str) or not slice_id:
            continue
        filename = _slice_spec_filename(slice_id)
        target = safe_child_file(specs_dir, filename)
        content = render_slice_spec_markdown(
            slice_item,
            run_id=run_id,
            intent_docs=intent_docs,
        )
        paths[slice_id] = str(write_text(target, content))
    return paths


def _slice_spec_filename(slice_id: str) -> str:
    try:
        validate_path_segment(slice_id, label="slice_id")
    except ValueError:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slice_id).strip(".-") or "slice"
        digest = hashlib.sha256(slice_id.encode("utf-8")).hexdigest()[:10]
        return f"{slug[:180]}-{digest}.md"
    return f"{slice_id}.md"


def export_slice_specs_payload(
    *,
    repo_root: Path,
    run_id: str,
) -> dict[str, Any]:
    run_dir = existing_artifact_dir(repo_root, run_id)
    try:
        plan_path = artifact_text_file(repo_root, run_id, "remediation-plan.json")
    except FileNotFoundError as error:
        raise FileNotFoundError(f"remediation plan not found for run: {run_id}") from error
    import json

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    slices = plan.get("slices")
    if not isinstance(slices, list):
        raise ValueError("remediation plan slices must be a list")
    for slice_item in slices:
        if not isinstance(slice_item, dict):
            continue
        slice_id = slice_item.get("id")
        if isinstance(slice_id, str) and slice_id:
            validate_path_segment(slice_id, label="slice_id")
    scan_path = safe_child_file(run_dir, "repo-scan.json")
    intent_docs = None
    if scan_path.exists():
        scan = json.loads(scan_path.read_text(encoding="utf-8"))
        discovered = scan.get("intent_docs")
        if isinstance(discovered, list):
            intent_docs = discovered
    paths = write_slice_specs(
        run_dir,
        slices,
        run_id=run_id,
        intent_docs=intent_docs,
    )
    return {
        "schema": "quality-runner-export-slice-specs-result-v0.1",
        "run_id": run_id,
        "slice_spec_paths": paths,
        "slice_spec_dir": str(run_dir / "slice-specs"),
    }


def _evidence_sections(findings: object) -> list[str]:
    if not isinstance(findings, list):
        return ["- No finding evidence captured."]
    lines: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = finding.get("id")
        summary = finding.get("summary")
        if isinstance(finding_id, str) and isinstance(summary, str):
            lines.append(f"- {finding_id}: {summary}")
        excerpt = finding.get("evidence_excerpt")
        if isinstance(excerpt, dict):
            file = excerpt.get("file")
            line = excerpt.get("line")
            text = excerpt.get("excerpt")
            if isinstance(file, str) and isinstance(line, int) and isinstance(text, str):
                lines.append(f"  - `{file}:{line}`")
                lines.append("    ```")
                for before in excerpt.get("context_before") or []:
                    if isinstance(before, str):
                        lines.append(f"    {before}")
                lines.append(f"    {text}")
                for after in excerpt.get("context_after") or []:
                    if isinstance(after, str):
                        lines.append(f"    {after}")
                lines.append("    ```")
    return lines or ["- No finding evidence captured."]


def _markdown_items(value: object, *, prefix: str = "item") -> list[str]:
    if not isinstance(value, list):
        return [f"- No {prefix} recorded."]
    items = [item for item in value if isinstance(item, str) and item]
    if not items:
        return [f"- No {prefix} recorded."]
    return [f"- {item}" for item in items]


def _numbered_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["1. unavailable"]
    items = [item for item in value if isinstance(item, str) and item]
    if not items:
        return ["1. unavailable"]
    return [f"{index}. {item}" for index, item in enumerate(items, start=1)]


def _scope_items(scope: object, *, field: str) -> list[str]:
    if not isinstance(scope, dict):
        return ["- unavailable"]
    items = scope.get(field)
    if not isinstance(items, list) or not items:
        return ["- unavailable"]
    return [f"- {item}" for item in items if isinstance(item, str) and item]
