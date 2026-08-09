"""Derive report-only finding and backfill capabilities from Quality Runner skills.

Skills remain domain procedures. This module describes the part of an active
Quality Runner representation that can be harvested into findings and
backfill evidence. It intentionally does not execute or mutate repositories.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAPABILITY_SCHEMA = "quality-runner-skill-capability/v1"
DEFAULT_CAPABILITY_FEED = (
    Path.home() / ".quality-runner" / "skill-capabilities" / "current" / "capabilities.json"
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _phase(phase_id: str, state: str, evidence: str) -> dict[str, str]:
    return {"id": phase_id, "state": state, "evidence": evidence}


def _report_only_backfill(*, has_verification: bool = True) -> dict[str, Any]:
    phases = [
        _phase("detect", "native", "Quality Runner evaluates the configured skill rules."),
        _phase("report", "native", "Findings are emitted with evidence, risk, and expected improvement."),
        _phase("plan", "available", "Findings can enter the existing remediation and handoff projections."),
        _phase("apply", "unsupported", "Quality Runner does not apply code changes from a skill finding."),
        _phase(
            "verify",
            "required" if has_verification else "not_evidenced",
            "A later gate or owner-controlled check must verify the remediation result.",
        ),
    ]
    return {
        "mode": "report_and_plan",
        "phases": phases,
        "safety": "Report-only; no automatic code changes are authorized by this capability record.",
    }


def _unknown_backfill() -> dict[str, Any]:
    return {
        "mode": "not_evidenced",
        "phases": [
            _phase("detect", "not_evidenced", "No reviewed Quality Runner representation was found."),
            _phase("report", "not_evidenced", "No finding-producing adapter was found."),
            _phase("plan", "not_evidenced", "Backfill planning cannot be inferred from skill inventory alone."),
            _phase("apply", "unsupported", "No automatic application path is implied."),
            _phase("verify", "not_evidenced", "Verification evidence is unavailable."),
        ],
        "safety": "Inventory evidence only; review is required before treating this skill as a finding source.",
    }


def _quality_runner_representation(
    *,
    skill_id: str,
    coverage: list[dict[str, Any]],
    quality_scan_present: bool,
    finding_categories: list[str],
    adapter: str = "quality_skill",
) -> dict[str, Any]:
    if not quality_scan_present:
        return {
            "status": "configured",
            "adapter": adapter,
            "finding_categories": finding_categories,
            "coverage": {
                "rule_count": len(coverage),
                "finding_count": 0,
                "statuses": [],
            },
            "evidence": ["The skill is represented by an active Quality Runner pack."],
            "gaps": ["No run-specific coverage was supplied to this capability report."],
        }

    statuses = sorted(
        {
            str(item.get("status"))
            for item in coverage
            if isinstance(item, dict) and isinstance(item.get("status"), str)
        }
    )
    finding_count = sum(
        _int_value(item.get("finding_count"))
        for item in coverage
        if isinstance(item, dict)
    )
    coverage_proven = bool(coverage) and all(
        status in {"evaluated", "matched", "reviewed"} for status in statuses
    )
    status = "coverage_proven" if coverage_proven else "configured"
    gaps = []
    if not coverage:
        gaps.append("The active pack has no deterministic or agent-review coverage entries.")
    if any(value in {"skipped", "no_matching_files", "review_required", "review_rejected"} for value in statuses):
        gaps.append("At least one configured rule or review is not covered by a successful evaluation.")
    return {
        "status": status,
        "adapter": adapter,
        "finding_categories": finding_categories,
        "coverage": {
            "rule_count": len(coverage),
            "finding_count": finding_count,
            "statuses": statuses,
        },
        "evidence": [
            "The supplied Quality Runner scan contains this skill and its coverage records."
        ],
        "gaps": gaps,
    }


def _skill_pack_capability(
    skill: dict[str, Any],
    *,
    coverage: list[dict[str, Any]],
    quality_scan_present: bool,
) -> dict[str, Any]:
    skill_id = str(skill.get("id") or "unknown")
    skill_name = str(skill.get("name") or skill_id)
    deterministic_rules = [
        item for item in skill.get("deterministic_rules", []) if isinstance(item, dict)
    ]
    agent_reviews = [item for item in skill.get("agent_reviews", []) if isinstance(item, dict)]
    classes: list[dict[str, str]] = []
    for rule in deterministic_rules:
        rule_id = str(rule.get("id") or "unknown-rule")
        rule_type = str(rule.get("type") or "deterministic")
        classes.append(
            {
                "id": rule_id,
                "label": f"{rule_type}: {rule_id}",
                "state": "native",
                "evidence": "Declared deterministic Quality Runner rule.",
            }
        )
    for review in agent_reviews:
        review_id = str(review.get("id") or "unknown-review")
        category = str(review.get("category") or "agent review")
        classes.append(
            {
                "id": review_id,
                "label": f"{category}: {review_id}",
                "state": "review_required",
                "evidence": "Declared agent review; a review report is required for findings.",
            }
        )

    if not classes:
        return {
            "id": skill_id,
            "name": skill_name,
            "finding_expectation": "review_required",
            "finding_expectation_reason": "The pack is active but declares no deterministic rule or agent review that can emit a finding.",
            "finding_classes": [],
            "backfill": _unknown_backfill(),
            "quality_runner": {
                "status": "configured",
                "adapter": "quality_skill",
                "finding_categories": [f"skill:{skill_id}"],
                "coverage": {"rule_count": 0, "finding_count": 0, "statuses": []},
                "evidence": ["The skill is present in the active Quality Runner selection."],
                "gaps": ["No finding-producing rule or review is declared."],
            },
            "gaps": ["Add a reviewed deterministic rule or agent review before expecting findings."],
        }

    return {
        "id": skill_id,
        "name": skill_name,
        "finding_expectation": "required",
        "finding_expectation_reason": "The active pack declares finding-producing Quality Runner rules or reviews.",
        "finding_classes": classes,
        "backfill": _report_only_backfill(has_verification=True),
        "quality_runner": _quality_runner_representation(
            skill_id=skill_id,
            coverage=coverage,
            quality_scan_present=quality_scan_present,
            finding_categories=[f"skill:{skill_id}"],
        ),
        "gaps": [
            "Apply remains owner-controlled; finding presence is not proof that remediation is safe or complete."
        ],
    }


def _native_debloat_capability(
    *,
    quality_scan: dict[str, Any] | None,
) -> dict[str, Any]:
    coverage = [
        item
        for item in (quality_scan or {}).get("skill_coverage", [])
        if isinstance(item, dict) and item.get("skill_id") == "debloat-repository"
    ]
    findings = [
        item
        for item in (quality_scan or {}).get("findings", [])
        if isinstance(item, dict) and item.get("category") == "debloat"
    ]
    quality_scan_present = isinstance(quality_scan, dict)
    if quality_scan_present:
        representation = _quality_runner_representation(
            skill_id="debloat-repository",
            coverage=coverage,
            quality_scan_present=True,
            finding_categories=["debloat"],
            adapter="native_debloat_category",
        )
        representation["status"] = "scan_observed"
        representation["coverage"]["finding_count"] = len(findings)
        representation["evidence"] = [
            "Quality Runner has a native debloat category and the supplied scan was inspected."
        ]
        if not findings:
            representation["gaps"].append(
                "The scan produced no debloat finding; that is a clean result, not proof that the repository has no ownership or architectural pressure."
            )
    else:
        representation = {
            "status": "adapter_defined",
            "adapter": "native_debloat_category",
            "finding_categories": ["debloat"],
            "coverage": {"rule_count": 2, "finding_count": 0, "statuses": []},
            "evidence": [
                "Quality Runner defines native debloat structural signals: large-source-file and fat-router."
            ],
            "gaps": [
                "No current Quality Runner scan was supplied, so repository-specific coverage is unknown."
            ],
        }
    return {
        "id": "debloat-repository",
        "name": "Debloat repository",
        "finding_expectation": "required",
        "finding_expectation_reason": "Debloat is an audit skill: it should produce reviewable structural candidate findings rather than silently deleting code.",
        "finding_classes": [
            {
                "id": "large-source-file",
                "label": "Large source file",
                "state": "native",
                "evidence": "Native Quality Runner debloat rule.",
            },
            {
                "id": "fat-router",
                "label": "Fat router",
                "state": "native",
                "evidence": "Native Quality Runner debloat rule.",
            },
            {
                "id": "ownership-pressure-review",
                "label": "Ownership-pressure review",
                "state": "review_required",
                "evidence": "Structural signals are candidate triggers; ownership and deletion decisions require review.",
            },
        ],
        "backfill": _report_only_backfill(has_verification=True),
        "quality_runner": representation,
        "gaps": [
            "File size and router size are triggers for a read-only audit, not proof of bloat or authorization to delete code.",
            "Apply and final verification remain owner-controlled.",
        ],
    }


def build_skill_capabilities(
    *,
    quality_skills: list[dict[str, Any]] | None = None,
    skill_coverage: list[dict[str, Any]] | None = None,
    findings: list[dict[str, Any]] | None = None,
    quality_scan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return capability records without assigning a scalar skill score."""

    active = [item for item in (quality_skills or []) if isinstance(item, dict)]
    coverage_items = [item for item in (skill_coverage or []) if isinstance(item, dict)]
    scan_present = isinstance(quality_scan, dict)
    records: dict[str, dict[str, Any]] = {
        "debloat-repository": _native_debloat_capability(quality_scan=quality_scan)
    }
    for skill in active:
        skill_id = str(skill.get("id") or "unknown")
        records[skill_id] = _skill_pack_capability(
            skill,
            coverage=[item for item in coverage_items if item.get("skill_id") == skill_id],
            quality_scan_present=scan_present,
        )
    if not active and not scan_present:
        records["debloat-repository"]["quality_runner"]["gaps"].append(
            "No active Quality Runner skill packs were supplied; only the native debloat adapter is represented."
        )
    return [records[key] for key in sorted(records)]


