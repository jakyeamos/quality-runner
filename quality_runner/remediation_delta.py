from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.artifacts import artifact_dir, write_json, write_text
from quality_runner.schema_constants import REMEDIATION_DELTA_SCHEMA


def build_remediation_delta(
    *,
    repo_root: Path,
    current_run_id: str,
    baseline_run_id: str,
) -> dict[str, Any]:
    current_dir = artifact_dir(repo_root, current_run_id)
    baseline_dir = artifact_dir(repo_root, baseline_run_id)
    current_audit = _load_json(current_dir / "quality-audit.json")
    baseline_audit = _load_json(baseline_dir / "quality-audit.json")
    current_plan = _load_json(current_dir / "remediation-plan.json")
    baseline_plan = _load_json(baseline_dir / "remediation-plan.json")
    current_capabilities = _load_json(current_dir / "capability-matrix.json")
    baseline_capabilities = _load_json(baseline_dir / "capability-matrix.json")
    current_preflight = _load_json(current_dir / "package-manager-preflight.json")
    baseline_preflight = _load_json(baseline_dir / "package-manager-preflight.json")
    current_gate = _load_optional_json(current_dir / "gate-verification.json")
    baseline_gate = _load_optional_json(baseline_dir / "gate-verification.json")

    current_findings = _findings(current_audit)
    baseline_findings = _findings(baseline_audit)
    current_by_fingerprint = _index_by_fingerprint(current_findings)
    baseline_by_fingerprint = _index_by_fingerprint(baseline_findings)
    current_fingerprints = set(current_by_fingerprint)
    baseline_fingerprints = set(baseline_by_fingerprint)

    current_slices = _slices(current_plan)
    baseline_slices = _slices(baseline_plan)
    current_slice_ids = set(current_slices)
    baseline_slice_ids = set(baseline_slices)

    package_evidence = _package_evidence(
        repo_root=repo_root,
        current_dir=current_dir,
        baseline_dir=baseline_dir,
        current_preflight=current_preflight,
        baseline_preflight=baseline_preflight,
    )
    changed = bool(
        current_fingerprints != baseline_fingerprints
        or current_slices != baseline_slices
        or package_evidence["changed"]
        or _gate_state(current_gate) != _gate_state(baseline_gate)
    )

    return {
        "schema": REMEDIATION_DELTA_SCHEMA,
        "implementation_allowed": False,
        "status": "changed" if changed else "unchanged",
        "current_run_id": current_run_id,
        "baseline_run_id": baseline_run_id,
        "findings": {
            "new": _finding_refs(
                current_by_fingerprint[key]
                for key in sorted(current_fingerprints - baseline_fingerprints)
            ),
            "persisted": _finding_refs(
                current_by_fingerprint[key]
                for key in sorted(current_fingerprints & baseline_fingerprints)
            ),
            "resolved": _finding_refs(
                baseline_by_fingerprint[key]
                for key in sorted(baseline_fingerprints - current_fingerprints)
            ),
        },
        "slices": {
            "added": [current_slices[key] for key in sorted(current_slice_ids - baseline_slice_ids)],
            "persisted": [
                {
                    "id": key,
                    "baseline": baseline_slices[key],
                    "current": current_slices[key],
                }
                for key in sorted(current_slice_ids & baseline_slice_ids)
            ],
            "removed": [
                baseline_slices[key] for key in sorted(baseline_slice_ids - current_slice_ids)
            ],
        },
        "capabilities": _capability_delta(
            current_capabilities=current_capabilities,
            baseline_capabilities=baseline_capabilities,
        ),
        "package_evidence": package_evidence,
        "verification": {
            "baseline": _gate_state(baseline_gate),
            "current": _gate_state(current_gate),
        },
        "recommendations": _recommendations(
            changed=changed,
            new_count=len(current_fingerprints - baseline_fingerprints),
            resolved_count=len(baseline_fingerprints - current_fingerprints),
            added_slice_count=len(current_slice_ids - baseline_slice_ids),
            removed_slice_count=len(baseline_slice_ids - current_slice_ids),
            package_changed=bool(package_evidence["changed"]),
        ),
        "source_artifacts": {
            "current_quality_audit_json": str(current_dir / "quality-audit.json"),
            "current_remediation_plan_json": str(current_dir / "remediation-plan.json"),
            "current_capability_matrix_json": str(current_dir / "capability-matrix.json"),
            "current_package_manager_preflight_json": str(
                current_dir / "package-manager-preflight.json"
            ),
            "current_gate_verification_json": str(current_dir / "gate-verification.json"),
            "baseline_quality_audit_json": str(baseline_dir / "quality-audit.json"),
            "baseline_remediation_plan_json": str(baseline_dir / "remediation-plan.json"),
            "baseline_capability_matrix_json": str(baseline_dir / "capability-matrix.json"),
            "baseline_package_manager_preflight_json": str(
                baseline_dir / "package-manager-preflight.json"
            ),
            "baseline_gate_verification_json": str(baseline_dir / "gate-verification.json"),
        },
    }


