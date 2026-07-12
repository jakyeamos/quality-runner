from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from quality_runner.application.review_v1_serializers import (
    REVIEW_CONTEXT_SCHEMA,
    V1ReviewPacket,
    review_packet_to_v1,
)
from quality_runner.application.review_v1_serializers import (
    REVIEW_MANIFEST_SCHEMA as _REVIEW_MANIFEST_SCHEMA,
)
from quality_runner.artifacts import artifact_dir
from quality_runner.core.review_contracts import (
    BlindReviewPacket,
    CombinedReviewPacket,
    EvidenceReference,
    FreshnessPolicy,
    NormalizedReviewOptions,
    ReviewBreadth,
    ReviewMode,
    ReviewScope,
    TaskReviewPacket,
)
from quality_runner.core.review_contracts import (
    ReviewPacket as StrictReviewPacket,
)
from quality_runner.review_types import ReviewOptions as LegacyReviewOptions
from quality_runner.review_types import ReviewPacket as LegacyReviewPacket

_MODES = ("task", "blind", "combined")
_SCOPES = ("task", "project")
_BREADTHS = ("focused", "related", "full")
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
    if mode not in _MODES:
        raise ValueError(f"invalid review mode: {mode}")
    if scope not in _SCOPES:
        raise ValueError(f"invalid review scope: {scope}")
    resolved_breadth = breadth or ("related" if scope == "project" else "focused")
    if resolved_breadth not in _BREADTHS:
        raise ValueError(f"invalid review breadth: {resolved_breadth}")
    normalized_task = task.strip() if isinstance(task, str) else None
    if mode in {"task", "combined"} and not normalized_task:
        raise ValueError("task is required for task and combined review modes")
    if scope == "task" and mode == "blind":
        raise ValueError("blind review requires project scope")
    if active_cycle:
        previous_summary = None
        prior_review_documents = ()
        include_known_issues = False
    options: NormalizedReviewOptions = {
        "mode": cast(ReviewMode, mode),
        "scope": cast(ReviewScope, scope),
        "breadth": cast(ReviewBreadth, resolved_breadth),
        "exclusions": _clean_strings(exclusions),
        "evidence": list(evidence),
        "known_issues": _clean_strings(known_issues),
        "include_known_issues": include_known_issues,
        "active_cycle": active_cycle,
    }
    if normalized_task:
        options["task"] = normalized_task
    if previous_summary and previous_summary.strip() and not active_cycle:
        options["previous_summary"] = previous_summary.strip()
    if prior_review_documents and not active_cycle:
        options["prior_review_documents"] = _clean_strings(prior_review_documents)
    return cast(LegacyReviewOptions, options)


def build_review_packet(
    *,
    repo_root: Path,
    run_id: str,
    options: LegacyReviewOptions,
    repository_state: Mapping[str, object] | None = None,
    changed_files: Sequence[str] = (),
    omitted_evidence: Sequence[str] = (),
) -> LegacyReviewPacket:
    normalized_options = _legacy_options(options)
    artifact_dir(repo_root, run_id)
    mode = normalized_options["mode"]
    freshness: FreshnessPolicy = {
        "new_invocation_required": True,
        "prior_review_context_included": False,
        "previous_agent_summary_included": bool(normalized_options.get("previous_summary")),
        "hidden_reasoning_included": False,
        "active_cycle": normalized_options["active_cycle"],
    }
    root = str(repo_root.expanduser().resolve())
    state = dict(repository_state or {})
    files = _clean_strings(changed_files)
    exclusions = list(normalized_options["exclusions"])
    evidence = list(normalized_options["evidence"])
    omitted = _clean_strings(omitted_evidence)
    if mode == "blind":
        blind_packet: BlindReviewPacket = {
            "schema": REVIEW_CONTEXT_SCHEMA,
            "run_id": run_id,
            "repo_root": root,
            "mode": "blind",
            "scope": normalized_options["scope"],
            "breadth": normalized_options["breadth"],
            "repository_state": state,
            "changed_files": files,
            "exclusions": exclusions,
            "evidence": evidence,
            "omitted_evidence": omitted,
            "freshness": freshness,
            "input_hashes": {},
        }
        if normalized_options["include_known_issues"] and not normalized_options["active_cycle"]:
            blind_packet["known_issues"] = list(normalized_options["known_issues"])
        blind_packet["input_hashes"] = _input_hashes(blind_packet)
        return cast(LegacyReviewPacket, blind_packet)
    task = normalized_options.get("task")
    if not task:
        raise ValueError("task is required for task and combined review modes")
    if mode == "combined":
        combined_packet: V1ReviewPacket = {
            "schema": REVIEW_CONTEXT_SCHEMA,
            "run_id": run_id,
            "repo_root": root,
            "mode": "combined",
            "scope": normalized_options["scope"],
            "breadth": normalized_options["breadth"],
            "task": task,
            "repository_state": state,
            "changed_files": files,
            "exclusions": exclusions,
            "evidence": evidence,
            "omitted_evidence": omitted,
            "freshness": freshness,
            "input_hashes": {},
        }
        if normalized_options["include_known_issues"] and not normalized_options["active_cycle"]:
            combined_packet["known_issues"] = list(normalized_options["known_issues"])
        if "previous_summary" in normalized_options and not normalized_options["active_cycle"]:
            combined_packet["previous_summary"] = normalized_options["previous_summary"]
        combined_packet["input_hashes"] = _input_hashes(combined_packet)
        return cast(LegacyReviewPacket, combined_packet)
    task_packet: TaskReviewPacket = {
        "schema": REVIEW_CONTEXT_SCHEMA,
        "run_id": run_id,
        "repo_root": root,
        "mode": "task",
        "scope": normalized_options["scope"],
        "breadth": normalized_options["breadth"],
        "task": task,
        "repository_state": state,
        "changed_files": files,
        "exclusions": exclusions,
        "evidence": evidence,
        "omitted_evidence": omitted,
        "freshness": freshness,
        "input_hashes": {},
    }
    if normalized_options["include_known_issues"] and not normalized_options["active_cycle"]:
        task_packet["known_issues"] = list(normalized_options["known_issues"])
    if "previous_summary" in normalized_options and not normalized_options["active_cycle"]:
        task_packet["previous_summary"] = normalized_options["previous_summary"]
    task_packet["input_hashes"] = _input_hashes(task_packet)
    return cast(LegacyReviewPacket, task_packet)


