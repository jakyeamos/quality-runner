from __future__ import annotations

from pathlib import Path
from shlex import quote

from quality_runner.core.outcome_contracts import (
    JourneyOutcome,
    OutcomeAssessment,
    OutcomeConfidence,
    OutcomeConfidenceLevel,
    OutcomeHistory,
    OutcomeJourney,
    OutcomeNextAction,
    OutcomeNextActionKind,
    OutcomeSafety,
    OutcomeSafetyMode,
    OutcomeState,
    OutcomeWrites,
)

type LegacyPayload = dict[str, object]


def _outcome(
    *,
    journey: OutcomeJourney,
    state: OutcomeState,
    assessment: OutcomeAssessment,
    confidence: OutcomeConfidence,
    writes: OutcomeWrites,
    safety: OutcomeSafety,
    next_action: OutcomeNextAction,
    summary: str,
    payload: LegacyPayload | None = None,
    legacy_schema: str | None = None,
    legacy_status: str | None = None,
    run_id: str | None = None,
    history: OutcomeHistory | None = None,
) -> JourneyOutcome:
    source_schema = (
        legacy_schema or _string(payload.get("schema") if payload else None) or "unknown"
    )
    source_status = legacy_status or _status(payload or {})
    outcome: JourneyOutcome = {
        "schema": "quality-runner-outcome-v0.2",
        "journey": journey,
        "state": state,
        "assessment": assessment,
        "confidence": confidence,
        "writes": writes,
        "safety": safety,
        "next_action": next_action,
        "summary": summary,
        "source": {"legacy_schema": source_schema, "legacy_status": source_status},
    }
    if run_id:
        outcome["run_id"] = run_id
    if history is not None:
        outcome["history"] = history
    return outcome


def _confidence(
    *,
    level: OutcomeConfidenceLevel,
    basis: list[str],
    limitations: list[str],
) -> OutcomeConfidence:
    return {"level": level, "basis": basis, "limitations": limitations}


def _writes(payload: LegacyPayload, *, branch_switched: bool) -> OutcomeWrites:
    artifact_paths = _artifact_paths(payload)
    return {
        "source_worktree": "branch-switched" if branch_switched else "unchanged",
        "state": "artifacts-written" if artifact_paths else "none",
        "artifact_paths": artifact_paths,
    }


def _history_writes() -> OutcomeWrites:
    return {"source_worktree": "unchanged", "state": "none", "artifact_paths": {}}


def _safety(
    *,
    mode: OutcomeSafetyMode,
    commands_executed: bool,
    requires_explicit_authorization: bool,
    note: str,
    source_worktree_mutated: bool = False,
) -> OutcomeSafety:
    return {
        "mode": mode,
        "commands_executed": commands_executed,
        "source_worktree_mutated": source_worktree_mutated,
        "requires_explicit_authorization": requires_explicit_authorization,
        "note": note,
    }


def _history_safety() -> OutcomeSafety:
    return _safety(
        mode="read-only-history",
        commands_executed=False,
        requires_explicit_authorization=False,
        note="Run history reads persisted artifacts and does not write new summaries.",
    )


def _next_action(
    *,
    kind: OutcomeNextActionKind,
    summary: str,
    command: str | None = None,
    requires_authorization: bool = False,
) -> OutcomeNextAction:
    action: OutcomeNextAction = {
        "kind": kind,
        "summary": summary,
        "requires_authorization": requires_authorization,
    }
    if command:
        action["command"] = command
    return action


def _execution_details(verification: LegacyPayload | None) -> _ExecutionDetails:
    if verification is None:
        return _ExecutionDetails(isolated=False, commands_executed=False)
    context = _object(verification.get("verification_context"))
    gates = _object_list(verification.get("gates"))
    commands_executed = any(gate.get("status") in {"passed", "failed"} for gate in gates)
    isolated = (
        commands_executed
        and verification.get("execute_discovered_gates") is True
        and context.get("execution_authorized") is True
        and context.get("worktree_mode") == "disposable"
        and context.get("mutations_isolated") is True
    )
    return _ExecutionDetails(isolated=isolated, commands_executed=commands_executed)


