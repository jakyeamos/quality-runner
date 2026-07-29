from __future__ import annotations

import json
from pathlib import Path

import pytest

from quality_runner.refresh_timeout import resolve_refresh_timeout_contract
from quality_runner.refresh_workflow import run_refresh_payload
from quality_runner.timeout_baseline import (
    TIMEOUT_BASELINE_SCHEMA,
    load_timeout_baseline,
    record_timeout_sample,
    resolve_timeout_context,
    timeout_baseline_path,
)

GATE_PLAN = [{"id": "tests", "command": ["pytest"], "timeout_seconds": 120}]


def _phase_timings(
    inspect: float = 10.0,
    run: float = 20.0,
    verify: float = 40.0,
) -> dict[str, dict[str, object]]:
    return {
        "inspect": {"status": "inspected", "elapsed_seconds": inspect},
        "run": {"status": "findings", "elapsed_seconds": run},
        "verify": {"status": "passed", "elapsed_seconds": verify},
    }


def _record(
    repo_root: Path,
    run_number: int,
    *,
    phase_timings: dict[str, dict[str, object]] | None = None,
    gate_plan: object = GATE_PLAN,
    execute: bool = True,
    overlay: object | None = None,
    timed_out: bool = False,
    focus_paths: list[str] | None = None,
    cache_state: str = "not-configured",
) -> dict[str, object]:
    return record_timeout_sample(
        repo_root,
        run_id_prefix=f"calibration-{run_number}",
        profile="default",
        per_gate_timeout_seconds=120,
        phase_timings=phase_timings or _phase_timings(),
        summary={"status": "passed"},
        execute_discovered_gates=execute,
        scan_exclusion_overlay=overlay,
        timed_out=timed_out,
        gate_plan=gate_plan,
        focus_paths=focus_paths,
        cache_state=cache_state,
    )


def _activate_baseline(repo_root: Path) -> None:
    for run_number in range(1, 4):
        result = _record(repo_root, run_number)
        assert result["status"] == "recorded"


def test_first_run_is_candidate_and_three_matching_runs_activate(tmp_path: Path) -> None:
    first = _record(tmp_path, 1)

    assert first["state"] == "candidate"
    baseline_path = timeout_baseline_path(tmp_path)
    baseline = load_timeout_baseline(tmp_path)
    assert baseline is not None
    assert baseline["schema"] == TIMEOUT_BASELINE_SCHEMA
    assert baseline["sample_count"] == 1
    assert baseline["phase_timings"]["inspect"]["elapsed_seconds"] == 10.0  # type: ignore[index]
    assert baseline["candidate_timeouts"] == {  # type: ignore[comparison-overlap]
        "inspect": 30,
        "run": 40,
        "verify": 120,
        "total": 219,
    }
    assert baseline_path.exists()

    _record(repo_root=tmp_path, run_number=2)
    third = _record(repo_root=tmp_path, run_number=3)

    assert third["state"] == "active"
    assert third["sample_count"] == 3
    baseline = load_timeout_baseline(tmp_path)
    assert baseline is not None
    assert baseline["state"] == "active"
    assert baseline["learned_timeouts"] == {  # type: ignore[comparison-overlap]
        "inspect": 30,
        "run": 30,
        "verify": 120,
        "total": 207,
    }
    context = resolve_timeout_context(
        tmp_path,
        profile="default",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
        gate_plan=GATE_PLAN,
    )
    assert context["status"] == "active"
    assert context["source"] == "adaptive-baseline"
    assert context["timeouts"] == baseline["learned_timeouts"]
    assert context["identity_sha256"] == baseline["identity"]["sha256"]  # type: ignore[index]


def test_active_budget_uses_rolling_p95_and_conservative_total(tmp_path: Path) -> None:
    _record(tmp_path, 1, phase_timings=_phase_timings(10, 20, 30))
    _record(tmp_path, 2, phase_timings=_phase_timings(20, 30, 40))
    _record(tmp_path, 3, phase_timings=_phase_timings(30, 40, 50))

    baseline = load_timeout_baseline(tmp_path)
    assert baseline is not None
    assert baseline["learned_timeouts"] == {  # type: ignore[comparison-overlap]
        "inspect": 45,
        "run": 60,
        "verify": 120,
        "total": 259,
    }


