from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from quality_runner.application.review_context_factory import build_review_context
from quality_runner.application.review_projection import build_review_manifest
from quality_runner.application.review_reporting import build_review_report
from quality_runner.application.review_responses import validate_review_response
from quality_runner.core.review_contracts import (
    AdapterStatus,
    FreshReviewExecution,
    NormalizedReviewOptions,
    ReviewFinding,
    ReviewHandoff,
    ReviewLoopStop,
    ReviewPacket,
    ReviewReport,
)
from quality_runner.review_execution_artifacts import (
    complete_review_execution_artifacts,
    legacy_review_artifact_paths,
    load_prepared_review,
    prepare_review_execution_artifacts,
    read_review_adapter_response,
    record_review_execution_failure,
)
from quality_runner.review_loop import (
    finalize_review_loop,
    select_handoff_findings,
    should_stop,
    start_review_loop,
)
from quality_runner.review_response_files import ReviewAdapterResponseError

_ADVISORY_EXCLUSION_LIMITATION = (
    "Exclusions are advisory for a local file adapter; Quality Runner cannot verify the external "
    "reviewer did not access excluded repository files."
)


def prepare_fresh_review(
    *,
    repo_root: Path,
    run_id: str,
    options: NormalizedReviewOptions,
    repository_state: Mapping[str, object],
    changed_files: Sequence[str],
    omitted_evidence: Sequence[str],
    save: bool,
) -> FreshReviewExecution:
    context = build_review_context(
        repo_root=repo_root,
        run_id=run_id,
        options=options,
        repository_state=repository_state,
        changed_files=changed_files,
        omitted_evidence=omitted_evidence,
    )
    manifest = build_review_manifest(
        context,
        artifact_paths=legacy_review_artifact_paths(repo_root, run_id) if save else {},
    )
    report = _review_report(
        context=context,
        status="review-not-run",
        evidence_unavailable=["No review adapter response was supplied.", *omitted_evidence],
        next_action=_prepare_next_action(
            repo_root=repo_root,
            run_id=run_id,
            save=save,
            context=context,
        ),
    )
    handoff = _not_ready_handoff()
    artifact_paths = (
        prepare_review_execution_artifacts(
            repo_root=repo_root,
            context=context,
            manifest=manifest,
            report=report,
        )
        if save
        else {}
    )
    return {
        "state": "packet-ready",
        "context": context,
        "manifest": manifest,
        "report": report,
        "artifact_paths": artifact_paths,
        "handoff": handoff,
    }


def complete_fresh_review(
    *,
    repo_root: Path,
    run_id: str,
    response_path: Path,
    finding_ids: Sequence[str],
    all_critical_high: bool,
    loop: bool,
    loop_stop: ReviewLoopStop | None,
) -> FreshReviewExecution:
    context, manifest, _, artifact_paths = load_prepared_review(repo_root=repo_root, run_id=run_id)
    active_cycle = context["freshness"]["active_cycle"]
    if loop and not active_cycle:
        raise ValueError("--loop must be selected when preparing the review packet")
    if loop_stop is not None and not active_cycle:
        raise ValueError("--loop-stop requires a packet prepared with --loop")
    try:
        response_payload = read_review_adapter_response(
            repo_root=repo_root,
            run_id=run_id,
            response_path=response_path,
        )
        report, response_provenance = validate_review_response(response_payload, context)
    except ReviewAdapterResponseError:
        raise
    except ValueError as error:
        raise ReviewAdapterResponseError(str(error)) from error
    report = _with_advisory_exclusion_limitation(report)
    handoff = build_review_handoff(
        run_id=run_id,
        report=report,
        finding_ids=finding_ids,
        all_critical_high=all_critical_high,
        loop=active_cycle,
        loop_stop=loop_stop,
    )
    next_action = handoff.get("next_action")
    if isinstance(next_action, str) and next_action:
        report["next_action"] = next_action
    artifact_paths = complete_review_execution_artifacts(
        repo_root=repo_root,
        context=context,
        report=report,
        handoff=handoff,
        response_payload=response_payload,
        response_provenance=response_provenance,
    )
    return {
        "state": "review-complete",
        "context": context,
        "manifest": manifest,
        "report": report,
        "artifact_paths": artifact_paths,
        "handoff": handoff,
        "response_provenance": response_provenance,
    }


def incomplete_fresh_review(
    *, repo_root: Path, run_id: str, status: AdapterStatus, message: str
) -> FreshReviewExecution:
    context, manifest, _, _ = load_prepared_review(repo_root=repo_root, run_id=run_id)
    report = _review_report(
        context=context,
        status=status,
        evidence_unavailable=[message],
        next_action=(
            "Correct the adapter response without changing the prepared packet, then submit it again."
        ),
    )
    artifact_paths = record_review_execution_failure(
        repo_root=repo_root,
        run_id=run_id,
        report=report,
        message=message,
    )
    return {
        "state": "review-incomplete",
        "context": context,
        "manifest": manifest,
        "report": report,
        "artifact_paths": artifact_paths,
        "handoff": _not_ready_handoff(),
    }