def build_review_context(
    *,
    repo_root: Path,
    run_id: str,
    options: LegacyReviewOptions,
    repository_state: Mapping[str, object] | None = None,
    changed_files: Sequence[str] = (),
    omitted_evidence: Sequence[str] = (),
) -> LegacyReviewPacket:
    normalized_options = _legacy_options(options)
    if normalized_options["mode"] != "combined":
        return build_review_packet(
            repo_root=repo_root,
            run_id=run_id,
            options=cast(LegacyReviewOptions, normalized_options),
            repository_state=repository_state,
            changed_files=changed_files,
            omitted_evidence=omitted_evidence,
        )
    task = normalized_options.get("task")
    if not task:
        raise ValueError("task is required for combined review mode")
    task_options: NormalizedReviewOptions = {
        **normalized_options,
        "mode": "task",
        "task": task,
    }
    blind_options: NormalizedReviewOptions = {
        "mode": "blind",
        "scope": normalized_options["scope"],
        "breadth": normalized_options["breadth"],
        "exclusions": list(normalized_options["exclusions"]),
        "evidence": list(normalized_options["evidence"]),
        "known_issues": list(normalized_options["known_issues"]),
        "include_known_issues": normalized_options["include_known_issues"],
        "active_cycle": normalized_options["active_cycle"],
    }
    task_packet = cast(
        TaskReviewPacket,
        build_review_packet(
            repo_root=repo_root,
            run_id=run_id,
            options=cast(LegacyReviewOptions, task_options),
            repository_state=repository_state,
            changed_files=changed_files,
            omitted_evidence=omitted_evidence,
        ),
    )
    blind_packet = cast(
        BlindReviewPacket,
        build_review_packet(
            repo_root=repo_root,
            run_id=run_id,
            options=cast(LegacyReviewOptions, blind_options),
            repository_state=repository_state,
            changed_files=changed_files,
            omitted_evidence=omitted_evidence,
        ),
    )
    combined: CombinedReviewPacket = {
        "schema": REVIEW_CONTEXT_SCHEMA,
        "run_id": run_id,
        "repo_root": str(repo_root.expanduser().resolve()),
        "mode": "combined",
        "scope": normalized_options["scope"],
        "breadth": normalized_options["breadth"],
        "exclusions": list(normalized_options["exclusions"]),
        "evidence": list(normalized_options["evidence"]),
        "omitted_evidence": _clean_strings(omitted_evidence),
        "freshness": {
            "new_invocation_required": True,
            "prior_review_context_included": False,
            "previous_agent_summary_included": False,
            "hidden_reasoning_included": False,
            "active_cycle": normalized_options["active_cycle"],
        },
        "input_hashes": {
            "task_packet": _hash_payload(task_packet),
            "blind_packet": _hash_payload(blind_packet),
        },
        "packets": [task_packet, blind_packet],
    }
    return cast(LegacyReviewPacket, combined)


def _input_hashes(payload: StrictReviewPacket | V1ReviewPacket) -> dict[str, str]:
    hashes = {"packet": _hash_payload(payload)}
    task = payload.get("task")
    if isinstance(task, str):
        hashes["task"] = _hash_text(task)
    return hashes


def _hash_payload(payload: StrictReviewPacket | V1ReviewPacket) -> str:
    serialized_payload = review_packet_to_v1(payload)
    serialized_payload.pop("input_hashes", None)
    serialized = json.dumps(serialized_payload, sort_keys=True, separators=(",", ":"))
    return _hash_text(serialized)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_strings(values: Sequence[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})


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
