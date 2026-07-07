from __future__ import annotations

from typing import Any

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
EFFORT_POINTS = {"S": 1, "M": 2, "L": 3}
FIX_RISK_POINTS = {"LOW": 1, "MED": 2, "HIGH": 3}
IMPACT_POINTS = {"low": 1, "medium": 3, "high": 5}

_CATEGORY_IMPACT: dict[str, str] = {
    "capability": "Missing gates block merge readiness and hide regressions.",
    "standard": "Standards drift increases review friction and toolchain mismatch risk.",
    "structural:harden": "Type and safety gaps increase review cost and defect risk.",
    "structural:simplify": "Complex control flow raises change risk and review time.",
    "structural:integrate": "Unwired work creates false completeness and surprise breakage.",
    "structural:deduplicate": "Duplicate logic drifts across fixes and doubles maintenance.",
    "structural:speed": "Sequential async work can become a latency bottleneck.",
    "security:": "Security findings affect safety and gate reliability.",
}


def compute_finding_quality(
    finding: dict[str, Any],
    *,
    raw_findings: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    confidence = _confidence_label(finding, raw_findings=raw_findings)
    effort = _effort_label(finding, raw_findings=raw_findings)
    fix_risk = _fix_risk_label(finding, raw_findings=raw_findings)
    impact = _impact_text(finding, raw_findings=raw_findings)
    why_now = _why_now(finding, raw_findings=raw_findings)
    return {
        "impact": impact,
        "effort": effort,
        "fix_risk": fix_risk,
        "confidence": confidence,
        "why_now": why_now,
    }


def compute_leverage(quality: dict[str, str]) -> dict[str, Any]:
    impact = IMPACT_POINTS.get(_impact_level(quality.get("impact", "")), 2)
    effort = EFFORT_POINTS.get(str(quality.get("effort", "M")), 2)
    confidence = CONFIDENCE_RANK.get(str(quality.get("confidence", "medium")).lower(), 2)
    fix_risk = FIX_RISK_POINTS.get(str(quality.get("fix_risk", "MED")), 2)
    rank = round((impact / effort) * (confidence / 3) * (1 / fix_risk), 2)
    return {
        "impact": impact,
        "effort": effort,
        "confidence": confidence,
        "fix_risk": fix_risk,
        "rank": rank,
        "explanation": _leverage_explanation(quality, rank),
    }


def _confidence_label(
    finding: dict[str, Any],
    *,
    raw_findings: list[dict[str, Any]] | None,
) -> str:
    if raw_findings:
        return _mode_confidence(raw_findings)
    value = finding.get("confidence")
    if isinstance(value, str) and value.lower() in CONFIDENCE_RANK:
        return value.upper() if value.isupper() else value.capitalize()
    severity = str(finding.get("severity") or "")
    if severity in {"critical", "blocker"}:
        return "High"
    return "Medium"


def _effort_label(
    finding: dict[str, Any],
    *,
    raw_findings: list[dict[str, Any]] | None,
) -> str:
    count = len(raw_findings) if raw_findings else 1
    category = str(finding.get("category") or "")
    if category == "capability":
        return "M"
    if category.startswith("structural:") and count >= 8:
        return "L"
    if count >= 4:
        return "M"
    return "S"


def _fix_risk_label(
    finding: dict[str, Any],
    *,
    raw_findings: list[dict[str, Any]] | None,
) -> str:
    if raw_findings:
        risks = [_risk_points(item.get("risk")) for item in raw_findings if item.get("risk")]
        if risks and max(risks) >= 3:
            return "HIGH"
        if risks and max(risks) >= 2:
            return "MED"
    category = str(finding.get("category") or "")
    if category.startswith("structural:integrate"):
        return "HIGH"
    if category.startswith("structural:"):
        return "MED"
    if category == "capability":
        return "LOW"
    return "MED"


def _impact_text(
    finding: dict[str, Any],
    *,
    raw_findings: list[dict[str, Any]] | None,
) -> str:
    category = str(finding.get("category") or "")
    for prefix, text in _CATEGORY_IMPACT.items():
        if category == prefix or category.startswith(prefix):
            base = text
            break
    else:
        base = "This finding affects review cost, safety, or gate reliability."
    score = finding.get("score")
    count = len(raw_findings) if raw_findings else None
    parts = [base]
    if isinstance(score, int) and score:
        parts.append(f"Aggregate score {score}.")
    if isinstance(count, int) and count > 1:
        parts.append(f"{count} related rows in this group.")
    return " ".join(parts)


def _why_now(
    finding: dict[str, Any],
    *,
    raw_findings: list[dict[str, Any]] | None,
) -> str:
    severity = str(finding.get("severity") or "")
    category = str(finding.get("category") or "")
    if severity in {"critical", "blocker"}:
        return "Blocker-class finding should be handled before broader cleanup."
    if category.startswith("security:"):
        return "Security findings should be triaged before cosmetic structural work."
    if category == "capability":
        return "Gate gaps block trustworthy verification for later slices."
    if raw_findings and len(raw_findings) >= 5:
        return "Cluster size makes this a high-leverage batch once gates are stable."
    return "Focused remediation with machine-checkable verification."


def _mode_confidence(raw_findings: list[dict[str, Any]]) -> str:
    weights: dict[str, int] = {}
    for finding in raw_findings:
        confidence = str(finding.get("confidence") or "medium").lower()
        score = int(finding.get("score") or 1)
        weights[confidence] = weights.get(confidence, 0) + score
    if not weights:
        return "Medium"
    winner = max(weights, key=lambda key: weights[key])
    return winner.capitalize()


def _risk_points(risk: object) -> int:
    if not isinstance(risk, str):
        return 1
    lowered = risk.lower()
    if any(term in lowered for term in ("injection", "secret", "unsafe", "critical")):
        return 3
    if any(term in lowered for term in ("regress", "behavior", "api", "public")):
        return 2
    return 1


def _impact_level(impact: str) -> str:
    lowered = impact.lower()
    if any(term in lowered for term in ("block", "security", "safety", "defect")):
        return "high"
    if any(term in lowered for term in ("review", "friction", "maintenance")):
        return "medium"
    return "low"


def _leverage_explanation(quality: dict[str, str], rank: float) -> str:
    effort = quality.get("effort", "M")
    confidence = quality.get("confidence", "Medium")
    if rank >= 2:
        return f"High-leverage slice with {confidence.lower()} confidence and effort {effort}."
    if rank >= 1:
        return f"Moderate leverage with focused verification and effort {effort}."
    return "Lower leverage; handle after blockers unless verification is trivial."
