from __future__ import annotations

from pathlib import Path

from quality_runner.application.outcome_projection_support import (
    LegacyPayload,
    _authorize_verification_command,
    _command,
    _confidence,
    _execution_details,
    _handoff_command,
    _history_safety,
    _history_writes,
    _next_action,
    _object_list,
    _outcome,
    _requires_verification_authorization,
    _review_finding_count,
    _run_command,
    _run_id,
    _safety,
    _status,
    _string,
    _string_list,
    _usable_verification,
    _verification_matches_result,
    _verify_confidence,
    _warning_messages,
    _writes,
)
from quality_runner.application.run_history import HistoryPayload
from quality_runner.core.outcome_contracts import (
    JourneyOutcome,
    OutcomeConfidence,
    OutcomeHistory,
    OutcomeHistoryRun,
)


def project_audit_outcome(
    payload: LegacyPayload,
    *,
    repo_root: Path,
    inspect_only: bool,
    branch_switched: bool,
) -> JourneyOutcome:
    warnings = _warning_messages(payload)
    confidence = _confidence(
        level="limited" if warnings else "observed",
        basis=["local repository analysis"],
        limitations=warnings,
    )
    writes = _writes(payload, branch_switched=branch_switched)
    safety = _safety(
        mode="scan-only",
        commands_executed=False,
        requires_explicit_authorization=False,
        source_worktree_mutated=branch_switched,
        note=(
            "The scan switched the checked-out branch before analysis; source files were not edited."
            if branch_switched
            else "Quality Runner wrote evidence artifacts but did not edit source files."
        ),
    )
    run_id = _run_id(payload)
    if inspect_only:
        return _outcome(
            journey="audit",
            state="complete",
            assessment="inspection-only",
            confidence=confidence,
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="start-audit",
                summary="Prepare a remediation plan when you are ready to act on this evidence.",
                command=_command("audit", repo_root),
            ),
            summary="Repository inspection completed; no remediation plan was prepared.",
            payload=payload,
            run_id=run_id,
        )
    if _status(payload) == "clean":
        return _outcome(
            journey="audit",
            state="complete",
            assessment="clean",
            confidence=confidence,
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="none",
                summary="Audit evidence is clean; no remediation action is recommended.",
            ),
            summary="Audit completed with no remediation slices.",
            payload=payload,
            run_id=run_id,
        )
    return _outcome(
        journey="audit",
        state="action-required",
        assessment="findings",
        confidence=confidence,
        writes=writes,
        safety=safety,
        next_action=_next_action(
            kind="read-handoff",
            summary="Read the remediation handoff before authorizing implementation work.",
            command=_handoff_command(repo_root, run_id),
        ),
        summary="Audit completed with remediation evidence that needs a decision.",
        payload=payload,
        run_id=run_id,
    )


def project_review_outcome(payload: LegacyPayload, *, repo_root: Path) -> JourneyOutcome:
    status = _status(payload)
    writes = _writes(payload, branch_switched=False)
    safety = _safety(
        mode="scan-only",
        commands_executed=False,
        requires_explicit_authorization=False,
        note="Review reads local evidence and may write review artifacts; it does not edit source files.",
    )
    run_id = _run_id(payload)
    next_summary = _string(payload.get("next_action"))
    if status == "review-not-run":
        return _outcome(
            journey="review",
            state="awaiting-evidence",
            assessment="packet-ready",
            confidence=_confidence(
                level="none",
                basis=["review packet prepared"],
                limitations=["No packet-bound local review response was supplied."],
            ),
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="provide-review-output",
                summary=next_summary
                or "Provide a packet-bound local review response for this prepared packet.",
            ),
            summary="Review packet is ready, but no packet-bound local response has completed.",
            payload=payload,
            run_id=run_id,
        )
    if status in {"malformed-output", "permission-denied"}:
        return _outcome(
            journey="review",
            state="blocked",
            assessment="review-unavailable",
            confidence=_confidence(
                level="limited",
                basis=["local review packet"],
                limitations=[next_summary or f"Review adapter status: {status}."],
            ),
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="provide-review-output",
                summary=next_summary
                or "Resolve the review adapter issue before relying on review evidence.",
            ),
            summary="Review could not produce a usable packet-bound local response.",
            payload=payload,
            run_id=run_id,
        )
    limitations = _string_list(payload.get("evidence_unavailable"))
    confidence = _review_confidence(limitations)
    finding_count = _review_finding_count(payload)
    if finding_count:
        return _outcome(
            journey="review",
            state="action-required",
            assessment="findings",
            confidence=confidence,
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="inspect-run",
                summary=next_summary
                or "Inspect the saved review report before selecting remediation work.",
            ),
            summary=f"Review completed with {finding_count} recorded finding(s).",
            payload=payload,
            run_id=run_id,
        )
    return _outcome(
        journey="review",
        state="complete",
        assessment="review-complete",
        confidence=confidence,
        writes=writes,
        safety=safety,
        next_action=_next_action(
            kind="none",
            summary="Review completed without recorded findings.",
        ),
        summary="Review completed without recorded findings.",
        payload=payload,
        run_id=run_id,
    )


