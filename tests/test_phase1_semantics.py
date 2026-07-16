from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quality_runner.actionability import actionability_for_finding, enrich_audit_findings
from quality_runner.intent import build_intent_packet, load_intent_file, resolve_workflow_intent
from quality_runner.lifecycle_status import compute_lifecycle_status
from quality_runner.run_summary import build_run_summary
from quality_runner.workflow import run_payload


def test_build_intent_packet_includes_goal_and_metadata() -> None:
    packet = build_intent_packet(
        run_id="run-001",
        goal="Add --json to status",
        source="cli",
        supplied_by="user",
        constraints=["Keep text output"],
    )
    assert packet["schema"] == "quality-runner-intent-v0.1"
    assert packet["goal"] == "Add --json to status"
    assert packet["constraints"] == ["Keep text output"]


def test_load_intent_file_requires_repo_local_path(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(
        json.dumps({"goal": "Ship feature", "constraints": ["No breaking changes"]}),
        encoding="utf-8",
    )
    packet = load_intent_file(
        repo_root=tmp_path,
        run_id="run-001",
        intent_file=intent_path,
    )
    assert packet["goal"] == "Ship feature"
    assert packet["constraints"] == ["No breaking changes"]


def test_load_intent_file_rejects_outside_repo(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-intent.json"
    outside.write_text(json.dumps({"goal": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError, match="inside the target repository"):
        load_intent_file(
            repo_root=tmp_path,
            run_id="run-001",
            intent_file=outside,
        )


def test_actionability_maps_capability_findings() -> None:
    actionability, _ = actionability_for_finding(
        {
            "category": "capability",
            "severity": "blocker",
            "summary": "Required quality capability is missing: tests.",
        }
    )
    assert actionability == "needs-maintainer-policy"


def test_actionability_maps_integrate_findings_to_author_decision() -> None:
    actionability, rationale = actionability_for_finding(
        {
            "category": "structural:integrate",
            "severity": "warning",
            "summary": "1 stub-implementation partial work finding requires author disposition.",
        }
    )

    assert actionability == "needs-author-decision"
    assert "wire" in rationale


def test_enrich_audit_findings_adds_actionability() -> None:
    findings = enrich_audit_findings(
        [
            {
                "id": "missing-tests",
                "severity": "blocker",
                "category": "capability",
                "summary": "missing tests",
                "recommended_fix": "add tests",
                "verification": ["rerun"],
            }
        ]
    )
    assert findings[0]["actionability"] == "needs-maintainer-policy"
    assert "actionability_rationale" in findings[0]


def test_compute_lifecycle_status_merge_ready_with_ci(tmp_path: Path) -> None:
    status = compute_lifecycle_status(
        summary_status="passed",
        handoff_status="gates-clean",
        gate_verification={"status": "passed"},
        audit={"status": "findings"},
        repo_scan={
            "ci_checks": [
                {
                    "name": "Quality / Lint",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "abc123",
                    "ref": "main",
                    "workflow_run_id": "run-1",
                    "captured_at": datetime.now(UTC).isoformat(),
                }
            ],
            "git_provenance": {"head_sha": "abc123", "branch": "main"},
        },
    )
    assert status == "merge-ready"


def test_run_payload_writes_intent_and_actionability(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    payload = run_payload(
        repo_root=tmp_path,
        run_id="intent-run",
        intent=resolve_workflow_intent(
            repo_root=tmp_path,
            run_id="intent-run",
            goal="Baseline audit before edits",
        ),
    )
    run_dir = Path(payload["artifact_paths"]["quality_audit_json"]).parent
    audit = json.loads((run_dir / "quality-audit.json").read_text())
    handoff = json.loads((run_dir / "agent-handoff.json").read_text())
    manifest = json.loads((run_dir / "run-manifest.json").read_text())
    assert (run_dir / "intent.json").exists()
    assert manifest["intent"]["goal"] == "Baseline audit before edits"
    assert handoff["intent"]["goal"] == "Baseline audit before edits"
    assert handoff["lifecycle_status"] in {
        "audit-clean",
        "gates-clean",
        "needs-triage",
        "merge-ready",
    }
    if audit["findings"]:
        assert "actionability" in audit["findings"][0]


def test_build_run_summary_includes_lifecycle_status(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    payload = run_payload(repo_root=tmp_path, run_id="summary-run")
    summary = build_run_summary(repo_root=tmp_path, run_id="summary-run", persist=False)
    assert "lifecycle_status" in summary
    assert summary["run_id"] == payload["run_id"]
