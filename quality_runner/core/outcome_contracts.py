from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

type OutcomeSchema = Literal["quality-runner-outcome-v0.2"]
type OutcomeJourney = Literal["audit", "review", "verify", "runs"]
type OutcomeState = Literal[
    "complete",
    "action-required",
    "awaiting-evidence",
    "blocked",
    "failed",
    "empty",
]
type OutcomeAssessment = Literal[
    "clean",
    "findings",
    "inspection-only",
    "packet-ready",
    "review-complete",
    "review-unavailable",
    "gates-passed",
    "gates-passed-with-findings",
    "evidence-incomplete",
    "gates-failed",
    "history",
    "no-history",
]
type OutcomeConfidenceLevel = Literal["confirmed", "observed", "limited", "none"]
type OutcomeWriteState = Literal["none", "artifacts-written"]
type OutcomeSourceWorktree = Literal["unchanged", "branch-switched"]
type OutcomeSafetyMode = Literal[
    "scan-only",
    "evidence-only",
    "disposable-execution",
    "read-only-history",
]
type OutcomeNextActionKind = Literal[
    "read-handoff",
    "provide-review-output",
    "authorize-verification",
    "inspect-gate-failure",
    "inspect-run",
    "start-audit",
    "none",
]


class OutcomeConfidence(TypedDict):
    level: OutcomeConfidenceLevel
    basis: list[str]
    limitations: list[str]


class OutcomeWrites(TypedDict):
    source_worktree: OutcomeSourceWorktree
    state: OutcomeWriteState
    artifact_paths: dict[str, str]


class OutcomeSafety(TypedDict):
    mode: OutcomeSafetyMode
    commands_executed: bool
    source_worktree_mutated: bool
    requires_explicit_authorization: bool
    note: NotRequired[str]


class OutcomeNextAction(TypedDict):
    kind: OutcomeNextActionKind
    summary: str
    command: NotRequired[str]
    requires_authorization: bool


class OutcomeSource(TypedDict):
    legacy_schema: str
    legacy_status: str


class OutcomeHistoryRun(TypedDict):
    run_id: str
    status: str
    lifecycle_status: NotRequired[str]


class OutcomeHistory(TypedDict):
    runs: list[OutcomeHistoryRun]
    truncated: bool
    unavailable_run_ids: list[str]
    selected_run_id: NotRequired[str]


class JourneyOutcome(TypedDict):
    schema: OutcomeSchema
    journey: OutcomeJourney
    state: OutcomeState
    assessment: OutcomeAssessment
    confidence: OutcomeConfidence
    writes: OutcomeWrites
    safety: OutcomeSafety
    next_action: OutcomeNextAction
    summary: str
    source: OutcomeSource
    run_id: NotRequired[str]
    history: NotRequired[OutcomeHistory]


type OutcomePayload = JourneyOutcome
