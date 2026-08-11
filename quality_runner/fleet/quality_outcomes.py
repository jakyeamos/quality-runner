from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quality_runner.fleet.contracts import DIMENSION_LABELS

QUALITY_OUTCOME_TAXONOMY = {
    "checks_failing": {
        "label": "Quality checks failing",
        "meaning": "An observed quality check or non-dynamic blocker failed; this is a failure finding, not a missing-evidence status.",
        "next_step": "Inspect the failing command or blocker finding, correct it, then rerun the owning quality check and fleet audit.",
    },
    "verification_blocked": {
        "label": "Quality verification blocked",
        "meaning": "Setup, execution, timeout, or target provenance prevented a trustworthy verdict; no pass or failure is inferred.",
        "next_step": "Repair the setup or target provenance, then rerun the blocked verification and fleet audit.",
    },
    "review_needed": {
        "label": "Quality review needed",
        "meaning": "No blocker is known, but one or more applicable dimensions remain below ideal, partial, discoverable-only, or unverified.",
        "next_step": "Review the listed dimensions, add or repair repository-owned evidence, then rerun the static audit and selected dynamic verification.",
    },
    "evidence_unknown": {
        "label": "Evidence review required",
        "meaning": "Required evidence is not current or confirmed. This is an evidence gap, not a failed-test result.",
        "next_step": "Identify the listed evidence gaps, reconcile the target branch and commit, then rerun the audit.",
    },
    "healthy": {
        "label": "Quality healthy",
        "meaning": "Verification passed or was safely reused, and all applicable dimensions are maintained with current evidence.",
        "next_step": "Keep the evidence checkpoint current and rerun verification when the target commit or quality contract changes.",
    },
}


def classify_quality_outcome(
    *,
    dynamic_status: str,
    non_dynamic_blockers: int,
    statuses: list[str],
    healthy: bool,
    dimension_gaps: list[Mapping[str, Any]] | None = None,
    blocker_count: int = 0,
) -> dict[str, str]:
    if dynamic_status == "failed" or non_dynamic_blockers:
        state = "checks_failing"
    elif dynamic_status in {"timeout", "blocked"}:
        state = "verification_blocked"
    elif dynamic_status in {"unavailable", "unknown"} or any(
        status in {"unknown", "stale"} for status in statuses
    ):
        state = "evidence_unknown"
    elif healthy:
        state = "healthy"
    else:
        state = "review_needed"
    definition = QUALITY_OUTCOME_TAXONOMY[state]
    gaps = dimension_gaps or []
    if state == "checks_failing":
        blocker_text = (
            f"Observed {blocker_count} blocker finding(s)."
            if blocker_count
            else "An observed quality failure requires repair."
        )
        disposition = f"{blocker_text} Inspect the failing command or finding, then rerun the owning quality check."
    elif state == "verification_blocked":
        disposition = f"No trustworthy verdict was produced because verification is {dynamic_status}. Repair setup or target provenance, then rerun it."
    elif state == "evidence_unknown":
        if gaps:
            details = _gap_details(gaps)
            remaining = len(gaps) - len(details)
            detail_text = _join_details(details)
            remainder_text = f"; plus {remaining} more" if remaining else ""
            disposition = (
                f"Evidence review required. {len(gaps)} evidence dimension(s) are not current or confirmed. "
                f"Priority review: {detail_text}{remainder_text}. "
                "This is an evidence gap, not a failing-test result."
            )
        else:
            disposition = (
                "Evidence review required. Required evidence is not current or confirmed. "
                "Reconcile the target branch and commit, then rerun the audit."
            )
    elif state == "review_needed":
        if gaps:
            details = _gap_details(gaps)
            remaining = len(gaps) - len(details)
            detail_text = _join_details(details)
            remainder_text = f"; plus {remaining} more" if remaining else ""
            disposition = (
                f"No blocker was observed. {len(gaps)} below-ideal dimension(s) remain. "
                f"Priority review: {detail_text}{remainder_text}. "
                "This is a review state, not a failing-test result."
            )
        else:
            disposition = (
                "No blocker was observed, but the repository is not yet fully verified. "
                "Review the available evidence and rerun the static audit."
            )
    else:
        disposition = definition["meaning"]
    return {
        "state": state,
        "label": definition["label"],
        "disposition": disposition,
        "next_step": definition["next_step"],
    }


_GAP_STATUS_PRIORITY = {
    "blocked": 0,
    "unknown": 1,
    "stale": 1,
    "missing": 2,
    "absent": 3,
    "static_gaps": 4,
    "untracked": 5,
    "attention": 6,
    "discoverable": 7,
    "prose_only": 8,
}


def _gap_details(gaps: list[Mapping[str, Any]], limit: int = 3) -> list[str]:
    ranked = sorted(
        gaps,
        key=lambda gap: (
            _GAP_STATUS_PRIORITY.get(str(gap.get("status", "")).strip(), 9),
            _score_value(gap.get("score")),
            str(gap.get("dimension", "")),
        ),
    )
    details: list[str] = []
    for gap in ranked[:limit]:
        dimension = str(gap.get("dimension", "")).strip()
        if not dimension:
            continue
        label = _dimension_label(dimension)
        status = str(gap.get("status", "unknown")).strip() or "unknown"
        status = _display_gap_status(status)
        score = gap.get("score")
        score_text = _score_text(score)
        message = " ".join(str(gap.get("message", "Evidence is incomplete.")).split()).rstrip(" .")
        if len(message) > 160:
            message = f"{message[:157].rstrip(' .')}..."
        details.append(f"{label} [{status}, score {score_text}]: {message}")
    return details


def _score_value(score: Any) -> float:
    if score is None:
        return 99.0
    try:
        return float(score)
    except (TypeError, ValueError):
        return 99.0


def _dimension_label(dimension: str) -> str:
    return DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").replace(".", " "))


def _display_gap_status(status: str) -> str:
    return {
        "unknown": "not confirmed",
    }.get(status, status)


def _score_text(score: Any) -> str:
    if score is None:
        return "n/a"
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return str(score)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)


def _join_details(details: list[str]) -> str:
    if len(details) <= 1:
        return details[0] if details else "the listed below-ideal dimensions"
    if len(details) == 2:
        return f"{details[0]} and {details[1]}"
    return f"{'; '.join(details[:-1])}; and {details[-1]}"


def _join_labels(labels: list[str]) -> str:
    if len(labels) <= 1:
        return labels[0] if labels else "one or more required dimensions"
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


def quality_outcome_counts(projections: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for projection in projections:
        outcome = projection.get("quality_outcome")
        state = (
            str(outcome.get("state", "evidence_unknown"))
            if isinstance(outcome, Mapping)
            else "evidence_unknown"
        )
        counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))
