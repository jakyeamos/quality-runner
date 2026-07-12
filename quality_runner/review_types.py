from __future__ import annotations

from typing import Literal, TypedDict

ReviewMode = Literal["task", "blind", "combined"]
ReviewScope = Literal["task", "project"]
ReviewBreadth = Literal["focused", "related", "full"]
AdapterStatus = Literal[
    "review-complete", "review-not-run", "malformed-output", "permission-denied"
]


class EvidenceReference(TypedDict):
    path: str
    kind: str
    available: bool
    note: str


class FreshnessPolicy(TypedDict):
    new_invocation_required: bool
    prior_review_context_included: bool
    previous_agent_summary_included: bool
    hidden_reasoning_included: bool
    active_cycle: bool


class ReviewOptions(TypedDict, total=False):
    mode: ReviewMode
    scope: ReviewScope
    breadth: ReviewBreadth
    task: str
    exclusions: list[str]
    evidence: list[EvidenceReference]
    known_issues: list[str]
    include_known_issues: bool
    previous_summary: str
    prior_review_documents: list[str]
    active_cycle: bool


class ReviewPacket(TypedDict, total=False):
    schema: str
    run_id: str
    repo_root: str
    mode: ReviewMode
    scope: ReviewScope
    breadth: ReviewBreadth
    task: str
    repository_state: dict[str, object]
    changed_files: list[str]
    exclusions: list[str]
    evidence: list[EvidenceReference]
    omitted_evidence: list[str]
    known_issues: list[str]
    previous_summary: str
    freshness: FreshnessPolicy
    input_hashes: dict[str, str]
    packets: list[ReviewPacket]


class ReviewManifest(TypedDict):
    schema: str
    run_id: str
    mode: ReviewMode
    scope: ReviewScope
    breadth: ReviewBreadth
    exclusions: list[str]
    evidence_references: list[EvidenceReference]
    freshness: FreshnessPolicy
    input_hashes: dict[str, str]
    artifact_paths: dict[str, str]
