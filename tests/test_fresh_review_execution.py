from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quality_runner.mcp import call_tool

ROOT = Path(__file__).resolve().parents[1]


def _finding(
    finding_id: str = "R-1", fingerprint: str = "fp-1", severity: str = "high"
) -> dict[str, object]:
    return {
        "id": finding_id,
        "fingerprint": fingerprint,
        "severity": severity,
        "classification": "confirmed",
        "confidence": "high",
        "summary": f"{finding_id} needs attention.",
        "why_it_matters": "The reviewed behavior is not adequately protected.",
        "location": ["src/check.py:1"],
        "evidence": ["src/check.py"],
        "recommended_fix": "Add the missing protection.",
        "agent_prompt": f"Investigate {finding_id} and propose a scoped fix.",
        "human_confirmation_required": True,
        "status": "open",
    }


def _review_result(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "review",
            str(repo_root),
            *arguments,
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=5,
    )


def _review(repo_root: Path, *arguments: str) -> dict[str, object]:
    result = _review_result(repo_root, *arguments)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _run_dir(repo_root: Path, run_id: str) -> Path:
    return repo_root / ".quality-runner" / "runs" / run_id


def _prepared_blind_review(
    repo_root: Path, run_id: str, *, loop: bool = False
) -> tuple[dict[str, object], Path]:
    arguments = ["--mode", "blind", "--run-id", run_id]
    if loop:
        arguments.append("--loop")
    payload = _review(repo_root, *arguments)
    return payload, _run_dir(repo_root, run_id)


def _write_single_response(
    run_dir: Path, *, findings: list[dict[str, object]], **changes: object
) -> Path:
    response = json.loads((run_dir / "review-adapter-response.template.json").read_text())
    response["completed_at"] = "2026-07-12T12:00:00+00:00"
    response["findings"] = findings
    response.update(changes)
    path = run_dir / "review-adapter-response.json"
    path.write_text(json.dumps(response), encoding="utf-8")
    return path


def test_prepare_writes_immutable_packet_and_bound_response_template(tmp_path: Path) -> None:
    payload, run_dir = _prepared_blind_review(tmp_path, "prepare-response")

    assert payload["status"] == "review-not-run"
    assert payload["outcome"] == "packet-ready"
    assert set(payload["artifact_paths"]) == {
        "review_manifest_json",
        "review_context_json",
        "review_report_json",
        "review_report_md",
        "review_agent_packet_md",
        "review_fix_prompts_md",
    }
    template = json.loads((run_dir / "review-adapter-response.template.json").read_text())
    context = json.loads((run_dir / "review-context.json").read_text())
    execution = json.loads((run_dir / "review-execution.json").read_text())

    assert template["run_id"] == "prepare-response"
    assert template["mode"] == "blind"
    assert template["packet_hash"] == context["input_hashes"]["packet"]
    assert execution["state"] == "packet-ready"
    assert execution["input_hashes"] == context["input_hashes"]
    assert not (run_dir / "review-adapter-response.json").exists()


def test_v2_outcome_lists_only_existing_lifecycle_artifacts(tmp_path: Path) -> None:
    outcome = _review(
        tmp_path,
        "--mode",
        "blind",
        "--run-id",
        "outcome-artifacts",
        "--outcome",
    )
    paths = outcome["writes"]["artifact_paths"]

    assert "review_adapter_response_template_json" in paths
    assert "review_execution_json" in paths
    assert "review_adapter_response_json" not in paths
    assert "review_fix_handoff_json" not in paths
    assert all(Path(path).exists() for path in paths.values())


def test_bound_response_finalizes_report_without_mutating_prepared_context(tmp_path: Path) -> None:
    _, run_dir = _prepared_blind_review(tmp_path, "complete-response")
    context_before = (run_dir / "review-context.json").read_text()
    response = _write_single_response(run_dir, findings=[_finding()])

    payload = _review(
        tmp_path,
        "--run-id",
        "complete-response",
        "--adapter-output",
        str(response.relative_to(tmp_path)),
    )

    execution = json.loads((run_dir / "review-execution.json").read_text())
    handoff = json.loads((run_dir / "review-fix-handoff.json").read_text())
    prompts = (run_dir / "review-fix-prompts.md").read_text()

    assert payload["status"] == "review-complete"
    assert payload["report"]["findings"][0]["id"] == "R-1"
    assert "Exclusions are advisory" in payload["evidence_unavailable"][0]
    assert (run_dir / "review-context.json").read_text() == context_before
    assert execution["state"] == "review-complete"
    assert execution["response_provenance"]["packet_hash"]
    assert handoff["status"] == "selection-required"
    assert "select findings" in prompts.lower()


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": "wrong-run"},
        {"packet_hash": "0" * 64},
        {"mode": "task"},
        {"unexpected": True},
        {"evidence_used": [1]},
    ],
)
def test_invalid_adapter_response_never_finalizes_a_review(
    tmp_path: Path, change: dict[str, object]
) -> None:
    _, run_dir = _prepared_blind_review(tmp_path, "invalid-response")
    response = _write_single_response(run_dir, findings=[], **change)

    payload = _review(
        tmp_path,
        "--run-id",
        "invalid-response",
        "--adapter-output",
        str(response.relative_to(tmp_path)),
    )

    execution = json.loads((run_dir / "review-execution.json").read_text())
    persisted_report = json.loads((run_dir / "review-report.json").read_text())

    assert payload["status"] == "malformed-output"
    assert payload["outcome"] == "malformed-output"
    assert execution["state"] == "packet-ready"
    assert persisted_report == payload["report"]
    assert persisted_report["adapter_status"] == "malformed-output"
    attempt = json.loads((run_dir / "review-adapter-attempt.json").read_text())
    assert attempt["status"] == "malformed-output"


