from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

from quality_runner.application.review_v1_serializers import (
    REVIEW_CONTEXT_SCHEMA,
    V1ReviewPacket,
    review_packet_to_v1,
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
    ReviewPacket,
    ReviewScope,
    TaskReviewPacket,
)

type ReviewPacketProjection = ReviewPacket | V1ReviewPacket
type ArtifactDirectory = Callable[[Path, str], Path]

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
) -> NormalizedReviewOptions:
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
    return options


def build_review_packet(
    *,
    repo_root: Path,
    run_id: str,
    options: NormalizedReviewOptions,
    repository_state: Mapping[str, object] | None = None,
    changed_files: Sequence[str] = (),
    omitted_evidence: Sequence[str] = (),
    artifact_path: ArtifactDirectory = artifact_dir,
) -> ReviewPacketProjection:
    artifact_path(repo_root, run_id)
    mode = options["mode"]
    freshness: FreshnessPolicy = {
        "new_invocation_required": True,
        "prior_review_context_included": False,
        "previous_agent_summary_included": bool(options.get("previous_summary")),
        "hidden_reasoning_included": False,
        "active_cycle": options["active_cycle"],
    }
    root = str(repo_root.expanduser().resolve())
    state = dict(repository_state or {})
    files = _clean_strings(changed_files)
    exclusions = list(options["exclusions"])
    evidence = list(options["evidence"])
    omitted = _clean_strings(omitted_evidence)
    if mode == "blind":
        blind_packet: BlindReviewPacket = {
            "schema": REVIEW_CONTEXT_SCHEMA,
            "run_id": run_id,
            "repo_root": root,
            "mode": "blind",
            "scope": options["scope"],
            "breadth": options["breadth"],
            "repository_state": state,
            "changed_files": files,
            "exclusions": exclusions,
            "evidence": evidence,
            "omitted_evidence": omitted,
            "freshness": freshness,
            "input_hashes": {},
        }
        if options["include_known_issues"] and not options["active_cycle"]:
            blind_packet["known_issues"] = list(options["known_issues"])
        blind_packet["input_hashes"] = _input_hashes(blind_packet)
        return blind_packet
    task = options.get("task")
    if not task:
        raise ValueError("task is required for task and combined review modes")
    if mode == "combined":
        combined_packet: V1ReviewPacket = {
            "schema": REVIEW_CONTEXT_SCHEMA,
            "run_id": run_id,
            "repo_root": root,
            "mode": "combined",
            "scope": options["scope"],
            "breadth": options["breadth"],
            "task": task,
            "repository_state": state,
            "changed_files": files,
            "exclusions": exclusions,
            "evidence": evidence,
            "omitted_evidence": omitted,
            "freshness": freshness,
            "input_hashes": {},
        }
        if options["include_known_issues"] and not options["active_cycle"]:
            combined_packet["known_issues"] = list(options["known_issues"])
        if "previous_summary" in options and not options["active_cycle"]:
            combined_packet["previous_summary"] = options["previous_summary"]
        combined_packet["input_hashes"] = _input_hashes(combined_packet)
        return combined_packet
    task_packet: TaskReviewPacket = {
        "schema": REVIEW_CONTEXT_SCHEMA,
        "run_id": run_id,
        "repo_root": root,
        "mode": "task",
        "scope": options["scope"],
        "breadth": options["breadth"],
        "task": task,
        "repository_state": state,
        "changed_files": files,
        "exclusions": exclusions,
        "evidence": evidence,
        "omitted_evidence": omitted,
        "freshness": freshness,
        "input_hashes": {},
    }
    if options["include_known_issues"] and not options["active_cycle"]:
        task_packet["known_issues"] = list(options["known_issues"])
    if "previous_summary" in options and not options["active_cycle"]:
        task_packet["previous_summary"] = options["previous_summary"]
    task_packet["input_hashes"] = _input_hashes(task_packet)
    return task_packet


def build_review_context(
    *,
    repo_root: Path,
    run_id: str,
    options: NormalizedReviewOptions,
    repository_state: Mapping[str, object] | None = None,
    changed_files: Sequence[str] = (),
    omitted_evidence: Sequence[str] = (),
    artifact_path: ArtifactDirectory = artifact_dir,
) -> ReviewPacket:
    if options["mode"] != "combined":
        return cast(
            ReviewPacket,
            build_review_packet(
                repo_root=repo_root,
                run_id=run_id,
                options=options,
                repository_state=repository_state,
                changed_files=changed_files,
                omitted_evidence=omitted_evidence,
                artifact_path=artifact_path,
            ),
        )
    task = options.get("task")
    if not task:
        raise ValueError("task is required for combined review mode")
    task_options: NormalizedReviewOptions = {**options, "mode": "task", "task": task}
    blind_options: NormalizedReviewOptions = {
        "mode": "blind",
        "scope": options["scope"],
        "breadth": options["breadth"],
        "exclusions": list(options["exclusions"]),
        "evidence": list(options["evidence"]),
        "known_issues": list(options["known_issues"]),
        "include_known_issues": options["include_known_issues"],
        "active_cycle": options["active_cycle"],
    }
    task_packet = cast(
        TaskReviewPacket,
        build_review_packet(
            repo_root=repo_root,
            run_id=run_id,
            options=task_options,
            repository_state=repository_state,
            changed_files=changed_files,
            omitted_evidence=omitted_evidence,
            artifact_path=artifact_path,
        ),
    )
    blind_packet = cast(
        BlindReviewPacket,
        build_review_packet(
            repo_root=repo_root,
            run_id=run_id,
            options=blind_options,
            repository_state=repository_state,
            changed_files=changed_files,
            omitted_evidence=omitted_evidence,
            artifact_path=artifact_path,
        ),
    )
    combined: CombinedReviewPacket = {
        "schema": REVIEW_CONTEXT_SCHEMA,
        "run_id": run_id,
        "repo_root": str(repo_root.expanduser().resolve()),
        "mode": "combined",
        "scope": options["scope"],
        "breadth": options["breadth"],
        "exclusions": list(options["exclusions"]),
        "evidence": list(options["evidence"]),
        "omitted_evidence": _clean_strings(omitted_evidence),
        "freshness": {
            "new_invocation_required": True,
            "prior_review_context_included": False,
            "previous_agent_summary_included": False,
            "hidden_reasoning_included": False,
            "active_cycle": options["active_cycle"],
        },
        "input_hashes": {
            "task_packet": _hash_payload(task_packet),
            "blind_packet": _hash_payload(blind_packet),
        },
        "packets": [task_packet, blind_packet],
    }
    return combined


def _input_hashes(payload: ReviewPacketProjection) -> dict[str, str]:
    hashes = {"packet": _hash_payload(payload)}
    task = payload.get("task")
    if isinstance(task, str):
        hashes["task"] = _hash_text(task)
    return hashes


def _hash_payload(payload: ReviewPacketProjection) -> str:
    serialized_payload = review_packet_to_v1(payload)
    serialized_payload.pop("input_hashes", None)
    serialized = json.dumps(serialized_payload, sort_keys=True, separators=(",", ":"))
    return _hash_text(serialized)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_strings(values: Sequence[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})
