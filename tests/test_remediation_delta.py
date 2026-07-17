from __future__ import annotations

import json
from pathlib import Path

from quality_runner.artifacts import artifact_dir
from quality_runner.cli import main
from quality_runner.remediation_delta import build_remediation_delta


def _write_run(
    repo_root: Path,
    run_id: str,
    *,
    findings: list[dict[str, object]],
    slices: list[dict[str, object]],
    available: list[dict[str, str]],
    preflight: dict[str, object],
    gate: dict[str, object],
) -> None:
    run_dir = artifact_dir(repo_root, run_id)
    run_dir.mkdir(parents=True)
    (run_dir / "quality-audit.json").write_text(
        json.dumps({"findings": findings}), encoding="utf-8"
    )
    (run_dir / "remediation-plan.json").write_text(json.dumps({"slices": slices}), encoding="utf-8")
    (run_dir / "capability-matrix.json").write_text(
        json.dumps({"available": available, "missing": []}), encoding="utf-8"
    )
    (run_dir / "package-manager-preflight.json").write_text(json.dumps(preflight), encoding="utf-8")
    (run_dir / "gate-verification.json").write_text(json.dumps(gate), encoding="utf-8")


def _finding(fingerprint: str, summary: str) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "id": fingerprint,
        "rule_id": "rule-1",
        "file": "src/example.py",
        "severity": "medium",
        "category": "structural",
        "summary": summary,
    }


def _slice(slice_id: str, title: str) -> dict[str, object]:
    return {
        "id": slice_id,
        "title": title,
        "priority": "medium",
        "findings": [{"id": slice_id}],
        "actions": [f"Update {slice_id}"],
        "verification_gates": ["Run focused verification"],
    }


def _preflight(*, warning: bool) -> dict[str, object]:
    return {
        "package_manager": "pnpm",
        "declared_package_manager": "pnpm",
        "lockfiles": ["pnpm-lock.yaml"],
        "nested_lockfiles": [],
        "warnings": [{"code": "changed"}] if warning else [],
    }


def test_remediation_delta_is_tool_neutral_and_tracks_updates(tmp_path: Path) -> None:
    _write_run(
        tmp_path,
        "baseline",
        findings=[_finding("keep", "Still relevant")],
        slices=[_slice("cluster-keep", "Keep cluster")],
        available=[{"id": "tests"}],
        preflight=_preflight(warning=False),
        gate={"status": "passed", "blockers": []},
    )
    _write_run(
        tmp_path,
        "current",
        findings=[_finding("keep", "Still relevant"), _finding("new", "New issue")],
        slices=[_slice("cluster-keep", "Keep cluster"), _slice("cluster-new", "New cluster")],
        available=[{"id": "tests"}, {"id": "lint"}],
        preflight=_preflight(warning=True),
        gate={"status": "failed", "failure_type": "command-failure", "blockers": ["tests"]},
    )

    payload = build_remediation_delta(
        repo_root=tmp_path,
        current_run_id="current",
        baseline_run_id="baseline",
    )

    assert payload["schema"] == "quality-runner-remediation-delta-v0.1"
    assert payload["implementation_allowed"] is False
    assert payload["status"] == "changed"
    assert [item["fingerprint"] for item in payload["findings"]["new"]] == ["new"]
    assert [item["fingerprint"] for item in payload["findings"]["persisted"]] == ["keep"]
    assert [item["id"] for item in payload["slices"]["added"]] == ["cluster-new"]
    assert payload["capabilities"]["added"] == ["lint"]
    assert payload["package_evidence"]["changed"] is True
    assert payload["verification"]["current"]["status"] == "failed"
    assert all("planning" not in str(value) for value in payload["source_artifacts"].values())


def test_remediation_delta_cli_writes_canonical_artifacts_without_planning_files(
    tmp_path: Path, capsys: object
) -> None:
    _write_run(
        tmp_path,
        "baseline",
        findings=[],
        slices=[],
        available=[],
        preflight=_preflight(warning=False),
        gate={"status": "passed", "blockers": []},
    )
    _write_run(
        tmp_path,
        "current",
        findings=[],
        slices=[],
        available=[],
        preflight=_preflight(warning=False),
        gate={"status": "passed", "blockers": []},
    )

    exit_code = main(
        [
            "remediation-delta",
            str(tmp_path),
            "--run-id",
            "current",
            "--baseline-run-id",
            "baseline",
            "--json",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out  # type: ignore[union-attr]
    payload = json.loads(output)
    assert payload["status"] == "unchanged"
    assert (tmp_path / ".quality-runner/runs/current/remediation-delta.json").exists()
    markdown = (tmp_path / ".quality-runner/runs/current/remediation-delta.md").read_text()
    assert "does not create or modify a project plan" in markdown
    assert not (tmp_path / ".planning").exists()