def test_adapter_response_rejects_extra_finding_properties(tmp_path: Path) -> None:
    _, run_dir = _prepared_blind_review(tmp_path, "extra-finding-field")
    response = _write_single_response(
        run_dir,
        findings=[{**_finding(), "unexpected": True}],
    )

    payload = _review(
        tmp_path,
        "--run-id",
        "extra-finding-field",
        "--adapter-output",
        str(response.relative_to(tmp_path)),
    )

    assert payload["status"] == "malformed-output"
    assert "unsupported fields" in payload["evidence_unavailable"][0]


def test_combined_review_validates_independent_task_and_blind_responses(tmp_path: Path) -> None:
    task = "SENTINEL TASK: connect the protected route"
    _review(
        tmp_path,
        "--mode",
        "combined",
        "--task",
        task,
        "--run-id",
        "combined-response",
    )
    run_dir = _run_dir(tmp_path, "combined-response")
    context = json.loads((run_dir / "review-context.json").read_text())
    template = json.loads((run_dir / "review-adapter-response.template.json").read_text())
    responses = template["responses"]

    assert context["packets"][0]["mode"] == "task"
    assert context["packets"][0]["task"] == task
    assert context["packets"][1]["mode"] == "blind"
    assert "task" not in context["packets"][1]
    guide = (run_dir / "review-agent-packet.md").read_text()
    task_packet = (run_dir / "review-agent-packet-task.md").read_text()
    blind_packet = (run_dir / "review-agent-packet-blind.md").read_text()
    assert task not in guide
    assert task in task_packet
    assert task not in blind_packet
    assert isinstance(responses, list)
    assert len(responses) == 2
    responses[0]["completed_at"] = "2026-07-12T12:00:00+00:00"
    responses[0]["findings"] = [_finding("T-1", "task-fp")]
    responses[1]["completed_at"] = "2026-07-12T12:01:00+00:00"
    responses[1]["findings"] = [_finding("B-1", "blind-fp", "medium")]
    response_path = run_dir / "review-adapter-response.json"
    response_path.write_text(json.dumps(template), encoding="utf-8")

    payload = _review(
        tmp_path,
        "--run-id",
        "combined-response",
        "--adapter-output",
        str(response_path.relative_to(tmp_path)),
    )

    execution = json.loads((run_dir / "review-execution.json").read_text())

    assert payload["status"] == "review-complete"
    assert {finding["id"] for finding in payload["report"]["findings"]} == {"T-1", "B-1"}
    assert payload["report"]["task_provenance"] == "None"
    assert [item["mode"] for item in execution["response_provenance"]["responses"]] == [
        "task",
        "blind",
    ]


def test_handoff_limits_prompts_to_selected_findings_and_records_loop_state(tmp_path: Path) -> None:
    _, run_dir = _prepared_blind_review(tmp_path, "selected-handoff", loop=True)
    response = _write_single_response(
        run_dir,
        findings=[_finding("H-1", "high-fp", "high"), _finding("M-1", "medium-fp", "medium")],
    )

    payload = _review(
        tmp_path,
        "--run-id",
        "selected-handoff",
        "--adapter-output",
        str(response.relative_to(tmp_path)),
        "--finding-id",
        "H-1",
        "--loop-stop",
        "none",
    )

    handoff = json.loads((run_dir / "review-fix-handoff.json").read_text())
    loop_state = json.loads((run_dir / "review-loop-state.json").read_text())
    prompts = (run_dir / "review-fix-prompts.md").read_text()

    assert payload["status"] == "review-complete"
    assert handoff["status"] == "ready"
    assert handoff["selected_finding_ids"] == ["H-1"]
    assert "review-fix-prompts.md" in payload["next_action"]
    assert "H-1" in prompts
    assert "M-1" not in prompts
    assert loop_state["active_cycle"] is True
    assert loop_state["fixing_agent_status"] == "handoff-ready"
    assert loop_state["stop_condition"] == "none"