def persist_remediation_delta(
    *, repo_root: Path, current_run_id: str, payload: dict[str, Any]
) -> dict[str, str]:
    run_dir = artifact_dir(repo_root, current_run_id)
    json_path = write_json(run_dir / "remediation-delta.json", payload)
    markdown_path = write_text(
        run_dir / "remediation-delta.md", render_remediation_delta_markdown(payload)
    )
    return {
        "remediation_delta_json": str(json_path),
        "remediation_delta_md": str(markdown_path),
    }


def render_remediation_delta_markdown(payload: dict[str, Any]) -> str:
    findings = payload.get("findings")
    findings = findings if isinstance(findings, dict) else {}
    slices = payload.get("slices")
    slices = slices if isinstance(slices, dict) else {}
    package_evidence = payload.get("package_evidence")
    package_evidence = package_evidence if isinstance(package_evidence, dict) else {}
    lines = [
        "# Quality Runner Remediation Delta",
        "",
        f"- Current run: `{payload.get('current_run_id')}`",
        f"- Baseline run: `{payload.get('baseline_run_id')}`",
        f"- Status: **{payload.get('status', 'unknown')}**",
        "",
        "This is a tool-neutral evidence update. It does not create or modify a project plan.",
        "",
        "## Findings",
        "",
    ]
    for key, title in (("new", "New"), ("persisted", "Persisted"), ("resolved", "Resolved")):
        items = findings.get(key)
        items = items if isinstance(items, list) else []
        lines.append(f"### {title} ({len(items)})")
        lines.append("")
        if items:
            lines.extend(
                f"- `{item.get('fingerprint')}`: {item.get('summary', 'Quality Runner finding')}"
                for item in items
                if isinstance(item, dict)
            )
        else:
            lines.append("- None")
        lines.append("")

    lines.extend(["## Remediation Clusters", ""])
    for key, title in (("added", "Added"), ("persisted", "Persisted"), ("removed", "Removed")):
        items = slices.get(key)
        items = items if isinstance(items, list) else []
        lines.append(f"### {title} ({len(items)})")
        lines.append("")
        if items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                current = item.get("current")
                if isinstance(current, dict):
                    item = current
                lines.append(f"- `{item.get('id')}`: {item.get('title', 'Untitled cluster')}")
        else:
            lines.append("- None")
        lines.append("")

    changed_paths = package_evidence.get("changed_paths")
    changed_paths = changed_paths if isinstance(changed_paths, list) else []
    lines.extend(["## Package Evidence", ""])
    lines.append(f"- Changed: `{package_evidence.get('changed', False)}`")
    lines.append(f"- Package or lockfile paths: {len(changed_paths)}")
    if changed_paths:
        lines.extend(f"  - `{path}`" for path in changed_paths if isinstance(path, str))
    lines.extend(["", "## Recommendations", ""])
    recommendations = payload.get("recommendations")
    if isinstance(recommendations, list) and recommendations:
        lines.extend(f"- {item}" for item in recommendations if isinstance(item, str))
    else:
        lines.append("- No plan update is indicated by this comparison.")
    lines.append("")
    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required QR artifact does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"QR artifact must contain a JSON object: {path}")
    return payload


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json(path)


def _findings(audit: dict[str, Any]) -> list[dict[str, Any]]:
    findings = audit.get("findings")
    if not isinstance(findings, list):
        return []
    return [_normalize_finding(item) for item in findings if isinstance(item, dict)]


def _normalize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    stable = {
        key: finding.get(key)
        for key in ("id", "rule_id", "category", "file", "path", "summary", "evidence")
        if finding.get(key) is not None
    }
    normalized = dict(finding)
    normalized["fingerprint"] = str(finding.get("fingerprint") or _hash_payload(stable))
    return normalized


def _index_by_fingerprint(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["fingerprint"]): item for item in findings}


def _finding_refs(findings: Any) -> list[dict[str, Any]]:
    return [_finding_ref(item) for item in findings]


def _finding_ref(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": finding["fingerprint"],
        "id": finding.get("id"),
        "rule_id": finding.get("rule_id"),
        "file": _finding_path(finding),
        "severity": finding.get("severity"),
        "category": finding.get("category"),
        "summary": finding.get("summary") or finding.get("message") or "Quality Runner finding",
    }


def _finding_path(finding: dict[str, Any]) -> str | None:
    for key in ("file", "path", "location"):
        value = finding.get(key)
        if isinstance(value, str) and value and not value.startswith("/"):
            return value.split(":", 1)[0]
    return None


