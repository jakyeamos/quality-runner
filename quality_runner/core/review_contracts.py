from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

type ReviewMode = Literal["task", "blind", "combined"]
type ReviewScope = Literal["task", "project"]
type ReviewBreadth = Literal["focused", "related", "full"]
type AdapterStatus = Literal[
    "review-complete", "review-not-run", "malformed-output", "permission-denied"
]
type ReviewSeverity = Literal["critical", "high", "medium", "low"]
type ReviewClassification = Literal[
    "confirmed", "suspected", "not-enough-evidence", "known-accepted"
]
type ReviewConfidence = Literal["high", "medium", "low"]


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
    exclusions: list[str]
    evidence: list[EvidenceReference]
    known_issues: list[str]
    include_known_issues: bool
    active_cycle: bool
    task: str
    previous_summary: str
    prior_review_documents: list[str]


class NormalizedReviewOptions(TypedDict):
    mode: ReviewMode
    scope: ReviewScope
    breadth: ReviewBreadth
    exclusions: list[str]
    evidence: list[EvidenceReference]
    known_issues: list[str]
    include_known_issues: bool
    active_cycle: bool
    task: NotRequired[str]
    previous_summary: NotRequired[str]
    prior_review_documents: NotRequired[list[str]]


class ReviewPacketBase(TypedDict):
    schema: str
    run_id: str
    repo_root: str
    scope: ReviewScope
    breadth: ReviewBreadth
    exclusions: list[str]
    evidence: list[EvidenceReference]
    omitted_evidence: list[str]
    freshness: FreshnessPolicy
    input_hashes: dict[str, str]


class TaskReviewPacket(ReviewPacketBase):
    mode: Literal["task"]
    task: str
    repository_state: dict[str, object]
    changed_files: list[str]
    known_issues: NotRequired[list[str]]
    previous_summary: NotRequired[str]


class BlindReviewPacket(ReviewPacketBase):
    mode: Literal["blind"]
    repository_state: dict[str, object]
    changed_files: list[str]
    known_issues: NotRequired[list[str]]


class CombinedReviewPacket(ReviewPacketBase):
    mode: Literal["combined"]
    packets: list[TaskReviewPacket | BlindReviewPacket]


type ReviewPacket = TaskReviewPacket | BlindReviewPacket | CombinedReviewPacket


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


class SeverityCounts(TypedDict):
    critical: int
    high: int
    medium: int
    low: int


class ReviewFinding(TypedDict):
    id: str
    fingerprint: str
    severity: ReviewSeverity
    classification: ReviewClassification
    confidence: ReviewConfidence
    summary: str
    why_it_matters: str
    location: list[str]
    evidence: list[str]
    recommended_fix: str
    agent_prompt: str
    human_confirmation_required: bool
    status: str


class ReviewSections(TypedDict):
    missed_requirements: list[ReviewFinding]
    confirmed_issues: list[ReviewFinding]
    suspected_issues: list[ReviewFinding]
    not_enough_evidence: list[ReviewFinding]
    project_consistency_risks: list[ReviewFinding]
    regression_risks: list[ReviewFinding]
    known_accepted_issues: list[ReviewFinding]
    suggested_fixes: list[str]
    agent_handoff_prompts: list[str]
    remaining_uncertainty: list[str]


class ReviewReport(TypedDict):
    schema: str
    run_id: str
    mode: ReviewMode
    scope: ReviewScope
    breadth: ReviewBreadth
    adapter_status: AdapterStatus
    task_provenance: str | None
    summary: str
    severity_counts: SeverityCounts
    evidence_used: list[str]
    evidence_unavailable: list[str]
    exclusions: list[str]
    sections: ReviewSections
    findings: list[ReviewFinding]
    next_action: NotRequired[str]


class AdapterResult(TypedDict):
    status: AdapterStatus
    report: ReviewReport | None
    evidence_unavailable: list[str]
    message: str | None


class KnownIssueDraft(TypedDict):
    fingerprint: str
    summary: str
    status: str
    reason: str
    owner: str


class KnownIssue(TypedDict):
    id: str
    fingerprint: str
    summary: str
    status: str
    extensions: dict[str, object]
    reason: NotRequired[str]
    owner: NotRequired[str]
    updated_at: NotRequired[str]
