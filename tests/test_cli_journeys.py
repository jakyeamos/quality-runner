from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_support.quality_runner_fixtures import write_js_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_root_help_leads_with_journeys_before_advanced_operations() -> None:
    result = _cli("--help")

    assert result.returncode == 0
    assert result.stdout.startswith("usage: qr <journey> [options]")
    assert result.stdout.index("audit REPO") < result.stdout.index("Advanced operations")
    assert result.stdout.index("review REPO") < result.stdout.index("Advanced operations")
    assert result.stdout.index("verify REPO") < result.stdout.index("Advanced operations")
    assert result.stdout.index("runs REPO") < result.stdout.index("Advanced operations")
    assert result.stdout.index("doctor") < result.stdout.index("Advanced operations")
    assert "verify-gates" in result.stdout
    assert "release-smoke" in result.stdout
    assert "review --legacy-output" in result.stdout


def test_root_help_can_render_the_compatibility_program_name() -> None:
    from quality_runner.cli import build_parser

    help_text = build_parser("quality-runner").format_help()

    assert help_text.startswith("usage: quality-runner <journey> [options]")
    assert "The canonical command is 'qr'" in help_text
    assert "audit REPO" in help_text
    assert "doctor" in help_text


def test_audit_journey_emits_outcome_json_without_changing_legacy_run(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    journey = _cli("audit", str(tmp_path), "--run-id", "journey-audit", "--json")
    legacy = _cli("run", str(tmp_path), "--run-id", "legacy-run", "--json")

    outcome = json.loads(journey.stdout)
    legacy_payload = json.loads(legacy.stdout)
    assert journey.returncode == 0
    assert outcome["schema"] == "quality-runner-outcome-v0.2"
    assert outcome["journey"] == "audit"
    assert outcome["source"] == {
        "legacy_schema": "quality-runner-run-result-v0.1",
        "legacy_status": "planned",
    }
    assert outcome["writes"]["state"] == "artifacts-written"
    assert legacy.returncode == 0
    assert legacy_payload["schema"] == "quality-runner-run-result-v0.1"
    assert "state" not in legacy_payload


def test_verify_journey_reports_evidence_only_block_without_changing_exit_code(
    tmp_path: Path,
) -> None:
    write_js_fixture(tmp_path)

    result = _cli("verify", str(tmp_path), "--run-id", "journey-verify", "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["schema"] == "quality-runner-outcome-v0.2"
    assert payload["journey"] == "verify"
    assert payload["state"] == "blocked"
    assert payload["safety"]["mode"] == "evidence-only"
    assert payload["next_action"]["kind"] == "authorize-verification"
    assert payload["next_action"]["requires_authorization"] is True


def test_runs_journey_reads_existing_history_without_writing_summaries(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    audit = _cli("audit", str(tmp_path), "--run-id", "journey-history", "--json")
    assert audit.returncode == 0

    result = _cli("runs", str(tmp_path), "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["schema"] == "quality-runner-outcome-v0.2"
    assert payload["journey"] == "runs"
    assert payload["assessment"] == "history"
    assert payload["writes"]["state"] == "none"
    assert not (
        tmp_path / ".quality-runner" / "runs" / "journey-history" / "run-summary.json"
    ).exists()


def test_runs_journey_rejects_an_unsafe_selected_run_id(tmp_path: Path) -> None:
    result = _cli("runs", str(tmp_path), "--run-id", "../escape", "--json")

    assert result.returncode == 1
    assert "single path segment" in result.stderr


def test_runs_journey_reports_a_missing_selected_run_as_incomplete_evidence(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    assert _cli("audit", str(tmp_path), "--run-id", "existing-run", "--json").returncode == 0

    result = _cli("runs", str(tmp_path), "--run-id", "missing-run", "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["state"] == "awaiting-evidence"
    assert payload["assessment"] == "evidence-incomplete"
    assert payload["summary"].startswith("The selected run is unavailable or unreadable")
    assert payload["history"]["unavailable_run_ids"] == ["missing-run"]


def test_review_defaults_to_outcome_with_explicit_v1_compatibility(tmp_path: Path) -> None:
    outcome_result = _cli("review", str(tmp_path), "--mode", "blind", "--json")
    outcome_alias = _cli("review", str(tmp_path), "--mode", "blind", "--outcome", "--json")
    legacy = _cli("review", str(tmp_path), "--mode", "blind", "--legacy-output", "--json")

    outcome = json.loads(outcome_result.stdout)
    legacy_payload = json.loads(legacy.stdout)
    assert outcome_result.returncode == 0
    assert outcome["schema"] == "quality-runner-outcome-v0.2"
    assert outcome["journey"] == "review"
    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "packet-ready"
    assert outcome_alias.returncode == 0
    assert json.loads(outcome_alias.stdout)["schema"] == "quality-runner-outcome-v0.2"
    assert legacy.returncode == 0
    assert legacy_payload["schema"] == "quality-runner-review-result-v0.1"
    assert "v1 review projection" in legacy.stderr
    assert "0.7.x" in legacy.stderr

    conflicting = _cli(
        "review",
        str(tmp_path),
        "--mode",
        "blind",
        "--outcome",
        "--legacy-output",
        "--json",
    )
    assert conflicting.returncode == 1
    assert "cannot be combined" in conflicting.stderr


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "quality_runner", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
