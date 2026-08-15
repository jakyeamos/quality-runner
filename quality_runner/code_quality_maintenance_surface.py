from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from quality_runner.branch_diff import BRANCH_DIFF_SCOPE_BASIS
from quality_runner.code_quality_findings import _finding
from quality_runner.maintenance_surface import (
    MAINTENANCE_SURFACE_SCHEMA,
    WORKTREE_REF,
    maintenance_surface_payload,
)

MAINTENANCE_CATEGORY = "maintenance-surface"
MAINTENANCE_BUCKET = "maintenance-surface review"
_SOURCE_SUFFIXES = {".go", ".java", ".js", ".jsx", ".mjs", ".py", ".rs", ".ts", ".tsx"}
_CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml"}
_TEST_PATH = re.compile(r"(^|/)(tests?|specs?|__tests__)(/|$)|(^|/)(test_|.*[._](?:test|spec)\.)")


def maintenance_surface_scan_findings(
    repo_root: Path,
    *,
    scope_metadata: dict[str, object] | None = None,
    eligible_paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project maintenance-surface evidence into native code-quality findings.

    A repository scan defaults to the current HEAD-to-worktree comparison. A
    branch-diff scan reuses its already-resolved base and includes the current
    working tree only when that scope explicitly did so.
    """

    base_ref, head_ref = _comparison_refs(scope_metadata)
    try:
        payload = maintenance_surface_payload(
            repo_root,
            base_ref=base_ref,
            head_ref=head_ref,
        )
    except ValueError as error:
        return [], {
            "schema": MAINTENANCE_SURFACE_SCHEMA,
            "status": "unavailable",
            "reason": str(error),
            "finding_count": 0,
        }

    findings = [
        *_dependency_findings(payload),
        *_candidate_findings(repo_root, payload, eligible_paths=eligible_paths),
        *_observation_findings(repo_root, payload),
    ]
    delta = payload["maintenance_surface_delta"]
    source_status = payload["status"]
    summary = {
        "schema": MAINTENANCE_SURFACE_SCHEMA,
        "status": ("review_required" if findings and source_status == "ready" else source_status),
        "source_status": source_status,
        "provenance": payload["provenance"],
        "contract_status": payload["contracts"]["status"],
        "finding_count": len(findings),
        "candidate_counts": {
            "dependencies": len(delta["dependencies"]),
            "public_surfaces": len(delta["public_surface_candidates"]),
            "flags_or_config": len(delta["flag_or_config_candidates"]),
            "compatibility": len(delta["compatibility_candidates"]),
            "review_observations": len(payload["observations"]),
        },
        "projected_counts": _projected_counts(findings),
    }
    return findings, summary


def _comparison_refs(scope_metadata: dict[str, object] | None) -> tuple[str, str]:
    if not isinstance(scope_metadata, dict):
        return "HEAD", WORKTREE_REF
    if scope_metadata.get("scope_basis") != BRANCH_DIFF_SCOPE_BASIS:
        return "HEAD", WORKTREE_REF
    base = scope_metadata.get("requested_base")
    head = scope_metadata.get("requested_head")
    if not isinstance(base, str) or not base:
        return "HEAD", WORKTREE_REF
    if scope_metadata.get("working_tree_included") is True:
        return base, WORKTREE_REF
    return base, head if isinstance(head, str) and head else "HEAD"


def _dependency_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    dependencies = payload["maintenance_surface_delta"]["dependencies"]
    return [
        _finding(
            category=MAINTENANCE_CATEGORY,
            severity="observation",
            confidence="high",
            file=item["manifest"],
            line=1,
            rule_id="maintenance-new-dependency",
            evidence=f"Added dependency {item['name']!r} in {item['manifest']}",
            expected_improvement=(
                "Confirm the dependency replaces less maintainable local code, has an owner, "
                "and is covered by the repository's dependency policy."
            ),
            risk=(
                "Every direct dependency adds upgrade, compatibility, security, and removal work."
            ),
            verification=(
                "Review the manifest diff, run the dependency audit, and rerun "
                "qr maintenance-surface for the selected comparison."
            ),
            remediation_bucket=MAINTENANCE_BUCKET,
        )
        for item in dependencies
    ]


def _candidate_findings(
    repo_root: Path,
    payload: dict[str, Any],
    *,
    eligible_paths: set[str] | None,
) -> list[dict[str, Any]]:
    delta = payload["maintenance_surface_delta"]
    findings: list[dict[str, Any]] = []
    definitions = (
        (
            "public_surface_candidates",
            "maintenance-public-surface",
            "medium",
            "Confirm the surface has one durable owner and only the intended consumers.",
            "An accidental or parallel public surface increases compatibility and support work.",
            "Review consumers and run the relevant API or contract tests.",
        ),
        (
            "flag_or_config_candidates",
            "maintenance-config-surface",
            "low",
            "Confirm the configuration path has an owner, default behavior, and retirement plan.",
            "Unowned flags and configuration paths multiply supported runtime states.",
            "Exercise both the default and configured paths, then document the removal condition.",
        ),
        (
            "compatibility_candidates",
            "maintenance-compatibility-surface",
            "medium",
            "Name the supported consumer, behavior owner, and evidence-backed removal condition.",
            "Compatibility code without an explicit consumer or exit condition tends to become permanent.",
            "Verify the named consumer and removal condition, then rerun qr maintenance-surface.",
        ),
    )
    for field, rule_id, confidence, improvement, risk, verification in definitions:
        grouped: dict[str, list[str]] = {}
        for candidate in delta[field]:
            path = candidate["path"]
            if not _candidate_path_is_eligible(
                path,
                field=field,
                eligible_paths=eligible_paths,
            ):
                continue
            grouped.setdefault(path, []).append(candidate["evidence"])
        for path, evidence_items in grouped.items():
            evidence = _grouped_evidence(evidence_items)
            findings.append(
                _finding(
                    category=MAINTENANCE_CATEGORY,
                    severity="observation",
                    confidence=confidence,
                    file=path,
                    line=_evidence_line(repo_root, path, evidence_items[0]),
                    rule_id=rule_id,
                    evidence=evidence,
                    expected_improvement=improvement,
                    risk=risk,
                    verification=verification,
                    remediation_bucket=MAINTENANCE_BUCKET,
                )
            )
    return findings


def _candidate_path_is_eligible(
    path: str,
    *,
    field: str,
    eligible_paths: set[str] | None,
) -> bool:
    if eligible_paths is not None and path not in eligible_paths:
        return False
    if _TEST_PATH.search(path):
        return False
    suffix = PurePosixPath(path).suffix.lower()
    if field in {"public_surface_candidates", "compatibility_candidates"}:
        return suffix in _SOURCE_SUFFIXES
    return suffix in _SOURCE_SUFFIXES | _CONFIG_SUFFIXES


def _grouped_evidence(items: list[str]) -> str:
    unique = list(dict.fromkeys(items))
    rendered = " | ".join(unique[:3])
    remaining = len(unique) - 3
    return f"{rendered} | +{remaining} more candidate(s)" if remaining > 0 else rendered


def _observation_findings(repo_root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in payload["observations"]:
        evidence_items = [str(value) for value in item.get("evidence", []) if str(value)]
        path = _observation_path(repo_root, evidence_items)
        evidence = " | ".join(evidence_items) or str(item["message"])
        findings.append(
            _finding(
                category=MAINTENANCE_CATEGORY,
                severity="observation",
                confidence=str(item.get("confidence", "low")),
                file=path,
                line=1,
                rule_id=f"maintenance-{item['id']}",
                evidence=evidence,
                expected_improvement=str(item["message"]),
                risk=(
                    "Leaving this maintenance-surface observation unresolved can preserve "
                    "ambiguous ownership, compatibility, or removal behavior."
                ),
                verification=(
                    "Resolve or explicitly disposition the observation and rerun "
                    "qr maintenance-surface for the same comparison."
                ),
                remediation_bucket=MAINTENANCE_BUCKET,
            )
        )
    return findings


def _observation_path(repo_root: Path, evidence: list[str]) -> str:
    for value in evidence:
        candidate = value.split(":", 1)[0]
        if candidate and (repo_root / candidate).exists():
            return candidate
        if (
            candidate
            and ("/" in candidate or Path(candidate).suffix)
            and not any(character.isspace() for character in candidate)
        ):
            return candidate
    return ".quality-runner.toml"


def _evidence_line(repo_root: Path, relative_path: str, evidence: str) -> int:
    try:
        lines = (repo_root / relative_path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return 1
    needle = evidence.strip()
    for index, line in enumerate(lines, start=1):
        if line.strip() == needle:
            return index
    return 1


def _projected_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        rule_id = str(finding["rule_id"])
        counts[rule_id] = counts.get(rule_id, 0) + 1
    return dict(sorted(counts.items()))
