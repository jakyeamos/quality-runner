from __future__ import annotations


def test_render_handoff_markdown_includes_next_slice_action_groups() -> None:
    from quality_runner.planning import render_handoff_markdown

    markdown = render_handoff_markdown(
        {
            "schema": "quality-runner-agent-handoff-v0.1",
            "status": "gates-blocked",
            "implementation_allowed": False,
            "artifact_paths": {"agent_handoff_json": "/tmp/agent-handoff.json"},
            "warnings": [],
            "finding_ids": ["gate-lint"],
            "slice_ids": ["resolve-gate-verification-blockers"],
            "next_slice": {
                "id": "resolve-gate-verification-blockers",
                "title": "Resolve dependency setup gate blockers",
                "priority": "high",
                "findings": [
                    {
                        "id": "gate-lint",
                        "severity": "blocker",
                        "category": "gate-verification",
                        "summary": "lint is blocked.",
                    }
                ],
                "actions": [
                    "Resolve dependency-setup blockers first: lint, tests.",
                    "Run dependency setup once for lint, tests: pnpm approve-builds.",
                ],
                "action_groups": [
                    {
                        "class": "dependency-setup",
                        "gate_ids": ["lint", "tests"],
                        "actions": ["Run dependency setup once: pnpm approve-builds."],
                    }
                ],
                "verification_gates": ["Rerun quality-runner verify-gates."],
            },
            "verification_gates": ["Rerun quality-runner verify-gates."],
        }
    )

    assert "### Action Groups" in markdown
    assert "- dependency-setup: lint, tests" in markdown
    assert "  - Run dependency setup once: pnpm approve-builds." in markdown
