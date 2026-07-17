from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.phase_planning import add_phase, initialize_plan, plan_phase
from quality_runner.phase_sources import load_planning_source
from quality_runner.phase_store import load_roadmap
from quality_runner.remediation_domains import DOMAIN_ORDER
from quality_runner.schema_constants import PHASE_RESULT_SCHEMA


def auto_plan(
    repo_root: Path,
    *,
    run_id: str | None = None,
    handoff_json: Path | None = None,
) -> dict[str, Any]:
    """Materialize every QR domain candidate as a security-first native phase."""

    initialization = initialize_plan(repo_root)
    source = load_planning_source(
        repo_root,
        run_id=run_id,
        handoff_json=handoff_json,
    )
    candidates = _ordered_candidates(source.get("slices"))
    if not candidates:
        raise ValueError("planning source contains no remediation candidates")

    roadmap = load_roadmap(repo_root)
    existing_by_candidate = {
        str(phase.get("source_candidate_id")): phase
        for phase in roadmap.get("phases", [])
        if isinstance(phase, dict) and isinstance(phase.get("source_candidate_id"), str)
    }
    phases: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate["id"])
        existing = existing_by_candidate.get(candidate_id)
        if existing is None:
            created = add_phase(
                repo_root,
                str(candidate.get("title") or candidate_id),
                source_candidate_id=candidate_id,
                automatic=True,
            )
            phase = created["phase"]
        else:
            phase = existing
        phase_number = int(phase["number"])
        planned = plan_phase(
            repo_root,
            phase_number=phase_number,
            run_id=run_id,
            handoff_json=handoff_json,
            candidate_id=candidate_id,
        )
        phases.append(
            {
                "number": phase_number,
                "candidate_id": candidate_id,
                "title": phase.get("title"),
                "status": planned.get("status"),
                "plan_count": len(planned.get("plans", [])),
                "source_slice_count": len(candidate.get("slice_ids", []))
                if isinstance(candidate.get("slice_ids"), list)
                else 0,
            }
        )

    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "auto-planned",
        "implementation_allowed": False,
        "planning_mode": "automatic",
        "ordering": "security-first",
        "initialization": initialization,
        "source": source["source"],
        "phases": phases,
    }


def _ordered_candidates(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    indexed = [
        (index, item)
        for index, item in enumerate(value)
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    domain_rank = {domain: index for index, domain in enumerate(DOMAIN_ORDER)}
    indexed.sort(
        key=lambda pair: (
            domain_rank.get(str(pair[1].get("domain")), len(domain_rank)),
            pair[0],
        )
    )
    return [item for _index, item in indexed]
