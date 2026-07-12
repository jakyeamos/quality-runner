from __future__ import annotations

from collections.abc import Mapping

from quality_runner.application.review_v1_serializers import REVIEW_MANIFEST_SCHEMA
from quality_runner.core.review_contracts import ReviewManifest, ReviewPacket


def build_review_manifest(
    context: ReviewPacket, *, artifact_paths: Mapping[str, str]
) -> ReviewManifest:
    freshness = context["freshness"]
    return {
        "schema": REVIEW_MANIFEST_SCHEMA,
        "run_id": context["run_id"],
        "mode": context["mode"],
        "scope": context["scope"],
        "breadth": context["breadth"],
        "exclusions": list(context["exclusions"]),
        "evidence_references": list(context["evidence"]),
        "freshness": {
            "new_invocation_required": freshness["new_invocation_required"],
            "prior_review_context_included": freshness["prior_review_context_included"],
            "previous_agent_summary_included": freshness["previous_agent_summary_included"],
            "hidden_reasoning_included": freshness["hidden_reasoning_included"],
            "active_cycle": freshness["active_cycle"],
        },
        "input_hashes": dict(context["input_hashes"]),
        "artifact_paths": dict(artifact_paths),
    }
