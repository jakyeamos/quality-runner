from __future__ import annotations

from typing import Any


def build_adoption_stage(
    *,
    findings: list[dict[str, Any]],
    missing_gates: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    if not findings:
        return {
            "id": "phase-0-clean-baseline",
            "title": "Clean baseline",
            "rationale": "No remediation slices are required for this run.",
        }
    if missing_gates:
        return {
            "id": "phase-1-capability-gates",
            "title": "Capability gates",
            "rationale": "Add or repair repo-owned quality commands before structural cleanup.",
        }
    if warnings:
        return {
            "id": "phase-2-scanner-scope",
            "title": "Scanner scope",
            "rationale": (
                "Resolve discovery or scope warnings before treating structural findings as product debt."
            ),
        }

    structural_findings = [
        finding for finding in findings if finding["category"].startswith("structural:")
    ]
    structural_score = sum(
        finding["score"] for finding in structural_findings if isinstance(finding["score"], int)
    )
    if len(structural_findings) >= 10 or structural_score >= 250:
        return {
            "id": "phase-4-debt-classification",
            "title": "Debt classification",
            "rationale": (
                "Structural findings are broad enough to classify and roadmap before attempting "
                "a clean-run branch."
            ),
            "structural_finding_groups": len(structural_findings),
            "structural_score": structural_score,
        }
    if structural_findings:
        return {
            "id": "phase-3-high-signal-findings",
            "title": "High-signal findings",
            "rationale": "Address a small, reviewable set of structural findings, then rerun QR.",
            "structural_finding_groups": len(structural_findings),
            "structural_score": structural_score,
        }
    return {
        "id": "phase-5-refactor-roadmap",
        "title": "Refactor roadmap",
        "rationale": "Remaining findings are non-gate work that should become planned follow-up.",
    }


def handoff_adoption_stage(remediation_plan: dict[str, Any]) -> dict[str, Any]:
    adoption_stage = remediation_plan.get("adoption_stage")
    if not isinstance(adoption_stage, dict):
        return {
            "id": "phase-5-refactor-roadmap",
            "title": "Refactor roadmap",
            "rationale": "Remediation plan did not include adoption-stage metadata.",
        }
    stage_id = adoption_stage.get("id")
    title = adoption_stage.get("title")
    rationale = adoption_stage.get("rationale")
    if not (
        isinstance(stage_id, str)
        and stage_id
        and isinstance(title, str)
        and title
        and isinstance(rationale, str)
        and rationale
    ):
        return {
            "id": "phase-5-refactor-roadmap",
            "title": "Refactor roadmap",
            "rationale": "Remediation plan adoption-stage metadata was incomplete.",
        }
    return dict(adoption_stage)


def stopping_criteria(adoption_stage: dict[str, Any]) -> list[str]:
    stage_id = adoption_stage.get("id")
    if stage_id == "phase-0-clean-baseline":
        return ["Stop after recording the clean baseline; no remediation branch is needed."]
    if stage_id == "phase-1-capability-gates":
        return [
            "Stop after missing repo-owned gates are added and verified.",
            "Do not chase broad structural findings in the same branch.",
        ]
    if stage_id == "phase-2-scanner-scope":
        return [
            "Stop after generated, vendored, or operational paths are scoped correctly.",
            "Do not disable whole structural rule groups merely to make QR green.",
        ]
    if stage_id == "phase-3-high-signal-findings":
        return [
            "Stop after a small reviewable set of high-signal fixes is committed.",
            "If broad structural debt remains, classify it instead of expanding the branch.",
        ]
    if stage_id == "phase-4-debt-classification":
        return [
            "Stop after documenting broad structural debt and representative buckets.",
            "Convert remaining work into future refactor phases instead of attempting one-shot cleanup.",
        ]
    return [
        "Stop after converting remaining work into an owner-reviewed roadmap.",
        "Do not treat a mature repo as failed solely because it is not QR-clean in one pass.",
    ]


def adoption_stage_markdown(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["- unavailable"]
    stage_id = value.get("id")
    title = value.get("title")
    rationale = value.get("rationale")
    if not (
        isinstance(stage_id, str)
        and stage_id
        and isinstance(title, str)
        and title
        and isinstance(rationale, str)
        and rationale
    ):
        return ["- unavailable"]
    lines = [
        f"- ID: {stage_id}",
        f"- Title: {title}",
        f"- Rationale: {rationale}",
    ]
    structural_groups = value.get("structural_finding_groups")
    structural_score = value.get("structural_score")
    if isinstance(structural_groups, int):
        lines.append(f"- Structural finding groups: {structural_groups}")
    if isinstance(structural_score, int):
        lines.append(f"- Structural score: {structural_score}")
    return lines
