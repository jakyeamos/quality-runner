from __future__ import annotations

from typing import Any

from quality_runner.fleet import audit_coverage
from quality_runner.fleet.agent_usability_scoring import applicable_agent_usability_scores
from quality_runner.fleet.contracts import DIMENSIONS, digest, standard_dimensions


def build_fleet_summary(
    *,
    audit_id: str,
    as_of: str,
    repositories: list[dict[str, Any]],
    dynamic: bool,
    changed_only: bool,
    standard: str | None = None,
    population_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_standard_dimensions = standard_dimensions(standard)
    selected_dimensions = selected_standard_dimensions or DIMENSIONS
    dimension_scores: dict[str, list[float]] = {dimension: [] for dimension in selected_dimensions}
    finding_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    dynamic_counts = {
        key: 0
        for key in (
            "selected",
            "reused",
            "passed",
            "failed",
            "blocked",
            "unavailable",
            "timeout",
            "unknown",
            "not_applicable",
            "not_selected",
        )
    }
    unresolved: list[str] = []
    coverage = audit_coverage.summarize_audit_coverage(repositories)
    unresolved.extend(coverage["gaps"])
    for result in repositories:
        dynamic_result = result.get("dynamic")
        dynamic_state = (
            str(dynamic_result.get("status", "unknown"))
            if isinstance(dynamic_result, dict)
            else "unknown"
        )
        for finding in result.get("findings", []):
            status = str(finding.get("status", "unknown"))
            finding_counts[status] = finding_counts.get(status, 0) + 1
            priority = str(finding.get("priority", "P2"))
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
            score = finding.get("score")
            dimension = finding.get("dimension")
            if selected_standard_dimensions and dimension not in selected_standard_dimensions:
                continue
            if isinstance(score, int | float) and isinstance(dimension, str) and score >= 0:
                dimension_scores.setdefault(dimension, []).append(float(score))
            if _is_unresolved_measurement(finding):
                unresolved.append(f"{result.get('repo_id')}:{dimension}:{status}")
        for score_record in (
            applicable_agent_usability_scores(result.get("agent_usability"))
            if standard is None
            else []
        ):
            dimension = str(score_record["dimension"])
            status = str(score_record["status"])
            dimension_scores.setdefault(dimension, []).append(float(score_record["score"]))
        if isinstance(dynamic_result, dict):
            state = dynamic_state
            if dynamic_result.get("selected") is True:
                dynamic_counts["selected"] += 1
            if state == "reused":
                dynamic_counts["reused"] += 1
            elif state == "passed":
                dynamic_counts["passed"] += 1
            elif state == "failed":
                dynamic_counts["failed"] += 1
            elif state == "blocked":
                dynamic_counts["blocked"] += 1
            elif state == "unavailable":
                dynamic_counts["unavailable"] += 1
            elif state == "timeout":
                dynamic_counts["timeout"] += 1
            elif state == "unknown":
                dynamic_counts["unknown"] += 1
            elif state == "not_applicable":
                dynamic_counts["not_applicable"] += 1
            elif state == "not_selected":
                dynamic_counts["not_selected"] += 1
    all_scores = [score for scores in dimension_scores.values() for score in scores]
    means = {
        dimension: round(sum(scores) / len(scores), 3) if scores else None
        for dimension, scores in sorted(dimension_scores.items())
    }
    stable_repositories = sorted(repositories, key=lambda item: str(item.get("repo_id", "")))
    resolved_population = population_coverage or {
        "status": "bounded",
        "source": "unspecified",
        "expected_repository_count": len(repositories),
        "observed_repository_count": len(repositories),
        "excluded_repository_count": 0,
    }
    unresolved_gaps = sorted(set(unresolved))
    confidence, confidence_basis, confidence_limitations = _measurement_confidence(
        repository_count=len(repositories),
        static_completed=len(repositories),
        dynamic=dynamic,
        changed_only=changed_only,
        dynamic_counts=dynamic_counts,
        unresolved_gaps=unresolved_gaps,
        population_coverage=resolved_population,
    )
    summary = {
        "schema": "quality-runner-fleet-summary-v0.1",
        "status": "completed",
        "audit_id": audit_id,
        "as_of": as_of,
        "repository_count": len(repositories),
        "checkout_count": sum(
            int(item.get("repository", {}).get("checkout_count", 0)) for item in repositories
        ),
        "static_completed": len(repositories),
        **coverage["summary"],
        "dynamic_policy": {"enabled": dynamic, "changed_only": changed_only},
        "dynamic_selected": dynamic_counts["selected"],
        "dynamic_reused": dynamic_counts["reused"],
        "dynamic_passed": dynamic_counts["passed"],
        "dynamic_failed": dynamic_counts["failed"],
        "dynamic_blocked": dynamic_counts["blocked"],
        "dynamic_unavailable": dynamic_counts["unavailable"],
        "dynamic_timeout": dynamic_counts["timeout"],
        "dynamic_unknown": dynamic_counts["unknown"],
        "dynamic_not_applicable": dynamic_counts["not_applicable"],
        "dynamic_not_selected": dynamic_counts["not_selected"],
        "mean_maturity": round(sum(all_scores) / len(all_scores), 3) if all_scores else None,
        "dimension_means": means,
        "finding_counts": dict(sorted(finding_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "sample_size": {
            "repositories": len(repositories),
            "applicable_dimension_scores": len(all_scores),
        },
        "confidence": confidence,
        "confidence_basis": confidence_basis,
        "confidence_limitations": confidence_limitations,
        "population_coverage": resolved_population,
        "unresolved_measurement_gaps": unresolved_gaps,
        "methodology": {
            "rubric": (
                "0 unknown, 1 ad hoc, 2 defined, 3 enforced, 4 newcomer verified"
                if standard == "developer-legibility"
                else "0 absent, 1 informal, 2 discoverable, 3 executable/currently validated, 4 maintained/routed/automatically checked"
            ),
            "unknown_evidence_is_not_green": True,
            "not_applicable_requires_bounded_evidence": True,
            "dynamic_scope": (
                "every eligible repository"
                if dynamic and not changed_only
                else "changed, new, dirty, priority, stale, failed, or incomplete evidence only"
            ),
            "target_branch_policy": "explicit override, dev, documented fallback, locally verified remote default, or sole local branch; no maturity-based branch selection",
            "audit_coverage_policy": "canonical findings remain exact-target evidence; unfolded branches, detached commits, and dirty worktrees qualify comparison and publication readiness",
            "source_checkouts_modified": False,
        },
        "provenance_hash": digest(
            {
                "audit_id": audit_id,
                "as_of": as_of,
                "repositories": [
                    item.get("static_provenance_hash") for item in stable_repositories
                ],
                "dynamic": [item.get("dynamic") for item in stable_repositories],
                "population_coverage": resolved_population,
                "audit_coverage": coverage["provenance"],
                **({"standard": standard} if standard is not None else {}),
            }
        ),
    }
    if standard is not None:
        summary["standard"] = standard
        summary["methodology"]["standard_scope"] = (
            f"Only the {standard!r} standard was assessed; this snapshot is not a complete "
            "fleet maturity verdict."
        )
    return summary


def _is_unresolved_measurement(finding: dict[str, Any]) -> bool:
    """Separate unknown measurement from a conclusively low maturity result."""

    if finding.get("applicable") is False or finding.get("status") == "not_applicable":
        return False
    score = finding.get("score")
    return not isinstance(score, int | float) or isinstance(score, bool) or score < 0


def _measurement_confidence(
    *,
    repository_count: int,
    static_completed: int,
    dynamic: bool,
    changed_only: bool,
    dynamic_counts: dict[str, int],
    unresolved_gaps: list[str],
    population_coverage: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    if repository_count == 0:
        return "low", [], ["empty_repository_population"]

    basis: list[str] = []
    limitations: list[str] = []
    expected_count = int(population_coverage.get("expected_repository_count", 0))
    observed_count = int(population_coverage.get("observed_repository_count", 0))
    if (
        population_coverage.get("status") == "complete"
        and expected_count == repository_count
        and observed_count == repository_count
    ):
        basis.append("complete_population")
    else:
        limitations.append("population_not_attested_complete")

    if static_completed == repository_count:
        basis.append("complete_static_scan")
    else:
        limitations.append("static_scan_incomplete")

    conclusive_dynamic_count = sum(
        dynamic_counts[state] for state in ("reused", "passed", "failed", "not_applicable")
    )
    if dynamic and not changed_only and conclusive_dynamic_count == repository_count:
        basis.append("complete_dynamic_verification")
    else:
        if not dynamic:
            limitations.append("dynamic_verification_disabled")
        elif changed_only:
            limitations.append("dynamic_verification_changed_only")
        if conclusive_dynamic_count != repository_count:
            limitations.append("dynamic_verification_incomplete")

    if unresolved_gaps:
        limitations.append("unresolved_measurement_gaps")
    else:
        basis.append("no_unresolved_measurement_gaps")

    return ("high" if not limitations else "medium"), basis, limitations
