from __future__ import annotations

import json
from pathlib import Path

import pytest

from quality_runner.review_delta import build_review_delta, persist_review_delta


def _write_run(
    repo_root: Path,
    run_id: str,
    findings: list[dict[str, object]],
    *,
    gate_status: str = "passed",
) -> None:
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "quality-audit.json").write_text(
        json.dumps({"findings": findings}), encoding="utf-8"
    )
    (run_dir / "gate-verification.json").write_text(
        json.dumps({"status": gate_status, "blockers": []}), encoding="utf-8"
    )
    (run_dir / "remediation-plan.json").write_text("{}", encoding="utf-8")
    (run_dir / "agent-handoff.json").write_text("{}", encoding="utf-8")
    (run_dir / "resolution-ledger.json").write_text("{}", encoding="utf-8")


def _finding(fingerprint: str, file: str) -> dict[str, str]:
    return {
        "id": fingerprint,
        "fingerprint": fingerprint,
        "file": file,
        "summary": f"Finding {fingerprint}",
        "category": "structural",
        "severity": "warning",
    }


def _intent() -> dict[str, str]:
    return {"goal": "Implement the requested task"}


def test_review_delta_classifies_new_persisted_resolved_and_out_of_scope(tmp_path: Path) -> None:
    _write_run(
        tmp_path,
        "baseline",
        [_finding("persisted", "src/main.py"), _finding("resolved", "src/old.py")],
    )
    _write_run(
        tmp_path,
        "current",
        [
            _finding("persisted", "src/main.py"),
            _finding("new", "src/new.py"),
            _finding("outside", "docs/old.md"),
        ],
    )

    delta = build_review_delta(
        repo_root=tmp_path,
        run_id="current",
        baseline_run_id="baseline",
        cycle_id="cycle-1",
        iteration=2,
        intent=_intent(),
        changed_paths=["src/main.py", "src/old.py", "src/new.py"],
    )

    assert [item["fingerprint"] for item in delta["findings"]["new"]] == ["new"]
    assert [item["fingerprint"] for item in delta["findings"]["persisted"]] == ["persisted"]
    assert [item["fingerprint"] for item in delta["findings"]["resolved"]] == ["resolved"]
    assert [item["fingerprint"] for item in delta["findings"]["out_of_scope"]] == ["outside"]
    assert delta["continue"] is True
    assert delta["clean"] is False


def test_review_delta_keeps_unrelated_findings_visible_without_blocking(tmp_path: Path) -> None:
    _write_run(tmp_path, "current", [_finding("outside", "docs/old.md")])

    delta = build_review_delta(
        repo_root=tmp_path,
        run_id="current",
        cycle_id="cycle-1",
        iteration=1,
        intent=_intent(),
        changed_paths=["src/main.py"],
    )

    assert delta["clean"] is True
    assert delta["continue"] is False
    assert delta["findings"]["out_of_scope"][0]["fingerprint"] == "outside"


def test_blocked_verification_cannot_be_clean(tmp_path: Path) -> None:
    _write_run(tmp_path, "current", [], gate_status="blocked")

    delta = build_review_delta(
        repo_root=tmp_path,
        run_id="current",
        cycle_id="cycle-1",
        iteration=1,
        intent=_intent(),
        changed_paths=["src/main.py"],
    )

    assert delta["clean"] is False
    assert delta["continue"] is True
    assert delta["stop_reason"] == "verification-blocked"


def test_review_delta_artifacts_are_json_and_markdown(tmp_path: Path) -> None:
    _write_run(tmp_path, "current", [])
    delta = build_review_delta(
        repo_root=tmp_path,
        run_id="current",
        cycle_id="cycle-1",
        iteration=1,
        intent=_intent(),
        changed_paths=["src/main.py"],
    )

    paths = persist_review_delta(repo_root=tmp_path, run_id="current", payload=delta)
    assert json.loads(Path(paths["review_delta_json"]).read_text()) == delta
    markdown = Path(paths["review_delta_md"]).read_text()
    assert "Recommendation: **stop**" in markdown
    assert "New (0)" in markdown


def test_review_delta_rejects_invalid_identity(tmp_path: Path) -> None:
    _write_run(tmp_path, "current", [])
    with pytest.raises(ValueError, match="iteration"):
        build_review_delta(
            repo_root=tmp_path,
            run_id="current",
            cycle_id="cycle-1",
            iteration=0,
            intent=_intent(),
            changed_paths=["src/main.py"],
        )


def test_refresh_parser_exposes_review_loop_flags() -> None:
    from quality_runner.cli import build_parser

    args = build_parser().parse_args(
        [
            "refresh",
            ".",
            "--run-id-prefix",
            "task-001-pass-1",
            "--review-cycle-id",
            "task-001",
            "--review-iteration",
            "1",
            "--intent",
            "Implement the task",
        ]
    )

    assert args.review_cycle_id == "task-001"
    assert args.review_iteration == 1
    assert args.intent == "Implement the task"


def test_refresh_payload_persists_delta_and_manifest_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(tmp_path, "task-001-pass-1-verify", [])
    manifest_path = (
        tmp_path / ".quality-runner" / "runs" / "task-001-pass-1-verify" / "run-manifest.json"
    )
    manifest_path.write_text(
        json.dumps({"schema": "quality-runner-run-manifest-v0.1"}), encoding="utf-8"
    )

    def fake_refresh(**_: object) -> dict[str, object]:
        return {
            "schema": "quality-runner-refresh-result-v0.1",
            "status": "clean",
            "summary": {"run_id": "task-001-pass-1-verify"},
        }

    monkeypatch.setattr("quality_runner.workflow.run_refresh_payload", fake_refresh)
    from quality_runner.workflow import refresh_payload

    payload = refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="task-001-pass-1",
        intent=_intent(),
        review_cycle_id="task-001",
        review_iteration=1,
    )

    assert payload["review_delta"]["stop_reason"] == "no-task-scope-evidence"
    assert payload["review_delta"]["continue"] is True
    assert Path(payload["review_delta_paths"]["review_delta_json"]).exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["review_cycle"]["cycle_id"] == "task-001"