def build_review_handoff(
    *,
    run_id: str,
    report: ReviewReport,
    finding_ids: Sequence[str],
    all_critical_high: bool,
    loop: bool,
    loop_stop: ReviewLoopStop | None,
) -> ReviewHandoff:
    if finding_ids and all_critical_high:
        raise ValueError("use --finding-id or --all-critical-high, not both")
    if loop_stop is not None and not loop:
        raise ValueError("--loop-stop requires --loop")
    if report["adapter_status"] != "review-complete":
        return _not_ready_handoff()
    available = {finding["id"] for finding in report["findings"]}
    unknown = sorted({finding_id for finding_id in finding_ids if finding_id not in available})
    if unknown:
        raise ValueError(f"unknown review finding id: {', '.join(unknown)}")
    selected = cast(
        list[ReviewFinding],
        select_handoff_findings(
            report["findings"],
            finding_ids=finding_ids,
            all_critical_high=all_critical_high,
        ),
    )
    if not report["findings"]:
        handoff: ReviewHandoff = {
            "status": "not-needed",
            "selected_finding_ids": [],
            "selected_findings": [],
            "next_action": "No review findings require a fixing-agent handoff.",
        }
    elif not selected:
        handoff = {
            "status": "selection-required",
            "selected_finding_ids": [],
            "selected_findings": [],
            "next_action": "Select --finding-id values or use --all-critical-high before handing work to a fixer.",
        }
    else:
        handoff = {
            "status": "ready",
            "selected_finding_ids": [finding["id"] for finding in selected],
            "selected_findings": selected,
            "next_action": "Send review-fix-prompts.md to a separate fixing agent; Quality Runner will not edit source files.",
        }
    if loop:
        handoff["loop_state"] = _loop_state(
            run_id=run_id,
            findings=report["findings"],
            selected_finding_ids=handoff["selected_finding_ids"],
            stop_condition=loop_stop or "critical-high",
        )
    return handoff


def _review_report(
    *,
    context: ReviewPacket,
    status: AdapterStatus,
    evidence_unavailable: Sequence[str],
    next_action: str,
) -> ReviewReport:
    mode = context["mode"]
    report = build_review_report(
        run_id=context["run_id"],
        mode=mode,
        scope=context["scope"],
        breadth=context["breadth"],
        findings=[],
        evidence_used=[],
        evidence_unavailable=evidence_unavailable,
        exclusions=context["exclusions"],
        adapter_status=status,
        task_provenance=_task_provenance(context),
    )
    report["next_action"] = next_action
    return report


def _task_provenance(context: ReviewPacket) -> str | None:
    if context["mode"] == "blind":
        return None
    task_hash = context["input_hashes"].get("task")
    return task_hash if isinstance(task_hash, str) else "None"


def _prepare_next_action(*, repo_root: Path, run_id: str, save: bool, context: ReviewPacket) -> str:
    if not save:
        return "Run this review again without --no-save to write a packet that a local adapter can answer."
    relative_response = f".quality-runner/runs/{run_id}/review-adapter-response.json"
    packet_instruction = (
        "Provide the separately scoped task and blind packets to their intended reviewers"
        if context["mode"] == "combined"
        else "Provide review-agent-packet.md to a reviewer"
    )
    return (
        f"{packet_instruction}, save the packet-bound response as {relative_response}, then run "
        f"quality-runner review {shlex.quote(str(repo_root))} --run-id {shlex.quote(run_id)} "
        f"--adapter-output {shlex.quote(relative_response)}."
    )


def _with_advisory_exclusion_limitation(report: ReviewReport) -> ReviewReport:
    limitations = sorted({*report["evidence_unavailable"], _ADVISORY_EXCLUSION_LIMITATION})
    return {**report, "evidence_unavailable": limitations}


def _not_ready_handoff() -> ReviewHandoff:
    return {
        "status": "not-ready",
        "selected_finding_ids": [],
        "selected_findings": [],
        "next_action": "Provide a bound adapter response before preparing a fixing handoff.",
    }


def _loop_state(
    *,
    run_id: str,
    findings: Sequence[Mapping[str, object]],
    selected_finding_ids: Sequence[str],
    stop_condition: ReviewLoopStop,
) -> dict[str, object]:
    state = start_review_loop(cycle_id=run_id, stop_condition=stop_condition)
    state["selected_finding_ids"] = list(selected_finding_ids)
    state["fixing_agent_status"] = "handoff-ready" if selected_finding_ids else "not-required"
    if should_stop(findings, stop_condition):
        return finalize_review_loop(state, findings)
    return dict(state)