def _usable_verification(verification: LegacyPayload | None) -> LegacyPayload | None:
    if verification is None:
        return None
    if verification.get("schema") != "quality-runner-gate-verification-v0.1":
        return None
    status = verification.get("status")
    if status not in {"passed", "failed", "blocked", "skipped-nonlocal"}:
        return None
    timeout_seconds = verification.get("timeout_seconds")
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or timeout_seconds < 1
    ):
        return None
    gates_value = verification.get("gates")
    if not isinstance(gates_value, list):
        return None
    gates = _object_list(gates_value)
    if len(gates) != len(gates_value):
        return None
    if any(
        _string(gate.get("id")) is None or gate.get("status") not in {"passed", "failed", "skipped"}
        for gate in gates
    ):
        return None
    if status == "passed" and not any(gate.get("status") == "passed" for gate in gates):
        return None
    if status == "failed" and not any(gate.get("status") == "failed" for gate in gates):
        return None
    if status == "skipped-nonlocal" and (
        not gates or any(gate.get("status") != "skipped" for gate in gates)
    ):
        return None
    return verification


def _verification_matches_result(
    result_status: str,
    verification: LegacyPayload | None,
) -> bool:
    if verification is None:
        return False
    expected_status = "passed" if result_status == "passed-with-findings" else result_status
    return verification.get("status") == expected_status


def _verify_confidence(
    execution: _ExecutionDetails,
    verification: LegacyPayload | None,
) -> OutcomeConfidence:
    if verification is None:
        return _confidence(
            level="limited",
            basis=["verification result envelope"],
            limitations=["Gate verification artifact was unavailable."],
        )
    limitations = _unexecuted_gate_limitations(verification)
    if execution.commands_executed:
        if not execution.isolated:
            limitations.append("Recorded execution did not prove disposable worktree isolation.")
            return _confidence(
                level="limited",
                basis=["executed gate evidence"],
                limitations=limitations,
            )
        return _confidence(
            level="limited" if limitations else "confirmed",
            basis=["executed disposable gate evidence"],
            limitations=limitations,
        )
    return _confidence(
        level="limited",
        basis=["discovered gate plan"],
        limitations=_gate_limitations(verification),
    )


def _requires_verification_authorization(verification: LegacyPayload | None) -> bool:
    if verification is None:
        return False
    return any(
        gate.get("skip_type") == "execution-consent-required"
        for gate in _object_list(verification.get("gates"))
    )


def _gate_limitations(verification: LegacyPayload) -> list[str]:
    limitations: list[str] = []
    for gate in _object_list(verification.get("gates")):
        reason = _string(gate.get("reason"))
        if reason and reason not in limitations:
            limitations.append(reason)
    return limitations or ["No gate command was executed."]


def _unexecuted_gate_limitations(verification: LegacyPayload) -> list[str]:
    limitations: list[str] = []
    for gate in _object_list(verification.get("gates")):
        if gate.get("status") in {"passed", "failed"}:
            continue
        reason = _string(gate.get("reason"))
        gate_id = _string(gate.get("id")) or "unnamed gate"
        limitation = reason or f"{gate_id} did not produce local execution evidence."
        if limitation not in limitations:
            limitations.append(limitation)
    return limitations


def _review_finding_count(payload: LegacyPayload) -> int:
    report = _object(payload.get("report"))
    findings = report.get("findings")
    return len(findings) if isinstance(findings, list) else 0


def _warning_messages(payload: LegacyPayload) -> list[str]:
    messages: list[str] = []
    for warning in _object_list(payload.get("warnings")):
        message = _string(warning.get("message"))
        if message and message not in messages:
            messages.append(message)
    return messages


def _artifact_paths(payload: LegacyPayload) -> dict[str, str]:
    value = _object(payload.get("artifact_paths"))
    return {key: path for key, path in value.items() if isinstance(path, str) and path}


def _run_id(payload: LegacyPayload) -> str | None:
    return _string(payload.get("run_id"))


def _status(payload: LegacyPayload) -> str:
    return _string(payload.get("status")) or "unknown"


def _command(journey: str, repo_root: Path) -> str:
    return f"quality-runner {journey} {quote(str(repo_root))}"


def _handoff_command(repo_root: Path, run_id: str | None) -> str | None:
    if run_id is None:
        return None
    return f"quality-runner export-handoff {quote(str(repo_root))} --run-id {quote(run_id)}"


def _run_command(repo_root: Path, run_id: str | None) -> str | None:
    if run_id is None:
        return None
    return f"quality-runner runs {quote(str(repo_root))} --run-id {quote(run_id)}"


def _authorize_verification_command(repo_root: Path, run_id: str | None) -> str:
    command = f"quality-runner verify {quote(str(repo_root))}"
    if run_id is not None:
        command = f"{command} --run-id {quote(run_id)}"
    return f"{command} --execute-gates --worktree-mode disposable"


def _object(value: object) -> LegacyPayload:
    return value if isinstance(value, dict) else {}


def _object_list(value: object) -> list[LegacyPayload]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


class _ExecutionDetails:
    def __init__(self, *, isolated: bool, commands_executed: bool) -> None:
        self.isolated = isolated
        self.commands_executed = commands_executed
