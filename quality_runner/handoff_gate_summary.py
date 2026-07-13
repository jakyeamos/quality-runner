from __future__ import annotations

from typing import Any

from quality_runner.timeout_diagnostics import timeout_diagnostics_markdown


def action_group_markdown(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    lines = ["", "### Action Groups", ""]
    for group in value:
        if not isinstance(group, dict):
            continue
        blocker_class = group.get("class")
        gate_ids = group.get("gate_ids")
        actions = group.get("actions")
        finding_ids = group.get("finding_ids")
        if not isinstance(blocker_class, str):
            continue
        ids_source = gate_ids if isinstance(gate_ids, list) else finding_ids
        ids = (
            [gate_id for gate_id in ids_source if isinstance(gate_id, str) and gate_id]
            if isinstance(ids_source, list)
            else []
        )
        if not ids:
            continue
        lines.append(f"- {blocker_class}: {', '.join(ids)}")
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, str) and action:
                    lines.append(f"  - {action}")
    return lines if len(lines) > 3 else []


def build_gate_verification_summary(
    *,
    gate_verification: dict[str, Any] | None,
    finding_count: int,
    missing_capability_count: int,
) -> dict[str, Any] | None:
    if not isinstance(gate_verification, dict):
        return None
    status = _string_or_none(gate_verification.get("status"))
    if status is None:
        return None
    failure_type = _string_or_none(gate_verification.get("failure_type"))
    gates = _gate_summaries(gate_verification)
    blockers = _gate_blockers(gates)
    primary_blocker_class = _primary_blocker_class(blockers)
    return {
        "status": status,
        "recommended_classification": _recommended_gate_classification(
            status=status,
            failure_type=failure_type,
            gates=gates,
            missing_capability_count=missing_capability_count,
            finding_count=finding_count,
        ),
        **_optional_string("failure_type", failure_type),
        **_optional_string("primary_blocker_class", primary_blocker_class),
        "blocker_groups": _blocker_groups(blockers),
        "blockers": blockers,
    }


def gate_handoff_status(gate_summary: dict[str, Any] | None) -> str | None:
    if not isinstance(gate_summary, dict):
        return None
    status = gate_summary.get("status")
    if status == "blocked":
        return "gates-blocked"
    if status == "failed":
        return "gates-failed"
    return None