def test_adapter_path_escape_is_reported_as_permission_denied(tmp_path: Path) -> None:
    _prepared_blind_review(tmp_path, "path-escape")
    outside = tmp_path.parent / "outside-response.json"
    outside.write_text("{}", encoding="utf-8")

    payload = _review(
        tmp_path,
        "--run-id",
        "path-escape",
        "--adapter-output",
        str(outside),
    )

    assert payload["status"] == "permission-denied"
    assert payload["outcome"] == "permission-denied"


def test_tampered_packet_or_manifest_cannot_finalize_a_review(tmp_path: Path) -> None:
    _, run_dir = _prepared_blind_review(tmp_path, "tampered-packet")
    response = _write_single_response(run_dir, findings=[])
    context_path = run_dir / "review-context.json"
    context = json.loads(context_path.read_text())
    context["repository_state"]["detail"] = "tampered"
    context_path.write_text(json.dumps(context), encoding="utf-8")

    result = _review_result(
        tmp_path,
        "--run-id",
        "tampered-packet",
        "--adapter-output",
        str(response.relative_to(tmp_path)),
    )

    assert result.returncode == 1
    assert "hashes do not match" in result.stderr
    assert json.loads((run_dir / "review-execution.json").read_text())["state"] == "packet-ready"


def test_tampered_combined_parent_cannot_finalize_a_review(tmp_path: Path) -> None:
    _review(
        tmp_path,
        "--mode",
        "combined",
        "--task",
        "Review the guarded route",
        "--run-id",
        "tampered-combined",
    )
    run_dir = _run_dir(tmp_path, "tampered-combined")
    template = json.loads((run_dir / "review-adapter-response.template.json").read_text())
    responses = template["responses"]
    assert isinstance(responses, list)
    for response in responses:
        assert isinstance(response, dict)
        response["completed_at"] = "2026-07-12T12:00:00+00:00"
    response_path = run_dir / "review-adapter-response.json"
    response_path.write_text(json.dumps(template), encoding="utf-8")
    context_path = run_dir / "review-context.json"
    context = json.loads(context_path.read_text())
    context["task"] = "injected parent task"
    context_path.write_text(json.dumps(context), encoding="utf-8")

    result = _review_result(
        tmp_path,
        "--run-id",
        "tampered-combined",
        "--adapter-output",
        str(response_path.relative_to(tmp_path)),
    )

    assert result.returncode == 1
    assert "child-only context" in result.stderr


def test_loop_cannot_be_enabled_after_packet_preparation(tmp_path: Path) -> None:
    _, run_dir = _prepared_blind_review(tmp_path, "late-loop")
    response = _write_single_response(run_dir, findings=[])

    result = _review_result(
        tmp_path,
        "--run-id",
        "late-loop",
        "--adapter-output",
        str(response.relative_to(tmp_path)),
        "--loop",
    )

    assert result.returncode == 1
    assert "selected when preparing" in result.stderr
    assert json.loads((run_dir / "review-execution.json").read_text())["state"] == "packet-ready"


def test_task_file_must_be_regular_and_inside_the_target_repository(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-task.txt"
    outside.write_text("Read external data", encoding="utf-8")
    escaped = _review_result(
        tmp_path,
        "--task-file",
        str(outside),
        "--run-id",
        "outside-task",
    )
    assert escaped.returncode == 1
    assert "inside the target repository" in escaped.stderr

    fifo = tmp_path / "task.fifo"
    os.mkfifo(fifo)
    fifo_result = _review_result(tmp_path, "--task-file", str(fifo), "--run-id", "fifo-task")
    assert fifo_result.returncode == 1
    assert "regular file" in fifo_result.stderr


def test_finalization_lock_releases_after_a_blocked_attempt(tmp_path: Path) -> None:
    _, run_dir = _prepared_blind_review(tmp_path, "locked-response")
    response = _write_single_response(run_dir, findings=[])
    lock = run_dir / ".review-execution.lock"
    with lock.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        blocked = _review_result(
            tmp_path,
            "--run-id",
            "locked-response",
            "--adapter-output",
            str(response.relative_to(tmp_path)),
        )
        assert blocked.returncode == 1
        assert "already being finalized" in blocked.stderr

    completed = _review(
        tmp_path,
        "--run-id",
        "locked-response",
        "--adapter-output",
        str(response.relative_to(tmp_path)),
    )
    assert completed["status"] == "review-complete"


def test_mcp_prepare_and_response_use_the_same_two_phase_contract(tmp_path: Path) -> None:
    prepared = call_tool(
        "quality_runner_review",
        {"repo_root": str(tmp_path), "mode": "blind", "run_id": "mcp-response"},
    )["structuredContent"]
    run_dir = _run_dir(tmp_path, "mcp-response")
    response = _write_single_response(run_dir, findings=[])

    completed = call_tool(
        "quality_runner_review",
        {
            "repo_root": str(tmp_path),
            "run_id": "mcp-response",
            "adapter_output": str(response.relative_to(tmp_path)),
        },
    )["structuredContent"]

    assert prepared["status"] == "review-not-run"
    assert completed["status"] == "review-complete"
    assert completed["report"]["findings"] == []
