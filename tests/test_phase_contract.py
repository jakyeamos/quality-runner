from __future__ import annotations

from pathlib import Path

import pytest

from quality_runner.artifacts import artifact_dir
from quality_runner.cli import main
from quality_runner.phase_closure import build_phase_closure
from quality_runner.phase_contract import load_phase_contract, validate_phase_contract
from quality_runner.scan_scope import discover_text_files


def _contract() -> dict[str, object]:
    return {
        "schema": "quality-runner-phase-contract-v0.1",
        "phase_id": "67",
        "plan_id": "67-01",
        "scan_tier": "phase",
        "scope": {"include_paths": ["src/security"]},
        "finding_map": [{"fingerprints": ["keep"], "plan_id": "67-01", "task_id": "T1"}],
        "dispositions": [
            {
                "fingerprint": "keep",
                "status": "accepted-false-positive",
                "reason": "Rule does not match runtime behavior",
                "owner": "security-maintainer",
                "evidence": "reproduced in focused fixture",
            }
        ],
    }


def _finding(fingerprint: str) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "id": fingerprint,
        "rule_id": "security-rule",
        "file": "src/security/auth.py",
        "category": "security",
        "summary": fingerprint,
    }


def test_phase_closure_accepts_evidence_backed_false_positive() -> None:
    payload = build_phase_closure(
        baseline_audit={"findings": []},
        current_audit={"findings": [_finding("keep")]},
        current_ledger={"entries": []},
        contract=_contract(),
    )

    assert payload["status"] == "passed"
    assert payload["counts"]["actionable"] == 0  # type: ignore[index]
    assert payload["counts"]["dispositioned"] == 1  # type: ignore[index]


def test_phase_closure_blocks_unmapped_findings() -> None:
    contract = _contract()
    contract["dispositions"] = []
    payload = build_phase_closure(
        baseline_audit={"findings": []},
        current_audit={"findings": [_finding("new")]},
        current_ledger={"entries": []},
        contract=contract,
    )

    assert payload["status"] == "blocked"
    assert "new" in payload["counts"]
    assert payload["counts"]["unmapped"] == 1  # type: ignore[index]


def test_phase_contract_rejects_accepted_risk() -> None:
    contract = _contract()
    contract["dispositions"] = [{"fingerprint": "x", "status": "accepted-risk"}]
    with pytest.raises(ValueError, match="unsupported accepted disposition"):
        validate_phase_contract(contract)


def test_scoped_discovery_only_reads_declared_paths(tmp_path: Path) -> None:
    (tmp_path / "src/security").mkdir(parents=True)
    (tmp_path / "src/other").mkdir(parents=True)
    (tmp_path / "src/security/auth.py").write_text("token = 'x'\n")
    (tmp_path / "src/other/ignored.py").write_text("token = 'y'\n")

    paths = discover_text_files(
        tmp_path,
        skipped_files=[],
        generated_paths=set(),
        include_ignored_paths=set(),
        scan_exclusions=[],
        max_text_files=10,
        include_paths=("src/security",),
    )

    assert [path.relative_to(tmp_path).as_posix() for path in paths] == ["src/security/auth.py"]


def test_contract_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "phase-contract.json"
    import json

    path.write_text(json.dumps(_contract()), encoding="utf-8")
    assert load_phase_contract(path)["phase_id"] == "67"


def test_phase_check_cli_writes_closure_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    for run_id, findings in (("baseline", []), ("current", [_finding("keep")])):
        run_dir = artifact_dir(tmp_path, run_id)
        run_dir.mkdir(parents=True)
        (run_dir / "quality-audit.json").write_text(json.dumps({"findings": findings}))
        (run_dir / "resolution-ledger.json").write_text(json.dumps({"entries": []}))
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_contract()), encoding="utf-8")

    assert main(
        [
            "phase-check",
            str(tmp_path),
            "--run-id",
            "current",
            "--baseline-run-id",
            "baseline",
            "--contract",
            str(contract_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert (tmp_path / ".quality-runner/runs/current/phase-closure.json").exists()
    assert (tmp_path / ".quality-runner/runs/current/phase-closure.md").exists()
