from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

DOMAIN_ORDER = (
    "security",
    "publication-visibility",
    "data-integrity",
    "quality-gates",
    "testing-quality",
    "release-readiness",
    "ui-quality",
    "performance",
    "architecture-maintainability",
    "developer-experience",
    "integration-decisions",
    "general-quality",
)

DOMAIN_TITLES = {
    "security": "Security and trust boundaries",
    "publication-visibility": "Publication, visibility, and content boundaries",
    "data-integrity": "Data integrity and state transitions",
    "quality-gates": "Quality gates and test infrastructure",
    "testing-quality": "Testing and regression confidence",
    "release-readiness": "Release readiness and change risk",
    "ui-quality": "UI foundations and interaction quality",
    "performance": "Performance and resource behavior",
    "architecture-maintainability": "Architecture and maintainability",
    "developer-experience": "Developer experience and workflow",
    "integration-decisions": "Integration and scope decisions",
    "general-quality": "General quality improvements",
}

_DOMAIN_RANK = {domain: index for index, domain in enumerate(DOMAIN_ORDER)}
_MAX_REPRESENTATIVE_SLICES = 8
_MAX_REPRESENTATIVE_PATHS = 12
_MAX_VERIFICATION_GATES = 16


def annotate_remediation_slices(slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach deterministic domain metadata without changing slice semantics."""

    annotated: list[dict[str, Any]] = []
    for slice_item in slices:
        item = dict(slice_item)
        domain, workstream = classify_remediation_slice(item)
        item["domain"] = domain
        item["workstream"] = workstream
        annotated.append(item)
    return annotated


def classify_remediation_slice(slice_item: dict[str, Any]) -> tuple[str, str]:
    categories = _categories(slice_item)
    text = _slice_text(slice_item)
    skill_ids = _skill_ids(categories)

    if _contains_publication_surface(text):
        return "publication-visibility", "publication-boundaries"
    if any(category.startswith("security:") for category in categories):
        if any(category.startswith("security:agent-review") for category in categories):
            return "security", "security-review"
        return "security", _security_workstream(categories)

    for skill_id in skill_ids:
        domain = _domain_for_skill(skill_id)
        if domain is not None:
            return domain, skill_id

    structural_categories = {
        category.removeprefix("structural:")
        for category in categories
        if category.startswith("structural:")
    }
    if "integrate" in structural_categories:
        return "integration-decisions", "integration-disposition"
    if "improve-tests" in structural_categories:
        return "testing-quality", "test-coverage"
    if "ui_structural" in structural_categories:
        return "ui-quality", "ui-structure"
    if "speed" in structural_categories:
        return "performance", "performance-hotspots"
    if "harden" in structural_categories:
        return "security", "boundary-hardening"
    if structural_categories & {"simplify", "deduplicate", "ponytail", "clarify"}:
        return "architecture-maintainability", "complexity-reduction"

    if "capability" in categories or "readiness" in categories:
        return "quality-gates", "missing-capabilities"
    if any(category.startswith("release") for category in categories):
        return "release-readiness", "release-evidence"
    if any(category.startswith("data") for category in categories):
        return "data-integrity", "data-state"
    if any(category.startswith("test") for category in categories):
        return "testing-quality", "test-confidence"
    if any(category.startswith("performance") for category in categories):
        return "performance", "runtime-behavior"
    if any(category.startswith("developer") for category in categories):
        return "developer-experience", "workflow"
    if any(category.startswith("architecture") for category in categories):
        return "architecture-maintainability", "architecture"
    return "general-quality", "unclassified"


def build_phase_candidates(
    slices: list[dict[str, Any]],
    *,
    security_review_slices: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build domain-level phase candidates while retaining every leaf slice id."""

    all_slices = [*slices, *(security_review_slices or [])]
    groups: dict[str, list[dict[str, Any]]] = {}
    for slice_item in all_slices:
        domain = str(slice_item.get("domain") or "general-quality")
        groups.setdefault(domain, []).append(slice_item)

    candidates = [_build_candidate(domain, group) for domain, group in groups.items()]
    candidates.sort(key=_candidate_sort_key)
    return candidates


def phase_candidate_summaries(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact handoff summaries; the full candidates remain in the plan artifact."""

    summary_fields = (
        "id",
        "domain",
        "title",
        "priority",
        "slice_count",
        "finding_count",
        "score",
        "requires_review",
        "review_slice_count",
        "workstreams",
        "representative_slice_ids",
        "representative_paths",
        "actions",
        "verification_gates",
        "verification_modes",
        "disposition_groups",
        "bulk_review_eligible_count",
        "status",
    )
    return [
        {key: candidate[key] for key in summary_fields if key in candidate}
        for candidate in candidates
    ]


def _build_candidate(domain: str, slices: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(slices, key=_slice_sort_key)
    finding_items = _unique_findings(ordered)
    finding_ids = [str(finding["id"]) for finding in finding_items]
    slice_ids = [str(item["id"]) for item in ordered if isinstance(item.get("id"), str)]
    priority = _aggregate_priority(ordered)
    workstreams = Counter(
        str(item.get("workstream"))
        for item in ordered
        if isinstance(item.get("workstream"), str) and item["workstream"]
    )
    disposition_groups = Counter(
        str(finding.get("disposition_group"))
        for finding in finding_items
        if isinstance(finding.get("disposition_group"), str)
    )
    verification_gates = _unique_strings(
        gate
        for item in ordered
        for gate in item.get("verification_gates", [])
        if isinstance(gate, str) and gate
    )
    verification_modes = sorted(
        {
            str(item["verification_mode"])
            for item in ordered
            if item.get("verification_mode") in {"command", "evidence"}
        }
    )
    representative_slice_ids = slice_ids[:_MAX_REPRESENTATIVE_SLICES]
    representative_paths = _representative_paths(ordered)
    requires_review = any(_slice_requires_review(item) for item in ordered)
    score = sum(
        int(item.get("score") or 0) for item in ordered if isinstance(item.get("score"), int)
    )
    truncated_gate_count = max(0, len(verification_gates) - _MAX_VERIFICATION_GATES)
    visible_gates = verification_gates[:_MAX_VERIFICATION_GATES]
    if truncated_gate_count:
        visible_gates.append(
            f"Review the remaining {truncated_gate_count} domain-specific verification gates in the leaf slices."
        )

    actions = [
        (
            f"Break this domain into bounded work items using the {len(slice_ids)} linked leaf slices; "
            "preserve the leaf scope and evidence references."
        ),
        "Resolve higher-priority findings before lower-priority cleanup within this domain.",
        "Rerun quality-runner and compare the resolution ledger for this domain after each bounded batch.",
    ]
    if requires_review:
        actions.insert(
            0,
            "Resolve the linked human or external-evidence review items before treating this domain as complete.",
        )
    if disposition_groups:
        actions.insert(
            1,
            "Review disposition groups in bulk; escalate only slices marked human-review or exceptions.",
        )

    return {
        "id": f"phase-{_slug(domain)}",
        "domain": domain,
        "title": DOMAIN_TITLES.get(domain, domain.replace("-", " ").title()),
        "priority": priority,
        "status": "review-required" if requires_review else "planned",
        "requires_review": requires_review,
        "review_slice_count": sum(1 for item in ordered if _slice_requires_review(item)),
        "slice_count": len(slice_ids),
        "finding_count": len(finding_items),
        "score": score,
        "slice_ids": slice_ids,
        "finding_ids": finding_ids,
        "finding_fingerprints": _finding_fingerprints(finding_items),
        "workstreams": [name for name, _ in sorted(workstreams.items())],
        "workstream_counts": dict(sorted(workstreams.items())),
        "representative_slice_ids": representative_slice_ids,
        "representative_paths": representative_paths,
        "actions": actions,
        "verification_gates": visible_gates,
        "verification_gate_count": len(verification_gates),
        "verification_gate_truncated": bool(truncated_gate_count),
        "verification_modes": verification_modes,
        "disposition_groups": dict(sorted(disposition_groups.items())),
        "bulk_review_eligible_count": sum(
            1
            for item in ordered
            for finding in item.get("findings", [])
            if isinstance(finding, dict)
            and finding.get("disposition_class") == "bulk-review-eligible"
        ),
    }


def _categories(slice_item: dict[str, Any]) -> list[str]:
    findings = slice_item.get("findings")
    if not isinstance(findings, list):
        return []
    return sorted(
        {
            str(finding["category"]).lower()
            for finding in findings
            if isinstance(finding, dict)
            and isinstance(finding.get("category"), str)
            and finding["category"]
        }
    )


def _slice_text(slice_item: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("id", "title", "actions", "verification_gates"):
        value = slice_item.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(item for item in value if isinstance(item, str))
    findings = slice_item.get("findings")
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            for key in ("category", "summary", "actionability"):
                value = finding.get(key)
                if isinstance(value, str):
                    values.append(value)
    return " ".join(values).lower()


def _skill_ids(categories: list[str]) -> list[str]:
    return sorted(
        {
            category.removeprefix("skill:").removeprefix("structural:skill:")
            for category in categories
            if category.startswith("skill:") or category.startswith("structural:skill:")
        }
    )


def _domain_for_skill(skill_id: str) -> str | None:
    if skill_id in {"security-privacy", "pr-risk"}:
        return "security" if skill_id == "security-privacy" else "release-readiness"
    if skill_id == "data-integrity":
        return "data-integrity"
    if skill_id == "test-strategy":
        return "testing-quality"
    if skill_id == "release-readiness":
        return "release-readiness"
    if skill_id in {"ui-foundations", "ui-specificity", "motion-quality", "copy-specificity"}:
        return "ui-quality"
    if skill_id == "performance-readiness":
        return "performance"
    if skill_id == "architecture-maintainability":
        return "architecture-maintainability"
    if skill_id == "developer-experience":
        return "developer-experience"
    return None


def _security_workstream(categories: list[str]) -> str:
    suffixes = [category.partition(":")[2] for category in categories if ":" in category]
    if any("secret" in suffix for suffix in suffixes):
        return "secrets-and-provenance"
    if any(
        keyword in suffix for suffix in suffixes for keyword in ("redirect", "webhook", "media")
    ):
        return "public-boundaries"
    if any("sink" in suffix or "eval" in suffix for suffix in suffixes):
        return "unsafe-sinks"
    return "security-controls"


def _contains_publication_surface(text: str) -> bool:
    return any(
        re.search(pattern, text)
        for pattern in (
            r"\bpublish(?:ed|ing)?\b",
            r"\bvisibility\b",
            r"\braw\s+(?:html|content)\b",
            r"\bpublic/private\b",
            r"\bmedia\s+access\b",
            r"\bdraft\b",
        )
    )


def _unique_findings(slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for slice_item in slices:
        findings = slice_item.get("findings")
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_id = finding.get("id")
            if isinstance(finding_id, str) and finding_id and finding_id not in by_id:
                by_id[finding_id] = dict(finding)
    return [by_id[finding_id] for finding_id in sorted(by_id)]


def _finding_fingerprints(findings: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(finding["fingerprint"])
            for finding in findings
            if isinstance(finding.get("fingerprint"), str) and finding["fingerprint"]
        }
    )


def _unique_strings(values: Iterable[object]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _representative_paths(slices: list[dict[str, Any]]) -> list[str]:
    paths: Counter[str] = Counter()
    for slice_item in slices:
        findings = slice_item.get("findings")
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                for key in ("file", "path"):
                    value = finding.get(key)
                    if isinstance(value, str) and value:
                        paths[value] += 1
        scope = slice_item.get("scope")
        if isinstance(scope, dict):
            in_scope = scope.get("in_scope")
            if isinstance(in_scope, list):
                for value in in_scope:
                    if isinstance(value, str) and value and "/" in value:
                        paths[value] += 1
    return [path for path, _ in sorted(paths.items(), key=lambda item: (-item[1], item[0]))][
        :_MAX_REPRESENTATIVE_PATHS
    ]


def _slice_requires_review(slice_item: dict[str, Any]) -> bool:
    if slice_item.get("disposition_required") is True:
        return True
    findings = slice_item.get("findings")
    if not isinstance(findings, list):
        return False
    return any(
        isinstance(finding, dict)
        and (
            finding.get("actionability") == "needs-author-decision"
            or str(finding.get("category") or "").startswith("security:agent-review")
        )
        for finding in findings
    )


def _aggregate_priority(slices: list[dict[str, Any]]) -> str:
    priorities = [str(item.get("priority")) for item in slices]
    return min(
        priorities, key=lambda priority: {"high": 0, "medium": 1, "low": 2}.get(priority, 99)
    )


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, str]:
    priority = {"high": 0, "medium": 1, "low": 2}.get(str(candidate.get("priority")), 99)
    return (
        _DOMAIN_RANK.get(str(candidate.get("domain")), len(_DOMAIN_RANK)),
        priority,
        -int(candidate.get("score") or 0),
        str(candidate.get("id") or ""),
    )


def _slice_sort_key(slice_item: dict[str, Any]) -> tuple[int, int, str]:
    priority = {"high": 0, "medium": 1, "low": 2}.get(str(slice_item.get("priority")), 99)
    score = slice_item.get("score")
    return priority, -(score if isinstance(score, int) else 0), str(slice_item.get("id") or "")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower() or "general-quality"
