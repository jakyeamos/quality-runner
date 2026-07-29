from __future__ import annotations

import sys
from pathlib import Path

import pytest

from quality_runner import task_readiness
from quality_runner.task_readiness import (
    evaluate_readiness,
    required_gate_failures,
    run_certified_gates,
)


def _gate(command: str, **overrides: object) -> dict[str, object]:
    return {
        "id": "fixture",
        "command": command,
        "state": "certified",
        "required": True,
        "owner": "quality",
        "rationale": "fixture",
        "bootstrap": "system Python fixture",
        "mutation_risk": "read-only",
        "scope": "fixture",
        "timeout_seconds": 10,
        "environment_paths": [],
        "evidence_refs": [
            "failure-fixture:tests/test_task_readiness.py",
            "repeat-pass:tests/test_task_readiness.py",
            "local:tests/test_task_readiness.py",
            "ci:.github/workflows/ci.yml",
        ],
        **overrides,
    }


def test_candidate_gate_remains_advisory(tmp_path: Path) -> None:
    readiness = evaluate_readiness(
        repo_root=tmp_path,
        prevention={"gates": [_gate(f"{sys.executable} --version", state="candidate")]},
    )

    assert readiness["gates"][0]["state"] == "candidate"


def test_missing_required_tool_is_unavailable_and_blocks(tmp_path: Path) -> None:
    readiness = evaluate_readiness(
        repo_root=tmp_path,
        prevention={"gates": [_gate("definitely-missing-quality-runner-command")]},
    )
    _results, blockers = run_certified_gates(
        snapshot_root=tmp_path,
        repo_root=tmp_path,
        readiness=readiness,
    )

    assert readiness["gates"][0]["state"] == "unavailable"
    assert blockers[0]["code"] == "required_gate_not_certified"


def test_incomplete_certification_evidence_is_blocked(tmp_path: Path) -> None:
    readiness = evaluate_readiness(
        repo_root=tmp_path,
        prevention={"gates": [_gate(f"{sys.executable} --version", evidence_refs=[])]},
    )

    assert readiness["gates"][0]["state"] == "blocked"
    assert "missing certification evidence" in readiness["gates"][0]["blocker"]


def test_missing_repeatability_evidence_blocks_nondeterministic_candidate(
    tmp_path: Path,
) -> None:
    evidence = [
        "failure-fixture:tests/test_task_readiness.py",
        "local:tests/test_task_readiness.py",
        "ci:.github/workflows/ci.yml",
    ]
    readiness = evaluate_readiness(
        repo_root=tmp_path,
        prevention={"gates": [_gate(f"{sys.executable} --version", evidence_refs=evidence)]},
    )

    assert readiness["gates"][0]["state"] == "blocked"
    assert "repeat-pass" in readiness["gates"][0]["blocker"]


def test_unverifiable_version_blocks_certification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(task_readiness, "_command_version", lambda *_args: None)

    readiness = evaluate_readiness(
        repo_root=tmp_path,
        prevention={"gates": [_gate(f"{sys.executable} --version")]},
    )

    assert readiness["gates"][0]["state"] == "blocked"
    assert "verifiable version" in readiness["gates"][0]["blocker"]


def test_certified_gate_pass_and_intentional_failure(tmp_path: Path) -> None:
    passing = evaluate_readiness(
        repo_root=tmp_path,
        prevention={"gates": [_gate(f"{sys.executable} -c \"print('ok')\"")]},
    )
    pass_results, blockers = run_certified_gates(
        snapshot_root=tmp_path,
        repo_root=tmp_path,
        readiness=passing,
    )
    assert blockers == []
    assert pass_results[0]["status"] == "passed"

    failing = evaluate_readiness(
        repo_root=tmp_path,
        prevention={"gates": [_gate(f'{sys.executable} -c "raise SystemExit(7)"')]},
    )
    fail_results, blockers = run_certified_gates(
        snapshot_root=tmp_path,
        repo_root=tmp_path,
        readiness=failing,
    )
    assert blockers == []
    assert fail_results[0]["status"] == "failed"
    assert required_gate_failures(fail_results) == fail_results


def test_certified_gate_timeout_is_unknown_evidence(tmp_path: Path) -> None:
    readiness = evaluate_readiness(
        repo_root=tmp_path,
        prevention={
            "gates": [
                _gate(
                    f'{sys.executable} -c "import time; time.sleep(2)"',
                    timeout_seconds=1,
                )
            ]
        },
    )
    results, blockers = run_certified_gates(
        snapshot_root=tmp_path,
        repo_root=tmp_path,
        readiness=readiness,
    )

    assert results[0]["status"] == "timeout"
    assert blockers[0]["code"] == "gate_evidence_unknown"


def test_bootstrap_or_permission_failure_is_blocked_not_policy_violation(
    tmp_path: Path,
) -> None:
    readiness = evaluate_readiness(
        repo_root=tmp_path,
        prevention={
            "gates": [
                _gate(
                    f'{sys.executable} -c "import sys; '
                    "sys.stderr.write('Failed to initialize cache: Operation not permitted'); "
                    'raise SystemExit(2)"'
                )
            ]
        },
    )

    results, blockers = run_certified_gates(
        snapshot_root=tmp_path,
        repo_root=tmp_path,
        readiness=readiness,
    )

    assert results[0]["status"] == "blocked"
    assert blockers[0]["code"] == "gate_evidence_unknown"
    assert required_gate_failures(results) == []


def test_gate_environment_isolates_git_config_and_preserves_bootstrap_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UV_CACHE_DIR", "/documented/bootstrap/cache")

    environment = task_readiness._gate_environment(tmp_path, [])

    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_CONFIG_SYSTEM"] == "/dev/null"
    assert environment["XDG_CONFIG_HOME"].endswith("xdg-config")
    assert environment["UV_CACHE_DIR"] == "/documented/bootstrap/cache"