def gate_blocker_slice(gate_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(gate_summary, dict):
        return None
    if gate_summary.get("status") not in {"blocked", "failed"}:
        return None
    blockers = gate_summary.get("blockers")
    if not isinstance(blockers, list) or not blockers:
        return None
    primary_blocker_class = _string_or_none(gate_summary.get("primary_blocker_class"))
    return {
        "id": "resolve-gate-verification-blockers",
        "title": _gate_blocker_title(primary_blocker_class),
        "priority": "high",
        "findings": [_gate_blocker_finding(gate) for gate in blockers],
        "actions": _grouped_gate_blocker_actions(gate_summary, blockers),
        "action_groups": _gate_blocker_action_groups(gate_summary, blockers),
        "verification_gates": [
            "Address the gate blockers listed in the handoff gate verification section.",
            "Rerun quality-runner verify-gates and confirm the gate verification status is passed.",
        ],
    }


def gate_verification_markdown(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    lines = [
        "## Gate Verification",
        "",
        f"- Status: {value.get('status')}",
        f"- Recommended classification: {value.get('recommended_classification')}",
    ]
    primary = value.get("primary_blocker_class")
    if isinstance(primary, str):
        lines.append(f"- Primary blocker class: {primary}")
    failure_type = value.get("failure_type")
    if isinstance(failure_type, str):
        lines.append(f"- Failure type: {failure_type}")
    groups = value.get("blocker_groups")
    if isinstance(groups, list) and groups:
        lines.extend(["", "### Gate Blocker Groups", ""])
        for group in groups:
            if not isinstance(group, dict):
                continue
            blocker_class = group.get("class")
            gate_ids = group.get("gate_ids")
            if isinstance(blocker_class, str) and isinstance(gate_ids, list):
                ids = ", ".join(str(gate_id) for gate_id in gate_ids)
                lines.append(f"- {blocker_class}: {ids}")
    lines.extend(["", "### Gate Blockers", ""])
    blockers = value.get("blockers")
    if isinstance(blockers, list) and blockers:
        for gate in blockers:
            if not isinstance(gate, dict):
                continue
            line = f"- {gate.get('id')}: {gate.get('status')}"
            failure_type = gate.get("failure_type")
            skip_type = gate.get("skip_type")
            if isinstance(failure_type, str):
                line += f" ({failure_type})"
            elif isinstance(skip_type, str):
                line += f" ({skip_type})"
            blocked_by = gate.get("blocked_by")
            if isinstance(blocked_by, str):
                line += f"; blocked by {blocked_by}"
            lines.append(line + ".")
            setup = gate.get("dependency_setup")
            if isinstance(setup, dict) and isinstance(setup.get("setup_command"), str):
                lines.append(f"  - Setup: `{setup['setup_command']}`")
            recommended = gate.get("recommended_action")
            if isinstance(recommended, str) and recommended:
                lines.append(f"  - Action: {recommended}")
            lines.extend(timeout_diagnostics_markdown(gate.get("timeout_diagnostics")))
    else:
        lines.append("No gate blockers.")
    return lines


def _gate_summaries(gate_verification: dict[str, Any]) -> list[dict[str, Any]]:
    gates = gate_verification.get("gates")
    if not isinstance(gates, list):
        return []
    summaries: list[dict[str, Any]] = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gate_id = _string_or_none(gate.get("id"))
        status = _string_or_none(gate.get("status"))
        if gate_id is None or status is None:
            continue
        summaries.append(
            {
                "id": gate_id,
                "status": status,
                **_optional_string("failure_type", gate.get("failure_type")),
                **_optional_string("skip_type", gate.get("skip_type")),
                **_optional_string("blocked_by", gate.get("blocked_by")),
                **_optional_string("command", gate.get("command")),
                **_optional_string("recommended_action", gate.get("recommended_action")),
                **_optional_value("dependency_setup", _dependency_setup(gate)),
                **_optional_value("timeout_diagnostics", _timeout_diagnostics(gate)),
                "blocker_class": _blocker_class(gate),
            }
        )
    return summaries


def _dependency_setup(gate: dict[str, Any]) -> dict[str, str] | None:
    diagnostics = gate.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return None
    setup = diagnostics.get("dependency_setup")
    if not isinstance(setup, dict):
        return None
    normalized = {
        key: value
        for key, value in setup.items()
        if key in {"package_manager", "setup_command", "reason"}
        and isinstance(value, str)
        and value
    }
    return normalized or None


def _timeout_diagnostics(gate: dict[str, Any]) -> dict[str, Any] | None:
    diagnostics = gate.get("timeout_diagnostics")
    return diagnostics if isinstance(diagnostics, dict) else None


def _gate_blockers(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [gate for gate in gates if _is_gate_blocker(gate)]


def _is_gate_blocker(gate: dict[str, Any]) -> bool:
    status = gate.get("status")
    failure_type = gate.get("failure_type")
    skip_type = gate.get("skip_type")
    return (
        status == "failed"
        or failure_type
        in {
            "command-failed",
            "environment-restricted",
            "dependency-setup-blocker",
            "read-only-mutation",
            "workflow-timeout",
        }
        or skip_type
        in {"dependency-setup-blocked", "mutating-gate-not-run", "execution-consent-required"}
    )


def _recommended_gate_classification(
    *,
    status: str,
    failure_type: str | None,
    gates: list[dict[str, Any]],
    missing_capability_count: int,
    finding_count: int,
) -> str:
    if failure_type == "workflow-timeout":
        return "workflow-timeout-blocker"
    if any(gate.get("failure_type") == "environment-restricted" for gate in gates):
        return "environment-or-runner-blocker"
    if any(
        gate.get("failure_type") == "dependency-setup-blocker"
        or gate.get("skip_type") == "dependency-setup-blocked"
        for gate in gates
    ):
        return "environment-or-dependency-blocker"
    if any(
        gate.get("skip_type") == "mutating-gate-not-run"
        or gate.get("failure_type") == "read-only-mutation"
        for gate in gates
    ):
        return "read-only-gate-blocker"
    if any(gate.get("skip_type") == "execution-consent-required" for gate in gates):
        return "execution-consent-required"
    if status == "failed":
        return "failing-executable-gates"
    if missing_capability_count > 0:
        return "missing-capabilities"
    if finding_count > 0:
        return "broad-repo-debt"
    if status in {"passed", "clean"}:
        return "clean"
    return "needs-triage"


def _gate_blocker_finding(gate: dict[str, Any]) -> dict[str, str]:
    gate_id = str(gate.get("id"))
    failure_type = _string_or_none(gate.get("failure_type"))
    skip_type = _string_or_none(gate.get("skip_type"))
    return {
        "id": f"gate-{gate_id}",
        "severity": "blocker",
        "category": "gate-verification",
        "summary": f"{gate_id} is {gate.get('status')} ({failure_type or skip_type or 'gate blocker'}).",
    }


def _gate_blocker_actions(blockers: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for gate in blockers:
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id:
            continue
        setup = gate.get("dependency_setup")
        if isinstance(setup, dict) and isinstance(setup.get("setup_command"), str):
            actions.append(f"Run dependency setup for {gate_id}: {setup['setup_command']}.")
            continue
        recommended = gate.get("recommended_action")
        if isinstance(recommended, str) and recommended:
            if gate.get("blocker_class") == "workflow-timeout":
                actions.append(f"{recommended}.")
                continue
            actions.append(f"For {gate_id}, {recommended}.")
            continue
        command = gate.get("command")
        if isinstance(command, str) and command:
            actions.append(f"Run `{command}` directly and fix the {gate_id} failure it reports.")
        else:
            actions.append(f"Resolve the {gate_id} gate blocker.")
    return actions or ["Resolve the blocked or failed gate verification result."]


def _blocker_class(gate: dict[str, Any]) -> str:
    failure_type = gate.get("failure_type")
    skip_type = gate.get("skip_type")
    if failure_type == "dependency-setup-blocker" or skip_type == "dependency-setup-blocked":
        return "dependency-setup"
    if failure_type == "environment-restricted":
        return "environment"
    if failure_type == "read-only-mutation" or skip_type == "mutating-gate-not-run":
        return "read-only-policy"
    if skip_type == "execution-consent-required":
        return "execution-consent"
    if failure_type == "workflow-timeout":
        return "workflow-timeout"
    if failure_type == "command-failed" or gate.get("status") == "failed":
        return "command-failure"
    return "other"


def _primary_blocker_class(blockers: list[dict[str, Any]]) -> str | None:
    classes = {_blocker_class(gate) for gate in blockers}
    for blocker_class in (
        "dependency-setup",
        "environment",
        "read-only-policy",
        "execution-consent",
        "workflow-timeout",
        "command-failure",
        "other",
    ):
        if blocker_class in classes:
            return blocker_class
    return None


def _blocker_groups(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for blocker_class in (
        "dependency-setup",
        "environment",
        "read-only-policy",
        "execution-consent",
        "workflow-timeout",
        "command-failure",
        "other",
    ):
        group = [gate for gate in blockers if _blocker_class(gate) == blocker_class]
        if not group:
            continue
        groups.append(
            {
                "class": blocker_class,
                "gate_ids": [
                    str(gate["id"])
                    for gate in group
                    if isinstance(gate.get("id"), str) and gate["id"]
                ],
            }
        )
    return groups


def _gate_blocker_title(primary_blocker_class: str | None) -> str:
    titles = {
        "dependency-setup": "Resolve dependency setup gate blockers",
        "environment": "Resolve environment-restricted gate blockers",
        "read-only-policy": "Resolve read-only gate policy blockers",
        "execution-consent": "Authorize or retain evidence-only gate verification",
        "workflow-timeout": "Resolve workflow timeout blockers",
        "command-failure": "Resolve failing executable gates",
    }
    return titles.get(primary_blocker_class or "", "Resolve gate verification blockers")


def _grouped_gate_blocker_actions(
    gate_summary: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> list[str]:
    action_groups = _gate_blocker_action_groups(gate_summary, blockers)
    if action_groups:
        return [
            action
            for group in action_groups
            for action in [
                f"Resolve {group['class']} blockers first: {', '.join(group['gate_ids'])}.",
                *[
                    _display_group_action(action=group_action, gate_ids=group["gate_ids"])
                    for group_action in group["actions"]
                ],
            ]
        ]
    return _gate_blocker_actions(blockers)


def _gate_blocker_action_groups(
    gate_summary: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups = gate_summary.get("blocker_groups")
    if not isinstance(groups, list) or not groups:
        return []
    action_groups: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        blocker_class = group.get("class")
        group_blockers = [
            gate
            for gate in blockers
            if isinstance(blocker_class, str) and gate.get("blocker_class") == blocker_class
        ]
        if not group_blockers:
            continue
        group_actions = _deduped_group_actions(group_blockers)
        if not group_actions:
            continue
        action_groups.append(
            {
                "class": blocker_class,
                "gate_ids": _gate_ids(group_blockers),
                "actions": group_actions,
            }
        )
    return action_groups


def _deduped_group_actions(blockers: list[dict[str, Any]]) -> list[str]:
    setup_actions = _deduped_dependency_setup_actions(blockers)
    if setup_actions:
        return setup_actions + _non_dependency_gate_actions(blockers)
    return _gate_blocker_actions(blockers)


def _deduped_dependency_setup_actions(blockers: list[dict[str, Any]]) -> list[str]:
    setup_groups: dict[str, list[str]] = {}
    for gate in blockers:
        setup = gate.get("dependency_setup")
        if not isinstance(setup, dict):
            continue
        setup_command = setup.get("setup_command")
        if not isinstance(setup_command, str) or not setup_command:
            continue
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id:
            continue
        setup_groups.setdefault(setup_command, []).append(gate_id)
    return [
        f"Run dependency setup once: {setup_command}."
        for setup_command, gate_ids in setup_groups.items()
        if gate_ids
    ]


def _non_dependency_gate_actions(blockers: list[dict[str, Any]]) -> list[str]:
    non_dependency_blockers = [
        gate for gate in blockers if not isinstance(gate.get("dependency_setup"), dict)
    ]
    if not non_dependency_blockers:
        return []
    return _gate_blocker_actions(non_dependency_blockers)


def _display_group_action(*, action: object, gate_ids: object) -> str:
    if not isinstance(action, str):
        return ""
    if (
        action.startswith("Run dependency setup once: ")
        and isinstance(gate_ids, list)
        and all(isinstance(gate_id, str) for gate_id in gate_ids)
    ):
        return action.replace(
            "Run dependency setup once: ",
            f"Run dependency setup once for {', '.join(gate_ids)}: ",
            1,
        )
    return action


def _gate_ids(blockers: list[dict[str, Any]]) -> list[str]:
    return [str(gate["id"]) for gate in blockers if isinstance(gate.get("id"), str) and gate["id"]]


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_string(key: str, value: object) -> dict[str, str]:
    if isinstance(value, str) and value:
        return {key: value}
    return {}


def _optional_value(key: str, value: object) -> dict[str, object]:
    if value is None:
        return {}
    return {key: value}