def project_verify_outcome(
    payload: LegacyPayload,
    *,
    repo_root: Path,
    verification: LegacyPayload | None,
    branch_switched: bool = False,
) -> JourneyOutcome:
    status = _status(payload)
    run_id = _run_id(payload)
    usable_verification = _usable_verification(verification)
    if not _verification_matches_result(status, usable_verification):
        usable_verification = None
    execution = _execution_details(usable_verification)
    requires_authorization = _requires_verification_authorization(usable_verification)
    safety_note = (
        "Authorized commands ran in a disposable checkout; this is not a host sandbox."
        if execution.isolated
        else "Recorded commands ran, but the available evidence does not prove disposable isolation."
        if execution.commands_executed
        else "No local gate command was executed; the recorded verification is evidence-only."
    )
    if branch_switched:
        safety_note = f"{safety_note} The scan switched the checked-out branch before verification."
    safety = _safety(
        mode="disposable-execution" if execution.isolated else "evidence-only",
        commands_executed=execution.commands_executed,
        requires_explicit_authorization=requires_authorization,
        source_worktree_mutated=branch_switched,
        note=safety_note,
    )
    writes = _writes(payload, branch_switched=branch_switched)
    if usable_verification is None:
        return _outcome(
            journey="verify",
            state="awaiting-evidence",
            assessment="evidence-incomplete",
            confidence=_verify_confidence(execution, usable_verification),
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="inspect-run",
                summary="Restore or inspect inconsistent gate verification evidence before drawing a conclusion.",
                command=_run_command(repo_root, run_id),
            ),
            summary="Verification result exists, but its gate evidence is unavailable or inconsistent.",
            payload=payload,
            run_id=run_id,
        )
    if status == "passed":
        confidence = _verify_confidence(execution, usable_verification)
        if confidence["level"] != "confirmed":
            return _outcome(
                journey="verify",
                state="awaiting-evidence",
                assessment="evidence-incomplete",
                confidence=confidence,
                writes=writes,
                safety=safety,
                next_action=_next_action(
                    kind="inspect-run",
                    summary="Inspect the skipped gate evidence before treating verification as complete.",
                    command=_run_command(repo_root, run_id),
                ),
                summary="Executed gates passed, but remaining evidence is incomplete.",
                payload=payload,
                run_id=run_id,
            )
        return _outcome(
            journey="verify",
            state="complete",
            assessment="gates-passed",
            confidence=confidence,
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="none",
                summary="Configured verification evidence is complete.",
            ),
            summary="Verification completed and all executed gates passed.",
            payload=payload,
            run_id=run_id,
        )
    if status == "passed-with-findings":
        return _outcome(
            journey="verify",
            state="action-required",
            assessment="gates-passed-with-findings",
            confidence=_verify_confidence(execution, usable_verification),
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="read-handoff",
                summary="Gate evidence passed; read the remediation handoff for remaining findings.",
                command=_handoff_command(repo_root, run_id),
            ),
            summary="Verification passed, but audit findings still need a decision.",
            payload=payload,
            run_id=run_id,
        )
    if status == "failed":
        return _outcome(
            journey="verify",
            state="failed",
            assessment="gates-failed",
            confidence=_verify_confidence(execution, usable_verification),
            writes=writes,
            safety=safety,
            next_action=_next_action(
                kind="inspect-gate-failure",
                summary="Inspect the recorded gate failure before retrying verification.",
                command=_run_command(repo_root, run_id),
            ),
            summary="Verification ran and one or more gates failed.",
            payload=payload,
            run_id=run_id,
        )
    if status == "blocked":
        return _outcome(
            journey="verify",
            state="blocked",
            assessment="evidence-incomplete",
            confidence=_verify_confidence(execution, usable_verification),
            writes=writes,
            safety=safety,
            next_action=(
                _next_action(
                    kind="authorize-verification",
                    summary="Authorize disposable execution to replace evidence-only gate records.",
                    command=_authorize_verification_command(repo_root, run_id),
                    requires_authorization=True,
                )
                if requires_authorization
                else _next_action(
                    kind="inspect-gate-failure",
                    summary="Inspect blocked gate evidence before changing verification policy.",
                    command=_run_command(repo_root, run_id),
                )
            ),
            summary="Verification evidence is blocked or incomplete.",
            payload=payload,
            run_id=run_id,
        )
    return _outcome(
        journey="verify",
        state="awaiting-evidence",
        assessment="evidence-incomplete",
        confidence=_verify_confidence(execution, usable_verification),
        writes=writes,
        safety=safety,
        next_action=_next_action(
            kind="inspect-run",
            summary="Inspect the recorded verification evidence before drawing a conclusion.",
            command=_run_command(repo_root, run_id),
        ),
        summary="Verification produced non-local or incomplete evidence.",
        payload=payload,
        run_id=run_id,
    )