def test_timeout_and_partial_runs_do_not_update_an_active_baseline(tmp_path: Path) -> None:
    _activate_baseline(tmp_path)
    before = load_timeout_baseline(tmp_path)
    assert before is not None

    timed_out = _record(tmp_path, 4, timed_out=True)
    partial = _record(
        tmp_path,
        5,
        phase_timings={
            **_phase_timings(),
            "verify": {"status": "not-started", "elapsed_seconds": 0.0},
        },
    )

    assert timed_out["status"] == "skipped"
    assert partial["status"] == "skipped"
    after = load_timeout_baseline(tmp_path)
    assert after is not None
    assert after["state"] == before["state"]
    assert after["sample_count"] == before["sample_count"]
    assert after["identity"] == before["identity"]


def test_profile_config_gitignore_inventory_and_gate_plan_invalidate_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _activate_baseline(tmp_path)

    (tmp_path / ".gitignore").write_text("ignored-output/\n", encoding="utf-8")
    stale_gitignore = resolve_timeout_context(
        tmp_path,
        profile="default",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
        gate_plan=GATE_PLAN,
    )
    assert stale_gitignore["status"] == "fallback"

    (tmp_path / ".gitignore").unlink()
    (tmp_path / "new-source.py").write_text("print('new')\n", encoding="utf-8")
    stale_inventory = resolve_timeout_context(
        tmp_path,
        profile="default",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
        gate_plan=GATE_PLAN,
    )
    assert stale_inventory["status"] == "fallback"

    (tmp_path / "new-source.py").unlink()
    stale_profile = resolve_timeout_context(
        tmp_path,
        profile="ci",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
        gate_plan=GATE_PLAN,
    )
    assert stale_profile["status"] == "fallback"

    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nscan_exclusions = ["generated-output/**"]\n',
        encoding="utf-8",
    )
    stale_config = resolve_timeout_context(
        tmp_path,
        profile="default",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
        gate_plan=GATE_PLAN,
    )
    assert stale_config["status"] == "fallback"

    (tmp_path / ".quality-runner.toml").unlink()
    import quality_runner.timeout_baseline_support as baseline_support

    monkeypatch.setattr(baseline_support, "__version__", "0.6.0-test-version")
    stale_version = resolve_timeout_context(
        tmp_path,
        profile="default",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
        gate_plan=GATE_PLAN,
    )
    assert stale_version["status"] == "fallback"

    monkeypatch.setattr(baseline_support, "__version__", "0.6.0")
    matching = resolve_timeout_context(
        tmp_path,
        profile="default",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
        gate_plan=GATE_PLAN,
    )
    assert matching["status"] == "active"
    changed_plan = resolve_timeout_context(
        tmp_path,
        profile="default",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
        gate_plan=[*GATE_PLAN, {"id": "lint", "command": ["ruff"]}],
    )
    assert changed_plan["status"] == "fallback"


def test_explicit_timeout_flags_override_adaptive_values() -> None:
    contract = resolve_refresh_timeout_contract(
        per_gate_timeout_seconds=120,
        workflow_timeout_seconds=None,
        verify_timeout_seconds=8,
        workflow_timeout_reason=None,
        total_timeout_seconds=9,
        total_timeout_reason=None,
        inspect_timeout_seconds=7,
        run_timeout_seconds=None,
        adaptive={
            "status": "active",
            "timeouts": {"inspect": 100, "run": 110, "verify": 120, "total": 400},
            "baseline_id": "baseline-1",
            "identity_sha256": "identity-1",
            "sample_count": 3,
        },
    )

    assert contract["inspect_timeout_seconds"] == 7
    assert contract["inspect_timeout_source"] == "explicit"
    assert contract["run_timeout_seconds"] == 110
    assert contract["run_timeout_source"] == "adaptive"
    assert contract["verify_timeout_seconds"] == 8
    assert contract["verify_timeout_source"] == "explicit"
    assert contract["total_timeout_seconds"] == 9
    assert contract["total_timeout_source"] == "explicit"
    assert contract["source"] == "explicit"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"timed_out": True}, "timed-out"),
        ({"execute": False}, "consent"),
        ({"overlay": ["generated-output"]}, "run-only"),
        ({"focus_paths": ["src/changed.py"]}, "focused"),
        ({"cache_state": "ambiguous"}, "ambiguous"),
    ],
)
def test_ineligible_runs_never_write_or_update_baseline(
    tmp_path: Path,
    kwargs: dict[str, object],
    reason: str,
) -> None:
    result = _record(tmp_path, 1, **kwargs)  # type: ignore[arg-type]

    assert result["status"] == "skipped"
    assert reason in str(result["reason"])
    assert not timeout_baseline_path(tmp_path).exists()


