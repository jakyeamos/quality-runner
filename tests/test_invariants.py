from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from quality_runner.gate_verification import verification_status
from quality_runner.invariants import (
    apply_invariant_status,
    build_invariant_report,
)
from quality_runner.workflow import verify_gates_payload


def test_configured_invariant_is_discovered_with_an_arbitrary_stable_id(
    tmp_path: Path,
) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.config import load_repo_config
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "queue-ui.mjs").write_text("export const queue = [];\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/queue-ui.test.mjs").write_text("// proof\n", encoding="utf-8")
    _write_config(tmp_path, enforcement="required")

    config = load_repo_config(tmp_path)
    scan = inspect_repo(tmp_path, run_id="invariant-discovery")
    packet = compile_standards(
        repo_root=tmp_path,
        scan=scan,
        profile="default",
        config=config,
    )
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)
    invariant = next(
        item
        for item in _objects(capability_map["available"])
        if item["id"] == "human-only-review-not-reusable"
    )

    assert config["invariants"] == [
        {
            "id": "human-only-review-not-reusable",
            "description": "Handoff-only prompts never enter the reusable answer queue.",
            "owner": "application-review-classifier",
            "surfaces": ["queue-ui.mjs", "tests/queue-ui.test.mjs"],
            "command": f'{sys.executable} -c "raise SystemExit(0)"',
            "enforcement": "required",
            "ecosystem": "javascript",
            "mutating_risk": "safe",
            "freshness_days": 30,
        }
    ]
    assert invariant["capability_kind"] == "semantic_invariant"
    assert invariant["enforcement"] == "required"
    assert invariant["required_by"] == "repository-invariant"


def test_required_invariant_with_missing_proof_surface_is_reported_missing(
    tmp_path: Path,
) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    _write_config(tmp_path, enforcement="required")
    scan = inspect_repo(tmp_path, run_id="invariant-missing-proof")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)
    missing = {
        item["id"]: item
        for item in _objects(capability_map["missing"])
    }

    assert missing["human-only-review-not-reusable"]["type"] == "invariant"
    assert "queue-ui.mjs" in str(
        missing["human-only-review-not-reusable"]["reason"]
    )


def test_invalid_and_duplicate_invariants_fail_closed_with_config_warnings(
    tmp_path: Path,
) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "",
                "[[quality_runner.invariants]]",
                'id = "valid-invariant"',
                'description = "A valid invariant."',
                'owner = "quality"',
                'surfaces = ["tests/proof.test"]',
                'command = "run proof"',
                "",
                "[[quality_runner.invariants]]",
                'id = "valid-invariant"',
                'description = "Duplicate invariant."',
                'owner = "quality"',
                'surfaces = ["tests/other.test"]',
                'command = "run other proof"',
                "",
                "[[quality_runner.invariants]]",
                'id = "Invalid ID"',
                'description = "Unsafe invariant."',
                'owner = "quality"',
                'surfaces = ["../outside"]',
                'command = "run unsafe proof"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert [item["id"] for item in _objects(config["invariants"])] == ["valid-invariant"]
    warning_messages = [
        str(item["message"]) for item in _objects(config["warnings"])
    ]
    assert any("duplicates 'valid-invariant'" in message for message in warning_messages)
    assert any("kebab-case id" in message for message in warning_messages)


def test_invariant_report_distinguishes_pass_fail_block_unknown_and_stale(
    tmp_path: Path,
) -> None:
    surface = tmp_path / "surface.txt"
    surface.write_text("proof surface\n", encoding="utf-8")
    base = {
        "id": "durable-behavior",
        "description": "Behavior stays durable.",
        "owner": "quality",
        "surfaces": ["surface.txt"],
        "command": "check behavior",
        "enforcement": "required",
        "ecosystem": "repository",
        "mutating_risk": "safe",
        "freshness_days": 7,
    }
    config = {"invariants": [base]}
    now = datetime(2026, 7, 29, tzinfo=UTC)

    assert _status(tmp_path, config, {"status": "passed"}, now) == "passed"
    assert _status(
        tmp_path,
        config,
        {"status": "failed", "failure_type": "command-failed"},
        now,
    ) == "failed"
    assert _status(
        tmp_path,
        config,
        {"status": "failed", "failure_type": "environment-restricted"},
        now,
    ) == "blocked"
    assert _status(tmp_path, config, None, now) == "unknown"

    evidence = tmp_path / "invariant-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "quality-runner-invariant-evidence-v0.1",
                "id": "durable-behavior",
                "status": "passed",
                "checked_at": "2026-07-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    config["invariants"] = [{**base, "evidence_file": "invariant-evidence.json"}]
    assert _status(tmp_path, config, None, now) == "stale"


def test_advisory_invariant_results_do_not_block_repository_gate_status() -> None:
    advisory_failure = {
        "id": "advisory-behavior",
        "status": "failed",
        "enforcement": "advisory",
    }
    assert verification_status([advisory_failure]) == "passed"

    required_report = {
        "schema": "quality-runner-invariant-verification-v0.1",
        "status": "unknown",
        "summary": {},
        "invariants": [
            {
                "id": "required-behavior",
                "enforcement": "required",
                "status": "unknown",
            }
        ],
    }
    applied = apply_invariant_status({"status": "passed"}, required_report)
    assert applied["status"] == "blocked"


def test_verify_executes_required_invariant_and_writes_dedicated_artifact(
    tmp_path: Path,
) -> None:
    (tmp_path / "queue-ui.mjs").write_text("export const queue = [];\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/queue-ui.test.mjs").write_text("// proof\n", encoding="utf-8")
    _write_config(tmp_path, enforcement="required")
    _init_git_repo(tmp_path)

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="semantic-invariant-execution",
        execute_discovered_gates=True,
        worktree_mode="disposable",
        only_gate_ids=("human-only-review-not-reusable",),
    )
    artifact_paths = _object(payload["artifact_paths"])
    report = _json(Path(str(artifact_paths["invariant_verification_json"])))
    verification = _json(Path(str(artifact_paths["gate_verification_json"])))

    assert report["status"] == "passed"
    assert _objects(report["invariants"])[0]["status"] == "passed"
    assert verification["status"] == "passed"
    assert _object(verification["invariant_verification"])["status"] == "passed"


def _write_config(repo: Path, *, enforcement: str) -> None:
    command = f'{sys.executable} -c "raise SystemExit(0)"'
    (repo / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "required_capabilities = []",
                "",
                "[[quality_runner.invariants]]",
                'id = "human-only-review-not-reusable"',
                'description = "Handoff-only prompts never enter the reusable answer queue."',
                'owner = "application-review-classifier"',
                'surfaces = ["queue-ui.mjs", "tests/queue-ui.test.mjs"]',
                f"command = {json.dumps(command)}",
                f'enforcement = "{enforcement}"',
                'ecosystem = "javascript"',
                'mutating_risk = "safe"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _status(
    repo: Path,
    config: dict[str, object],
    gate: dict[str, object] | None,
    now: datetime,
) -> str:
    verification = (
        {
            "gates": [
                {
                    "id": "durable-behavior",
                    **gate,
                }
            ]
        }
        if gate is not None
        else None
    )
    report = build_invariant_report(
        repo_root=repo,
        config=config,
        gate_verification=verification,
        now=now,
    )
    return str(_objects(report["invariants"])[0]["status"])


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=quality-runner@example.com",
            "-c",
            "user.name=Quality Runner",
            "commit",
            "-m",
            "Add invariant fixture",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _json(path: Path) -> dict[str, object]:
    return _object(json.loads(path.read_text(encoding="utf-8")))


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _objects(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [_object(item) for item in value]
