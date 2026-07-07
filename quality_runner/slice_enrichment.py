from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.evidence_excerpts import enrich_finding_evidence
from quality_runner.finding_quality import compute_finding_quality, compute_leverage


def enrich_remediation_slices(
    slices: list[dict[str, Any]],
    *,
    repo_root: Path | None,
    git_state: dict[str, Any] | None,
    code_quality_scan: dict[str, Any] | None,
    run_id: str | None,
) -> list[dict[str, Any]]:
    raw_by_id = _raw_findings_by_id(code_quality_scan)
    planned_at = _planned_at(git_state)
    enriched: list[dict[str, Any]] = []
    for slice_item in slices:
        item = dict(slice_item)
        findings = item.get("findings")
        if isinstance(findings, list):
            item["findings"] = [
                _enrich_slice_finding(
                    finding,
                    repo_root=repo_root,
                    raw_by_id=raw_by_id,
                )
                for finding in findings
                if isinstance(finding, dict)
            ]
        quality = _slice_quality(item, raw_by_id=raw_by_id)
        item.update(quality)
        item["leverage"] = compute_leverage(quality)
        if planned_at is not None:
            item["planned_at"] = planned_at
        drift_paths = _scope_paths(item)
        if planned_at is not None and drift_paths:
            head = planned_at.get("head")
            if isinstance(head, str) and head:
                item["drift_check"] = {
                    "command": _drift_command(head, drift_paths),
                    "paths": drift_paths,
                }
        item["scope"] = _slice_scope(item, raw_by_id=raw_by_id)
        item["stop_conditions"] = _stop_conditions(item)
        if run_id:
            item["source_run_id"] = run_id
        enriched.append(item)
    return enriched


def _enrich_slice_finding(
    finding: dict[str, Any],
    *,
    repo_root: Path | None,
    raw_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    item = dict(finding)
    raw = raw_by_id.get(str(item.get("id") or ""))
    raw_group = [raw] if raw else None
    item.update(compute_finding_quality(item, raw_findings=raw_group))
    excerpt = enrich_finding_evidence(repo_root, item)
    if excerpt is not None:
        item["evidence_excerpt"] = excerpt
    return item


def _slice_quality(
    slice_item: dict[str, Any],
    *,
    raw_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    findings = slice_item.get("findings")
    if not isinstance(findings, list) or not findings:
        representative = {"category": "", "severity": "warning", "score": slice_item.get("score")}
        return compute_finding_quality(representative)
    first = findings[0]
    raw_group = [
        raw_by_id[str(finding["id"])]
        for finding in findings
        if isinstance(finding, dict)
        and isinstance(finding.get("id"), str)
        and finding["id"] in raw_by_id
    ]
    aggregate = {
        "id": first.get("id"),
        "severity": first.get("severity"),
        "category": first.get("category"),
        "score": slice_item.get("score"),
        "summary": first.get("summary"),
    }
    return compute_finding_quality(aggregate, raw_findings=raw_group or None)


def _planned_at(git_state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(git_state, dict) or not git_state.get("is_repo"):
        return None
    head = git_state.get("head_sha")
    branch = git_state.get("branch")
    dirty = git_state.get("dirty")
    if not isinstance(head, str) or not head:
        return None
    return {
        "head": head,
        "branch": branch if isinstance(branch, str) else None,
        "dirty": bool(dirty) if isinstance(dirty, bool) else None,
    }


def _drift_command(head: str, paths: list[str]) -> str:
    quoted = " ".join(f'"{path}"' for path in paths)
    return f"git diff --stat {head}..HEAD -- {quoted}"


def _scope_paths(slice_item: dict[str, Any]) -> list[str]:
    findings = slice_item.get("findings")
    if not isinstance(findings, list):
        return []
    paths = sorted(
        {
            str(finding["file"])
            for finding in findings
            if isinstance(finding, dict)
            and isinstance(finding.get("file"), str)
            and finding["file"]
        }
    )
    return paths


def _slice_scope(
    slice_item: dict[str, Any],
    *,
    raw_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    findings = slice_item.get("findings")
    if not isinstance(findings, list):
        return {"in_scope": [], "out_of_scope": _default_out_of_scope()}
    fingerprints = sorted(
        {
            str(finding["fingerprint"])
            for finding in findings
            if isinstance(finding, dict)
            and isinstance(finding.get("fingerprint"), str)
            and finding["fingerprint"]
        }
    )
    files = _scope_paths(slice_item)
    in_scope: list[str] = []
    if fingerprints:
        in_scope.append(
            f"Only files and rows for fingerprints {', '.join(fingerprints[:8])}"
            + (" …" if len(fingerprints) > 8 else "")
        )
    elif files:
        in_scope.append(f"Only listed files: {', '.join(files)}")
    else:
        finding_ids = [
            str(finding["id"])
            for finding in findings
            if isinstance(finding, dict) and isinstance(finding.get("id"), str)
        ]
        if finding_ids:
            in_scope.append(f"Only findings {', '.join(finding_ids)}")
        else:
            in_scope.append(f"Only slice {slice_item.get('id')} findings and declared actions.")
    categories = {
        str(raw_by_id[finding["id"]]["category"])
        for finding in findings
        if isinstance(finding, dict)
        and isinstance(finding.get("id"), str)
        and finding["id"] in raw_by_id
        and isinstance(raw_by_id[finding["id"]].get("category"), str)
    }
    if len(categories) == 1:
        in_scope.append(f"Same finding family only ({next(iter(categories))}).")
    return {"in_scope": in_scope, "out_of_scope": _default_out_of_scope()}


def _default_out_of_scope() -> list[str]:
    return [
        "Do not reformat unrelated files.",
        "Do not fix adjacent TODOs unless they are in the same finding family.",
        "Do not change public API behavior without explicit approval.",
    ]


def _stop_conditions(slice_item: dict[str, Any]) -> list[str]:
    conditions = [
        "Stop and report if current code no longer matches the QR evidence excerpt.",
        "Stop if the fix requires touching files outside the slice scope.",
        "Stop if the finding appears intentional and should become an accepted disposition.",
        "Stop after two failed focused verification attempts.",
    ]
    if slice_item.get("disposition_required") is True:
        conditions.append(
            "Stop after documenting wire, finish, descope, or accepted-WIP disposition."
        )
    findings = slice_item.get("findings")
    if isinstance(findings, list) and any(
        isinstance(finding, dict) and str(finding.get("category", "")).startswith("structural:")
        for finding in findings
    ):
        conditions.append(
            "Stop if the row is generated, vendor, or test-fixture code that QR should exclude instead."
        )
    return conditions


def _raw_findings_by_id(code_quality_scan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(code_quality_scan, dict):
        return {}
    findings = code_quality_scan.get("findings")
    if not isinstance(findings, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = finding.get("id")
        if isinstance(finding_id, str) and finding_id:
            indexed[finding_id] = finding
    return indexed