def test_invalid_baseline_falls_back(tmp_path: Path) -> None:
    path = timeout_baseline_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"state": "active", "learned_timeouts": {}}), encoding="utf-8")

    context = resolve_timeout_context(
        tmp_path,
        profile="default",
        per_gate_timeout_seconds=120,
        scan_exclusion_overlay=None,
    )

    assert context["status"] == "fallback"
    assert "schema" in str(context["reason"])
    contract = resolve_refresh_timeout_contract(
        per_gate_timeout_seconds=120,
        workflow_timeout_seconds=None,
        verify_timeout_seconds=None,
        workflow_timeout_reason=None,
        total_timeout_seconds=None,
        total_timeout_reason=None,
        adaptive=context,
    )
    assert contract["source"] == "fixed-default"
    assert contract["inspect_timeout_seconds"] == 360
    assert contract["run_timeout_seconds"] == 360
    assert contract["verify_timeout_seconds"] == 360
    assert contract["total_timeout_seconds"] is None


def test_custom_exclusions_require_a_matching_validated_preflight(tmp_path: Path) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nscan_exclusions = ["generated-output/**"]\n',
        encoding="utf-8",
    )

    result = _record(tmp_path, 1)

    assert result["status"] == "skipped"
    assert "validated preflight" in str(result["reason"])


def test_refresh_workflow_records_only_complete_executed_runs(tmp_path: Path) -> None:
    def inspect_stub(**_: object) -> dict[str, object]:
        return {"status": "inspected"}

    def run_stub(**_: object) -> dict[str, object]:
        return {"status": "findings"}

    def verify_stub(**kwargs: object) -> dict[str, object]:
        repo_root = kwargs["repo_root"]
        run_id = kwargs["run_id"]
        assert isinstance(repo_root, Path)
        assert isinstance(run_id, str)
        run_dir = repo_root / ".quality-runner" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "gate-execution-plan.json").write_text(
            json.dumps(GATE_PLAN) + "\n", encoding="utf-8"
        )
        return {"status": "passed"}

    def summary_stub(**_: object) -> dict[str, object]:
        return {"status": "passed"}

    def refresh(run_number: int, *, focus_paths: list[str] | None = None) -> dict[str, object]:
        return run_refresh_payload(
            repo_root=tmp_path,
            run_id_prefix=f"workflow-calibration-{run_number}",
            baseline_run_id=None,
            profile="default",
            ci_status_json=None,
            timeout_seconds=120,
            workflow_timeout_seconds=None,
            verify_timeout_seconds=None,
            workflow_timeout_reason=None,
            total_timeout_seconds=None,
            total_timeout_reason=None,
            checkout_most_advanced_branch=False,
            execute_discovered_gates=True,
            allow_mutating_gates=False,
            worktree_mode="in-place",
            allow_dirty_worktree_verify=False,
            intent=None,
            inspect_callback=inspect_stub,
            run_callback=run_stub,
            verify_callback=verify_stub,
            summary_callback=summary_stub,
            focus_paths=focus_paths,
        )

    first = refresh(1)
    second = refresh(2)
    third = refresh(3)

    assert first["timeout_contract"]["baseline_recording"]["state"] == "candidate"  # type: ignore[index]
    assert second["timeout_contract"]["baseline_recording"]["sample_count"] == 2  # type: ignore[index]
    assert third["timeout_contract"]["baseline_recording"]["state"] == "active"  # type: ignore[index]
    assert load_timeout_baseline(tmp_path)["state"] == "active"  # type: ignore[index]

    focused = refresh(4, focus_paths=["src/changed.py"])
    assert focused["timeout_contract"]["baseline_recording"]["status"] == "skipped"  # type: ignore[index]
    assert load_timeout_baseline(tmp_path)["sample_count"] == 3  # type: ignore[index]