def _slices(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    slices = plan.get("slices")
    if not isinstance(slices, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in slices:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        findings = item.get("findings")
        finding_ids = sorted(
            str(finding.get("id"))
            for finding in findings
            if isinstance(finding, dict) and finding.get("id") is not None
        ) if isinstance(findings, list) else []
        result[item["id"]] = {
            "id": item["id"],
            "title": item.get("title", item["id"]),
            "priority": item.get("priority"),
            "finding_ids": finding_ids,
            "actions": item.get("actions", []) if isinstance(item.get("actions"), list) else [],
            "verification_gates": (
                item.get("verification_gates", [])
                if isinstance(item.get("verification_gates"), list)
                else []
            ),
        }
    return result


def _capability_delta(
    *, current_capabilities: dict[str, Any], baseline_capabilities: dict[str, Any]
) -> dict[str, Any]:
    current = _capability_states(current_capabilities)
    baseline = _capability_states(baseline_capabilities)
    return {
        "removed": sorted(set(baseline) - set(current)),
        "added": sorted(set(current) - set(baseline)),
        "changed": [
            {"id": capability_id, "baseline": baseline[capability_id], "current": current[capability_id]}
            for capability_id in sorted(set(current) & set(baseline))
            if current[capability_id] != baseline[capability_id]
        ],
        "baseline_total": len(baseline),
        "current_total": len(current),
    }


def _capability_states(payload: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in ("available", "missing"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                values[str(item["id"])] = key
    return values


def _package_evidence(
    *,
    repo_root: Path,
    current_dir: Path,
    baseline_dir: Path,
    current_preflight: dict[str, Any],
    baseline_preflight: dict[str, Any],
) -> dict[str, Any]:
    changed_paths = sorted(
        set(_package_diff_paths(repo_root, baseline_dir, current_dir))
        | set(_working_tree_package_paths(repo_root))
    )
    preflight_changed = _package_snapshot(current_preflight) != _package_snapshot(
        baseline_preflight
    )
    changed = bool(changed_paths or preflight_changed)
    return {
        "changed": changed,
        "changed_paths": changed_paths,
        "current": _package_snapshot(current_preflight),
        "baseline": _package_snapshot(baseline_preflight),
    }


def _package_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_manager": payload.get("package_manager"),
        "declared_package_manager": payload.get("declared_package_manager"),
        "lockfiles": payload.get("lockfiles", []),
        "nested_lockfiles": payload.get("nested_lockfiles", []),
        "warnings": payload.get("warnings", []),
    }


def _package_diff_paths(repo_root: Path, baseline_dir: Path, current_dir: Path) -> list[str]:
    baseline_sha = _run_head_sha(baseline_dir)
    current_sha = _run_head_sha(current_dir)
    if not baseline_sha or not current_sha or baseline_sha == current_sha:
        return []
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", baseline_sha, current_sha],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return sorted(
        path
        for path in result.stdout.splitlines()
        if path and _is_package_path(path)
    )


def _working_tree_package_paths(repo_root: Path) -> list[str]:
    if not (repo_root / ".git").exists():
        return []
    paths: set[str] = set()
    for args in (("diff", "--name-only", "HEAD"), ("diff", "--cached", "--name-only"), ("ls-files", "--others", "--exclude-standard")):
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            paths.update(
                path for path in result.stdout.splitlines() if path and _is_package_path(path)
            )
    return sorted(paths)


def _run_head_sha(run_dir: Path) -> str | None:
    manifest_path = run_dir / "run-manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    git_state = manifest.get("git") if isinstance(manifest, dict) else None
    head_sha = git_state.get("head_sha") if isinstance(git_state, dict) else None
    return head_sha if isinstance(head_sha, str) and head_sha else None


def _is_package_path(path: str) -> bool:
    name = Path(path).name
    return (
        name in {
            "package.json",
            "pnpm-lock.yaml",
            "package-lock.json",
            "yarn.lock",
            "bun.lock",
            "bun.lockb",
            "pyproject.toml",
            "uv.lock",
            "requirements.txt",
            "Cargo.toml",
            "Cargo.lock",
            "go.mod",
            "go.sum",
            "Gemfile",
            "Gemfile.lock",
            "composer.json",
            "composer.lock",
        }
        or name.startswith("requirements-")
    )


def _gate_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status", "unavailable"),
        "failure_type": payload.get("failure_type"),
        "blockers": payload.get("blockers", []) if isinstance(payload.get("blockers", []), list) else [],
    }


def _recommendations(
    *,
    changed: bool,
    new_count: int,
    resolved_count: int,
    added_slice_count: int,
    removed_slice_count: int,
    package_changed: bool,
) -> list[str]:
    if not changed:
        return ["No QR evidence changed; existing work items remain current."]
    recommendations: list[str] = []
    if package_changed:
        recommendations.append(
            "Recheck dependency and package-manager assumptions before executing existing work items."
        )
    if new_count or added_slice_count:
        recommendations.append(
            "Add new findings or remediation clusters to the consumer's work queue."
        )
    if resolved_count or removed_slice_count:
        recommendations.append(
            "Close or mark resolved work only after reviewing the current evidence and verification state."
        )
    recommendations.append(
        "Keep the consumer plan's structure and ownership decisions; update only the affected work items."
    )
    return recommendations


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
