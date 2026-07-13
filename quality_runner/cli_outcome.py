from __future__ import annotations

from quality_runner.core.outcome_contracts import JourneyOutcome, OutcomeHistory

OUTCOME_SCHEMA = "quality-runner-outcome-v0.2"


def render_outcome(outcome: JourneyOutcome) -> str:
    confidence = outcome["confidence"]
    writes = outcome["writes"]
    safety = outcome["safety"]
    next_action = outcome["next_action"]
    lines = [
        f"{outcome['journey']}: {outcome['state']}",
        f"assessment: {outcome['assessment']}",
        f"confidence: {confidence['level']} — {', '.join(confidence['basis'])}",
        _writes_line(writes["state"], len(writes["artifact_paths"])),
    ]
    history = outcome.get("history")
    if history is not None:
        lines.append(_history_line(history))
    lines.extend(
        [
            f"safety: {safety['mode']} — {safety.get('note', 'no additional safety note')}",
            f"next: {next_action['summary']}",
        ]
    )
    run_id = outcome.get("run_id")
    if run_id:
        lines.insert(1, f"run id: {run_id}")
    limitations = confidence["limitations"]
    if limitations:
        lines.append(f"limitations: {'; '.join(limitations)}")
    command = next_action.get("command")
    if command:
        lines.append(f"command: {command}")
    return "\n".join(lines)


def _writes_line(state: str, artifact_count: int) -> str:
    if state == "none":
        return "writes: no new artifacts"
    noun = "artifact" if artifact_count == 1 else "artifacts"
    return f"writes: {artifact_count} {noun}"


def _history_line(history: OutcomeHistory) -> str:
    details = f"history: {len(history['runs'])} run(s)"
    if history.get("truncated") is True:
        details = f"{details}; truncated"
    if history["unavailable_run_ids"]:
        details = f"{details}; {len(history['unavailable_run_ids'])} unreadable"
    return details
