from __future__ import annotations

from typing import Any

from quality_runner.security.review_obligations import build_security_review_obligations


def security_review_handoff(
    security_scan: dict[str, Any] | None,
    capability_map: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(security_scan, dict):
        return None
    if security_scan.get("settings", {}).get("enabled") is False:
        return None

    executable_gates = [
        gate
        for gate in security_scan.get("available_capabilities", [])
        if isinstance(gate, dict) and gate.get("capability_kind") == "local_command"
    ]
    missing_gates = security_scan.get("missing_capabilities", [])
    candidates = security_scan.get("candidates", [])
    agent_gates = security_scan.get("agent_review_gates", [])
    obligations = build_security_review_obligations(security_scan)
    return {
        "executable_repo_gates": executable_gates,
        "missing_repo_owned_gates": missing_gates if isinstance(missing_gates, list) else [],
        "security_candidates": candidates if isinstance(candidates, list) else [],
        "agent_review_gates": agent_gates if isinstance(agent_gates, list) else [],
        "review_obligations": obligations["obligations"],
        "review_obligation_count": obligations["obligation_count"],
        "capability_matrix_security_summary": (
            capability_map.get("security_summary") if isinstance(capability_map, dict) else None
        ),
    }


def security_review_markdown(security_review: object) -> list[str]:
    if not isinstance(security_review, dict):
        return []

    lines = [
        "",
        "## Security Review Gates",
        "",
        "These are not deterministic pass/fail checks. They are QR-generated review obligations for the coding agent.",
        "",
    ]

    agent_gates = security_review.get("agent_review_gates")
    if isinstance(agent_gates, list) and agent_gates:
        for gate in agent_gates:
            if not isinstance(gate, dict):
                continue
            gate_id = gate.get("id")
            if not isinstance(gate_id, str):
                continue
            lines.extend([f"### {gate_id}", ""])
            scope = gate.get("scope")
            if isinstance(scope, dict):
                paths = scope.get("paths")
                categories = scope.get("categories")
                if isinstance(paths, list) and paths:
                    lines.append("Scope:")
                    lines.extend(f"- {path}" for path in paths if isinstance(path, str))
                    lines.append("")
                if isinstance(categories, list) and categories:
                    lines.append("Review categories:")
                    lines.extend(
                        f"- {category}" for category in categories if isinstance(category, str)
                    )
                    lines.append("")
            instructions = gate.get("review_instructions")
            if isinstance(instructions, list) and instructions:
                lines.append("Instructions:")
                for index, instruction in enumerate(
                    (item for item in instructions if isinstance(item, str)),
                    start=1,
                ):
                    lines.append(f"{index}. {instruction}")
                lines.append("")
            completion = gate.get("completion_criteria")
            if isinstance(completion, list) and completion:
                lines.append("Completion criteria:")
                lines.extend(f"- {item}" for item in completion if isinstance(item, str))
                lines.append("")
    else:
        lines.extend(["No agent-review security gates for this run.", ""])

    candidates = security_review.get("security_candidates")
    if isinstance(candidates, list) and candidates:
        lines.extend(["## QR-Detected Security Candidates", ""])
        for candidate in candidates[:20]:
            if not isinstance(candidate, dict):
                continue
            lines.append(
                f"- {candidate.get('id')} ({candidate.get('category')}): "
                f"{candidate.get('file')}:{candidate.get('line')}"
            )
        if len(candidates) > 20:
            lines.append(f"- {len(candidates) - 20} additional candidates omitted.")
        lines.append("")

    missing = security_review.get("missing_repo_owned_gates")
    if isinstance(missing, list) and missing:
        lines.extend(["## Missing Repo-Owned Security Gates", ""])
        for gate in missing:
            if not isinstance(gate, dict):
                continue
            gate_id = gate.get("id")
            commands = gate.get("recommended_commands")
            if isinstance(gate_id, str):
                if isinstance(commands, list) and commands:
                    lines.append(f"- {gate_id}: add `{commands[0]}`.")
                else:
                    lines.append(f"- {gate_id}: add a repo-owned security gate.")
        lines.append("")

    return lines
