from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from quality_runner.review_adapters import FileReviewAdapter, NoReviewAdapter

ROOT = Path(__file__).resolve().parents[1]


def _finding() -> dict[str, object]:
    return {
        "id": "R-1",
        "fingerprint": "fp-1",
        "severity": "high",
        "classification": "confirmed",
        "confidence": "high",
        "summary": "A required check is missing.",
        "why_it_matters": "The acceptance criteria are not enforced.",
        "location": ["src/check.py:1"],
        "evidence": ["src/check.py"],
        "recommended_fix": "Add the check.",
        "agent_prompt": "Inspect the check boundary and propose a fix.",
        "human_confirmation_required": True,
        "status": "open",
    }


def test_no_adapter_is_explicitly_packet_only() -> None:
    result = NoReviewAdapter().review({"run_id": "run"}, Path("/tmp/run"))
    assert result["status"] == "review-not-run"
    assert result["report"] is None


def test_file_adapter_validates_local_report(tmp_path: Path) -> None:
    from quality_runner.application.review_responses import response_template
    from quality_runner.review_context import build_review_context, normalize_review_options

    packet = build_review_context(
        repo_root=tmp_path,
        run_id="run",
        options=normalize_review_options(
            mode="blind", scope="project", breadth="related", task=None
        ),
    )
    response = response_template(packet)
    response["completed_at"] = "2026-07-12T12:00:00+00:00"
    response["findings"] = [_finding()]
    output = tmp_path / "report.json"
    output.write_text(json.dumps(response), encoding="utf-8")
    result = FileReviewAdapter(output).review(packet, tmp_path)
    assert result["status"] == "review-complete"
    report = result["report"]
    assert report is not None
    assert report["severity_counts"] == {"critical": 0, "high": 1, "medium": 0, "low": 0}


def test_combined_file_adapter_preserves_v1_task_provenance(tmp_path: Path) -> None:
    from quality_runner.review_context import build_review_context, normalize_review_options

    output = tmp_path / "combined-report.json"
    packet = build_review_context(
        repo_root=tmp_path,
        run_id="combined-adapter-report",
        options=normalize_review_options(
            mode="combined",
            scope="project",
            breadth="related",
            task="Review the integration boundary",
        ),
    )
    from quality_runner.application.review_responses import response_template

    response = response_template(packet)
    responses = response["responses"]
    assert isinstance(responses, list)
    assert len(responses) == 2
    responses[0]["completed_at"] = "2026-07-12T12:00:00+00:00"
    responses[0]["findings"] = [_finding()]
    responses[1]["completed_at"] = "2026-07-12T12:01:00+00:00"
    responses[1]["findings"] = []
    output.write_text(json.dumps(response), encoding="utf-8")

    result = FileReviewAdapter(output).review(packet, tmp_path)

    assert result["status"] == "review-complete"
    assert result["report"] is not None
    assert result["report"]["task_provenance"] == "None"


def test_file_adapter_rejects_unbound_legacy_payload(tmp_path: Path) -> None:
    from quality_runner.review_context import build_review_context, normalize_review_options

    output = tmp_path / "report.json"
    output.write_text(json.dumps({"findings": [_finding()]}), encoding="utf-8")
    packet = build_review_context(
        repo_root=tmp_path,
        run_id="unbound-response",
        options=normalize_review_options(
            mode="blind", scope="project", breadth="related", task=None
        ),
    )

    result = FileReviewAdapter(output).review(packet, tmp_path)

    assert result["status"] == "malformed-output"


def test_file_adapter_rejects_path_escape(tmp_path: Path) -> None:
    output = tmp_path.parent / "outside.json"
    output.write_text("{}", encoding="utf-8")
    result = FileReviewAdapter(output).review({"run_id": "run"}, tmp_path)
    assert result["status"] == "permission-denied"


def test_review_cli_requires_task_or_blind_mode(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "review", str(tmp_path), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "--mode blind" in result.stderr


def test_review_cli_reports_packet_only_outcome_json(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "review",
            str(tmp_path),
            "--mode",
            "blind",
            "--run-id",
            "cli-review",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-outcome-v0.2"
    assert payload["journey"] == "review"
    assert payload["state"] == "awaiting-evidence"
    assert payload["assessment"] == "packet-ready"
    assert payload["next_action"]["kind"] == "provide-review-output"
    assert "review_report_json" in payload["writes"]["artifact_paths"]
