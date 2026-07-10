from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from quality_runner.artifacts import artifact_dir
from quality_runner.review_types import (
    EvidenceReference,
    FreshnessPolicy,
    ReviewBreadth,
    ReviewMode,
    ReviewOptions,
    ReviewPacket,
    ReviewScope,
)

REVIEW_CONTEXT_SCHEMA = "quality-runner-review-context-v0.1"
REVIEW_MANIFEST_SCHEMA = "quality-runner-review-manifest-v0.1"
_MODES = ("task", "blind", "combined")
_SCOPES = ("task", "project")
_BREADTHS = ("focused", "related", "full")


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
) -> ReviewOptions:
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
    options: ReviewOptions = {
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
    return options


def build_review_packet(
    *,
    repo_root: Path,
    run_id: str,
    options: ReviewOptions,
    repository_state: Mapping[str, object] | None = None,
    changed_files: Sequence[str] = (),
    omitted_evidence: Sequence[str] = (),
) -> ReviewPacket:
    artifact_dir(repo_root, run_id)
    mode = options.get("mode")
    scope = options.get("scope")
    breadth = options.get("breadth")
    if mode is None or scope is None or breadth is None:
        raise ValueError("review options require mode, scope, and breadth")
    active_cycle = bool(options.get("active_cycle", False))
    evidence = list(options.get("evidence", []))
    task = options.get("task")
    if mode in {"task", "combined"} and not task:
        raise ValueError("task is required for task and combined review modes")
    freshness: FreshnessPolicy = {
        "new_invocation_required": True,
        "prior_review_context_included": False,
        "previous_agent_summary_included": bool(options.get("previous_summary")),
        "hidden_reasoning_included": False,
        "active_cycle": active_cycle,
    }
    payload: ReviewPacket = {
        "schema": REVIEW_CONTEXT_SCHEMA,
        "run_id": run_id,
        "repo_root": str(repo_root.expanduser().resolve()),
        "mode": mode,
        "scope": scope,
        "breadth": breadth,
        "repository_state": dict(repository_state or {}),
        "changed_files": _clean_strings(changed_files),
        "exclusions": list(options.get("exclusions", [])),
        "evidence": evidence,
        "omitted_evidence": _clean_strings(omitted_evidence),
        "freshness": freshness,
        "input_hashes": {},
    }
    if mode != "blind" and task:
        payload["task"] = task
    if options.get("include_known_issues") and not active_cycle:
        payload["known_issues"] = list(options.get("known_issues", []))
    if options.get("previous_summary") and not active_cycle and mode != "blind":
        previous_summary = options.get("previous_summary")
        if previous_summary:
            payload["previous_summary"] = previous_summary
    payload["input_hashes"] = _input_hashes(payload)
    return payload


def build_review_context(
    *,
    repo_root: Path,
    run_id: str,
    options: ReviewOptions,
    repository_state: Mapping[str, object] | None = None,
    changed_files: Sequence[str] = (),
    omitted_evidence: Sequence[str] = (),
) -> ReviewPacket:
    mode = options.get("mode")
    scope = options.get("scope")
    breadth = options.get("breadth")
    if mode is None or scope is None or breadth is None:
        raise ValueError("review options require mode, scope, and breadth")
    if mode != "combined":
        return build_review_packet(
            repo_root=repo_root,
            run_id=run_id,
            options=options,
            repository_state=repository_state,
            changed_files=changed_files,
            omitted_evidence=omitted_evidence,
        )
    task_options = dict(options)
    task_options["mode"] = "task"
    blind_options = dict(options)
    blind_options["mode"] = "blind"
    blind_options.pop("task", None)
    blind_options.pop("previous_summary", None)
    task_packet = build_review_packet(
        repo_root=repo_root,
        run_id=run_id,
        options=cast(ReviewOptions, task_options),
        repository_state=repository_state,
        changed_files=changed_files,
        omitted_evidence=omitted_evidence,
    )
    blind_packet = build_review_packet(
        repo_root=repo_root,
        run_id=run_id,
        options=cast(ReviewOptions, blind_options),
        repository_state=repository_state,
        changed_files=changed_files,
        omitted_evidence=omitted_evidence,
    )
    combined: ReviewPacket = {
        "schema": REVIEW_CONTEXT_SCHEMA,
        "run_id": run_id,
        "repo_root": str(repo_root.expanduser().resolve()),
        "mode": "combined",
        "scope": scope,
        "breadth": breadth,
        "exclusions": list(options.get("exclusions", [])),
        "evidence": list(options.get("evidence", [])),
        "omitted_evidence": _clean_strings(omitted_evidence),
        "freshness": {
            "new_invocation_required": True,
            "prior_review_context_included": False,
            "previous_agent_summary_included": False,
            "hidden_reasoning_included": False,
            "active_cycle": bool(options.get("active_cycle", False)),
        },
        "input_hashes": {
            "task_packet": _hash_payload(task_packet),
            "blind_packet": _hash_payload(blind_packet),
        },
        "packets": [task_packet, blind_packet],
    }
    return combined


def _input_hashes(payload: ReviewPacket) -> dict[str, str]:
    hashes = {"packet": _hash_payload(payload)}
    task = payload.get("task")
    if isinstance(task, str):
        hashes["task"] = _hash_text(task)
    return hashes


def _hash_payload(payload: Mapping[str, object]) -> str:
    without_hashes = {key: value for key, value in payload.items() if key != "input_hashes"}
    serialized = json.dumps(without_hashes, sort_keys=True, separators=(",", ":"))
    return _hash_text(serialized)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_strings(values: Sequence[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})