def build_skill_capability_feed(quality_scan: dict[str, Any]) -> dict[str, Any]:
    """Create the file consumed by Pronto's Skills analysis surface."""

    if not isinstance(quality_scan, dict):
        raise ValueError("quality scan must be a JSON object")
    capabilities = quality_scan.get("skill_capabilities")
    if not isinstance(capabilities, list):
        capabilities = build_skill_capabilities(
            quality_skills=quality_scan.get("quality_skills"),
            skill_coverage=quality_scan.get("skill_coverage"),
            findings=quality_scan.get("findings"),
            quality_scan=quality_scan,
        )
    return {
        "schema": CAPABILITY_SCHEMA,
        "generated_at": _now(),
        "source": "Quality Runner code-quality scan",
        "run_id": quality_scan.get("run_id") if isinstance(quality_scan.get("run_id"), str) else None,
        "status": "report_only",
        "skills": capabilities,
        "gaps": [
            "Capability records describe representation and evidence; they do not certify remediation completion."
        ],
    }


def load_quality_scan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("quality scan must be a JSON object")
    return payload


def write_skill_capability_feed(quality_scan: dict[str, Any], output: Path) -> dict[str, Any]:
    payload = build_skill_capability_feed(quality_scan)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "written", "path": str(output), "feed": payload}
