"""Compatibility packet factories retained until the M6 deprecation cutover."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from quality_runner.application.review_context_factory import (
    build_review_context as _build_review_context,
)
from quality_runner.application.review_context_factory import (
    build_review_packet as _build_review_packet,
)
from quality_runner.application.review_context_factory import (
    normalize_review_options as _normalize_review_options,
)
from quality_runner.application.review_v1_serializers import (
    REVIEW_CONTEXT_SCHEMA as _REVIEW_CONTEXT_SCHEMA,
)
from quality_runner.application.review_v1_serializers import (
    REVIEW_MANIFEST_SCHEMA as _REVIEW_MANIFEST_SCHEMA,
)
from quality_runner.artifacts import artifact_dir
from quality_runner.core.review_contracts import EvidenceReference, NormalizedReviewOptions
from quality_runner.review_types import ReviewOptions as LegacyReviewOptions
from quality_runner.review_types import ReviewPacket as LegacyReviewPacket

REVIEW_CONTEXT_SCHEMA = _REVIEW_CONTEXT_SCHEMA
REVIEW_MANIFEST_SCHEMA = _REVIEW_MANIFEST_SCHEMA


def normalize_review_options(
    *,
    mode: str,
    scope: str,
    breadth: str | None,
    task: str | None,
    exclusions: Sequence[str] = (),
    evidence: Sequence[EvidenceReference] = (),
    known_issues: Sequence[str] = (),
    include_known_issues: bool = False,
    previous_summary: str | None = None,
    prior_review_documents: Sequence[str] = (),
    active_cycle: bool = False,
) -> LegacyReviewOptions:
    return cast(
        LegacyReviewOptions,
        _normalize_review_options(
            mode=mode,
            scope=scope,
            breadth=breadth,
            task=task,
            exclusions=exclusions,
            evidence=evidence,
            known_issues=known_issues,
            include_known_issues=include_known_issues,
            previous_summary=previous_summary,
            prior_review_documents=prior_review_documents,
            active_cycle=active_cycle,
        ),
    )


def build_review_packet(
    *,
    repo_root: Path,
    run_id: str,
    options: LegacyReviewOptions,
    repository_state: Mapping[str, object] | None = None,
    changed_files: Sequence[str] = (),
    omitted_evidence: Sequence[str] = (),
) -> LegacyReviewPacket:
    return cast(
        LegacyReviewPacket,
        _build_review_packet(
            repo_root=repo_root,
            run_id=run_id,
            options=_legacy_options(options),
            repository_state=repository_state,
            changed_files=changed_files,
            omitted_evidence=omitted_evidence,
            artifact_path=artifact_dir,
        ),
    )


def build_review_context(
    *,
    repo_root: Path,
    run_id: str,
    options: LegacyReviewOptions,
    repository_state: Mapping[str, object] | None = None,
    changed_files: Sequence[str] = (),
    omitted_evidence: Sequence[str] = (),
) -> LegacyReviewPacket:
    return cast(
        LegacyReviewPacket,
        _build_review_context(
            repo_root=repo_root,
            run_id=run_id,
            options=_legacy_options(options),
            repository_state=repository_state,
            changed_files=changed_files,
            omitted_evidence=omitted_evidence,
            artifact_path=artifact_dir,
        ),
    )


def _legacy_options(
    options: LegacyReviewOptions | NormalizedReviewOptions,
) -> NormalizedReviewOptions:
    mode = options.get("mode")
    scope = options.get("scope")
    breadth = options.get("breadth")
    if mode is None or scope is None or breadth is None:
        raise ValueError("review options require mode, scope, and breadth")
    normalized: NormalizedReviewOptions = {
        "mode": mode,
        "scope": scope,
        "breadth": breadth,
        "exclusions": list(options.get("exclusions", [])),
        "evidence": list(options.get("evidence", [])),
        "known_issues": list(options.get("known_issues", [])),
        "include_known_issues": bool(options.get("include_known_issues", False)),
        "active_cycle": bool(options.get("active_cycle", False)),
    }
    if "task" in options:
        normalized["task"] = options["task"]
    previous_summary = options.get("previous_summary")
    if isinstance(previous_summary, str) and previous_summary:
        normalized["previous_summary"] = previous_summary
    if "prior_review_documents" in options:
        normalized["prior_review_documents"] = list(options["prior_review_documents"])
    return normalized
