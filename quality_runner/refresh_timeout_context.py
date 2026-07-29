from __future__ import annotations


def timeout_context(
    *,
    phase: str,
    execute_discovered_gates: bool,
    refresh_context: dict[str, object],
    timeout_reason: str,
) -> dict[str, str]:
    if phase == "verify-gates":
        command_timeout = execute_discovered_gates and "gate command" in timeout_reason.lower()
        mode = "gate-command-execution" if command_timeout else "read-only-gate-discovery"
        analysis_source = (
            "fresh-gate-analysis"
            if command_timeout
            else str(refresh_context.get("analysis_source") or "fresh-read-only-audit")
        )
    else:
        mode = f"{phase}-analysis"
        analysis_source = str(refresh_context.get("analysis_source") or "unknown")
    return {"mode": mode, "analysis_source": analysis_source}