def project_runs_outcome(history: HistoryPayload, *, repo_root: Path) -> JourneyOutcome:
    runs = _object_list(history.get("runs"))
    unavailable = _string_list(history.get("unavailable_run_ids"))
    selected_run_id = _string(history.get("selected_run_id"))
    history_snapshot = _history_snapshot(history, runs, unavailable, selected_run_id)
    if not runs:
        if unavailable:
            return _outcome(
                journey="runs",
                state="awaiting-evidence",
                assessment="evidence-incomplete",
                confidence=_confidence(
                    level="limited",
                    basis=["local Quality Runner artifact directory"],
                    limitations=unavailable,
                ),
                writes=_history_writes(),
                safety=_history_safety(),
                next_action=_next_action(
                    kind="inspect-run",
                    summary="Inspect available run history before replacing unreadable evidence.",
                    command=_command("runs", repo_root),
                ),
                summary=(
                    "The selected run is unavailable or unreadable; no clean history conclusion is available."
                    if selected_run_id
                    else "Quality Runner found unreadable run evidence; no clean history conclusion is available."
                ),
                legacy_schema="quality-runner-run-summary-v0.1",
                legacy_status="unavailable",
                run_id=selected_run_id,
                history=history_snapshot,
            )
        return _outcome(
            journey="runs",
            state="empty",
            assessment="no-history",
            confidence=_confidence(
                level="limited" if unavailable else "none",
                basis=["local Quality Runner artifact directory"],
                limitations=unavailable,
            ),
            writes=_history_writes(),
            safety=_history_safety(),
            next_action=_next_action(
                kind="start-audit",
                summary="Start an audit to create the first evidence run.",
                command=_command("audit", repo_root),
            ),
            summary="No readable Quality Runner runs were found.",
            legacy_schema="quality-runner-run-summary-v0.1",
            legacy_status="no-runs",
            history=history_snapshot,
        )
    latest = runs[0]
    latest_run_id = _string(latest.get("run_id"))
    latest_status = _string(latest.get("status")) or "unknown"
    limitations = list(unavailable)
    if latest_status == "unknown":
        limitations.append(
            "The newest run did not contain a readable audit or verification status."
        )
    return _outcome(
        journey="runs",
        state="awaiting-evidence" if latest_status == "unknown" else "complete",
        assessment="history",
        confidence=_confidence(
            level="limited" if limitations else "observed",
            basis=["persisted local run artifacts"],
            limitations=limitations,
        ),
        writes=_history_writes(),
        safety=_history_safety(),
        next_action=_next_action(
            kind="inspect-run",
            summary="Inspect the newest run before acting on its historical status.",
            command=_run_command(repo_root, selected_run_id or latest_run_id),
        ),
        summary=(
            f"Showing {len(runs)} readable run(s); newest status is {latest_status}."
            if latest_status != "unknown"
            else f"Showing {len(runs)} readable run(s), but newest evidence is incomplete."
        ),
        legacy_schema="quality-runner-run-summary-v0.1",
        legacy_status=latest_status,
        run_id=selected_run_id or latest_run_id,
        history=history_snapshot,
    )


def _review_confidence(limitations: list[str]) -> OutcomeConfidence:
    return _confidence(
        level="limited" if limitations else "confirmed",
        basis=["validated packet-bound local response"],
        limitations=limitations,
    )


def _history_snapshot(
    history: HistoryPayload,
    runs: list[LegacyPayload],
    unavailable_run_ids: list[str],
    selected_run_id: str | None,
) -> OutcomeHistory:
    snapshots: list[OutcomeHistoryRun] = []
    for run in runs:
        run_id = _string(run.get("run_id"))
        if run_id is None:
            continue
        snapshot: OutcomeHistoryRun = {
            "run_id": run_id,
            "status": _string(run.get("status")) or "unknown",
        }
        lifecycle_status = _string(run.get("lifecycle_status"))
        if lifecycle_status:
            snapshot["lifecycle_status"] = lifecycle_status
        snapshots.append(snapshot)
    result: OutcomeHistory = {
        "runs": snapshots,
        "truncated": history.get("truncated") is True,
        "unavailable_run_ids": unavailable_run_ids,
    }
    if selected_run_id:
        result["selected_run_id"] = selected_run_id
    return result
