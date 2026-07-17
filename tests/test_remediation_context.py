from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any


def _slice(
    slice_id: str,
    *,
    domain: str = "general-quality",
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": slice_id,
        "title": f"Remediate {slice_id}",
        "priority": "medium",
        "domain": domain,
        "workstream": "test-workstream",
        "findings": findings
        or [
            {
                "id": f"finding-{slice_id}",
                "file": "src/example.py",
                "line": 12,
                "category": "structural:example",
                "rule_id": "example-rule",
            }
        ],
        "verification_mode": "command",
        "verification_gates": ["python -m pytest"],
        "verification_requirements": [],
        "drift_check": {"command": "git diff --stat HEAD", "paths": ["src/example.py"]},
    }


def _mark_ready(context: dict[str, Any]) -> None:
    records = context["records"]
    for record in records:
        record["status"] = "ready"
        for field in record["required_agent_fields"]:
            record["agent_evidence"][field] = [f"Observed evidence for {field}."]
    context["summary"] = {
        "status": "ready",
        "blocking": False,
        "record_count": len(records),
        "finding_count": len(
            {finding_id for record in records for finding_id in record["finding_ids"]}
        ),
        "ready_count": len(records),
        "pending_count": 0,
        "by_risk_tier": {
            risk_tier: sum(record["risk_tier"] == risk_tier for record in records)
            for risk_tier in {record["risk_tier"] for record in records}
        },
    }


def test_context_groups_findings_and_starts_blocked() -> None:
    from quality_runner.remediation_context import (
        build_remediation_context,
        validate_remediation_context,
    )

    slices = [
        _slice(
            "slice-one",
            findings=[
                {
                    "id": "finding-one",
                    "file": "src/example.py",
                    "line": 12,
                    "category": "structural:example",
                    "rule_id": "example-rule",
                },
                {
                    "id": "finding-two",
                    "file": "src/example.py",
                    "line": 20,
                    "category": "structural:example",
                    "rule_id": "example-rule",
                },
            ],
        )
    ]
    context = build_remediation_context(
        run_id="context-run",
        repo_root=Path("/tmp/context-repo"),
        slices=slices,
    )

    assert len(context["records"]) == 1
    assert context["summary"]["finding_count"] == 2
    assert context["summary"]["pending_count"] == 1
    result = validate_remediation_context(
        context,
        remediation_plan={"slices": slices},
        require_ready=False,
    )
    assert result["passed"] is True, result["errors"]


def test_context_requires_risk_appropriate_evidence_and_fresh_summary() -> None:
    from quality_runner.remediation_context import (
        build_remediation_context,
        validate_remediation_context,
    )

    slices = [
        _slice("local", findings=[_slice("local")["findings"][0]]),
        _slice("high-risk", domain="data-integrity"),
    ]
    context = build_remediation_context(
        run_id="context-run",
        repo_root=None,
        slices=slices,
    )
    pending = validate_remediation_context(
        context,
        remediation_plan={"slices": slices},
        require_ready=True,
    )
    assert pending["passed"] is False
    assert any("not ready" in error for error in pending["errors"])

    _mark_ready(context)
    ready = validate_remediation_context(
        context,
        remediation_plan={"slices": slices},
        require_ready=True,
    )
    assert ready["passed"] is True, ready["errors"]
    assert "impact_map" not in context["records"][0]["required_agent_fields"]
    assert "affected_boundaries" in context["records"][1]["required_agent_fields"]

    context["summary"]["pending_count"] = 1
    stale = validate_remediation_context(
        context,
        remediation_plan={"slices": slices},
        require_ready=True,
    )
    assert stale["passed"] is False
    assert any("summary field pending_count is stale" in error for error in stale["errors"])


def test_context_requires_complete_plan_coverage() -> None:
    from quality_runner.remediation_context import (
        build_remediation_context,
        validate_remediation_context,
    )

    context = build_remediation_context(
        run_id="context-run",
        repo_root=None,
        slices=[_slice("known")],
    )
    result = validate_remediation_context(
        context,
        remediation_plan={"slices": [_slice("known"), _slice("missing")]},
        require_ready=False,
    )
    assert result["passed"] is False
    assert "remediation context missing slice missing" in result["errors"]


def test_validate_context_cli_reports_rejected_pending_packet(tmp_path: Path) -> None:
    from quality_runner.cli_handoff import validate_remediation_context_command_payload
    from quality_runner.remediation_context import build_remediation_context

    context_path = tmp_path / "remediation-context.json"
    plan_path = tmp_path / "remediation-plan.json"
    slices = [_slice("cli-slice")]
    context_path.write_text(
        json.dumps(
            build_remediation_context(
                run_id="context-run",
                repo_root=tmp_path,
                slices=slices,
            )
        ),
        encoding="utf-8",
    )
    plan_path.write_text(json.dumps({"slices": slices}), encoding="utf-8")

    payload = validate_remediation_context_command_payload(
        Namespace(
            context_json=str(context_path),
            remediation_plan=str(plan_path),
        )
    )

    assert payload["schema"] == "quality-runner-validate-remediation-context-result-v0.1"
    assert payload["status"] == "rejected"
    assert payload["implementation_allowed"] is False


def test_handoff_lint_blocks_pending_context_without_plan_argument() -> None:
    from quality_runner.handoff_lint import validate_handoff_quality
    from quality_runner.remediation_context import build_remediation_context

    slices = [_slice("handoff-slice")]
    context = build_remediation_context(
        run_id="context-run",
        repo_root=None,
        slices=slices,
    )
    result = validate_handoff_quality(
        {
            "schema": "quality-runner-agent-handoff-v0.2",
            "implementation_allowed": False,
            "artifact_paths": {},
            "remediation_context": context["summary"],
        },
        remediation_context=context,
    )

    assert result["passed"] is False
    assert any("not ready" in error for error in result["errors"])
