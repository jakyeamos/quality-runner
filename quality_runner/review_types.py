"""Compatibility exports retained until the M6 deprecation cutover."""

from typing import TypedDict

from quality_runner.core.review_contracts import (
    AdapterStatus,
    BlindReviewPacket,
    CombinedReviewPacket,
    EvidenceReference,
    FreshnessPolicy,
    ReviewBreadth,
    ReviewManifest,
    ReviewMode,
    ReviewOptions,
    ReviewScope,
    TaskReviewPacket,
)


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
    packets: list["ReviewPacket"]


__all__ = [
    "AdapterStatus",
    "BlindReviewPacket",
    "CombinedReviewPacket",
    "EvidenceReference",
    "FreshnessPolicy",
    "ReviewBreadth",
    "ReviewManifest",
    "ReviewMode",
    "ReviewOptions",
    "ReviewPacket",
    "ReviewScope",
    "TaskReviewPacket",
]
