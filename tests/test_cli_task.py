from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path, *, large: bool = False, extra_policy: str = "") -> Path:
    _git(tmp_path, "clone", "--quiet", "--no-checkout", str(ROOT), ".")
    source = "\n".join(f"value_{index} = {index}" for index in range(8 if large else 2)) + "\n"
    (tmp_path / "app.py").write_text(source, encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.structural_scan]",
                "large_file_lines = 5",
                "similarity_enabled = false",
                "",
                "[quality_runner.prevention]",
                'required_modules = ["code_quality"]',
                "",
                "[[quality_runner.prevention.rules]]",
                'detector = "code_quality"',
                'rule_id = "large-source-file"',
                'state = "behavior-verified"',
                'owner = "quality"',
                'rationale = "Large source files increase review cost."',
                'evidence_refs = ["positive:tests/fixtures/large.py", "negative:tests/fixtures/small.py", "ambiguous:tests/fixtures/generated.py"]',
                'paths = ["**/*.py", "*.py"]',
                # Debloat is intentionally low-confidence; this fixture opts in to
                # enforcing it so the end-to-end violation path remains covered.
                "confidence_threshold = 0.3",
                "",
                extra_policy,
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def _qr(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "quality_runner", "task", *args, str(repo), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "QUALITY_RUNNER_DOGFOOD_STATE_DIR": str(repo / ".quality-runner" / "test-dogfood"),
        },
    )


def test_task_clean_check_passes_and_writes_canonical_artifacts(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    start = _qr(repo, "start", "--task-id", "clean")
    check = _qr(repo, "check", "--task-id", "clean")

    assert start.returncode == 0
    assert check.returncode == 0
    payload = json.loads(check.stdout)
    assert payload["status"] == "pass"
    assert payload["mode"] == "authoritative"
    assert payload["release_enforcement"] == "advisory"
    assert payload["release_readiness"]["status"] == "ready"
    assert payload["release_readiness"]["eligible"] is True
    assert all(payload["release_readiness"]["criteria"].values())
    assert "remaining repository-required checks" in payload["next_action"]
    assert payload["delta"]["counts"]["new_enforced"] == 0
    assert payload["analysis"]["analysis_mode"] == "full"
    assert payload["analysis"]["cache_mode"] == "external"
    assert payload["analysis"]["cache_summary"]["analyses"]["code_quality"]["cache_hits"] > 0
    assert payload["analysis"]["performance"]["elapsed_seconds"] >= 0
    run_dir = repo / ".quality-runner" / "runs" / payload["run_id"]
    assert (run_dir / "task-check.json").is_file()
    assert (run_dir / "task-check.md").is_file()
    assert "Release readiness: **ready**" in (run_dir / "task-check.md").read_text()


def test_task_release_check_requires_eligible_authoritative_evidence(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert _qr(repo, "start", "--task-id", "release-clean").returncode == 0

    check = _qr(repo, "release-check", "--task-id", "release-clean")
    payload = json.loads(check.stdout)

    assert check.returncode == 0
    assert payload["status"] == "pass"
    assert payload["mode"] == "authoritative"
    assert payload["release_enforcement"] == "required"
    assert payload["release_readiness"]["eligible"] is True
    assert "release evidence passes" in payload["next_action"]
    record = json.loads((repo / ".quality-runner" / "tasks" / "release-clean.json").read_text())
    assert record["last_release_enforcement"] == "required"


def test_task_release_check_rejects_new_enforced_findings(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert _qr(repo, "start", "--task-id", "release-finding").returncode == 0
    (repo / "app.py").write_text(
        "\n".join(f"value_{index} = {index}" for index in range(8)) + "\n",
        encoding="utf-8",
    )

    check = _qr(repo, "release-check", "--task-id", "release-finding")
    payload = json.loads(check.stdout)

    assert check.returncode == 1
    assert payload["status"] == "violation"
    assert payload["release_enforcement"] == "required"
    assert payload["release_readiness"]["eligible"] is False
    assert "rerun `qr task release-check`" in payload["next_action"]


def test_task_release_check_does_not_accept_fast_mode() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "task",
            "release-check",
            "--help",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--fast" not in result.stdout


def test_task_fast_check_is_provisional_and_skips_certified_gates(tmp_path: Path) -> None:
    command = json.dumps(f'{sys.executable} -c "raise SystemExit(7)"')
    bootstrap = json.dumps(f"{sys.executable} --version")
    gate = "\n".join(
        [
            "[[quality_runner.prevention.gates]]",
            'id = "intentional-failure"',
            f"command = {command}",
            'state = "certified"',
            "required = true",
            'owner = "quality"',
            'rationale = "Intentional failure fixture."',
            f"bootstrap = {bootstrap}",
            'mutation_risk = "read-only"',
            'scope = "fixture"',
            "timeout_seconds = 10",
            'evidence_refs = ["failure-fixture:tests/test_cli_task.py", "repeat-pass:tests/test_cli_task.py", "local:tests/test_cli_task.py", "ci:.github/workflows/ci.yml"]',
        ]
    )
    repo = _init_repo(tmp_path, extra_policy=gate)
    assert _qr(repo, "start", "--task-id", "fast").returncode == 0

    check = _qr(repo, "check", "--task-id", "fast", "--fast")
    payload = json.loads(check.stdout)

    assert check.returncode == 0
    assert payload["status"] == "pass"
    assert payload["mode"] == "fast"
    assert payload["release_enforcement"] == "advisory"
    assert payload["gate_results"] == []
    assert payload["required_gate_failures"] == []
    assert payload["release_readiness"]["status"] == "ineligible"
    assert payload["release_readiness"]["eligible"] is False
    assert payload["release_readiness"]["criteria"]["authoritative_check"] is False
    assert "`qr task release-check`" in payload["next_action"]

    record = json.loads((repo / ".quality-runner" / "tasks" / "fast.json").read_text())
    assert record["last_check_mode"] == "fast"


def test_task_new_promoted_finding_is_violation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert _qr(repo, "start", "--task-id", "finding").returncode == 0
    (repo / "app.py").write_text(
        "\n".join(f"value_{index} = {index}" for index in range(8)) + "\n",
        encoding="utf-8",
    )

    check = _qr(repo, "check", "--task-id", "finding")
    payload = json.loads(check.stdout)

    assert check.returncode == 1
    assert payload["status"] == "violation"
    assert "rerun `qr task check`" in payload["next_action"]
    assert payload["delta"]["counts"]["new_enforced"] == 1


def test_task_persisted_legacy_debt_alone_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, large=True)
    assert _qr(repo, "start", "--task-id", "legacy").returncode == 0

    check = _qr(repo, "check", "--task-id", "legacy")
    payload = json.loads(check.stdout)

    assert check.returncode == 0
    assert payload["status"] == "pass"
    assert payload["delta"]["counts"]["persisted"] == 1


def test_task_required_uncertified_gate_is_blocked(tmp_path: Path) -> None:
    gate = "\n".join(
        [
            "[[quality_runner.prevention.gates]]",
            'id = "candidate"',
            f'command = "{sys.executable} --version"',
            'state = "candidate"',
            "required = true",
            'owner = "quality"',
            'rationale = "Not certified yet."',
            'bootstrap = "system fixture"',
            'mutation_risk = "read-only"',
            'scope = "fixture"',
        ]
    )
    repo = _init_repo(tmp_path, extra_policy=gate)
    assert _qr(repo, "start", "--task-id", "blocked").returncode == 0

    check = _qr(repo, "check", "--task-id", "blocked")
    payload = json.loads(check.stdout)

    assert check.returncode == 3
    assert payload["status"] == "blocked"
    assert "Resolve every blocker" in payload["next_action"]
    assert {item["code"] for item in payload["blockers"]} >= {"required_gate_not_ready"}


def test_task_certified_gate_failure_is_violation(tmp_path: Path) -> None:
    command = json.dumps(f'{sys.executable} -c "raise SystemExit(7)"')
    bootstrap = json.dumps(f"{sys.executable} --version")
    gate = "\n".join(
        [
            "[[quality_runner.prevention.gates]]",
            'id = "intentional-failure"',
            f"command = {command}",
            'state = "certified"',
            "required = true",
            'owner = "quality"',
            'rationale = "Intentional failure fixture."',
            f"bootstrap = {bootstrap}",
            'mutation_risk = "read-only"',
            'scope = "fixture"',
            "timeout_seconds = 10",
            'evidence_refs = ["failure-fixture:tests/test_cli_task.py", "repeat-pass:tests/test_cli_task.py", "local:tests/test_cli_task.py", "ci:.github/workflows/ci.yml"]',
        ]
    )
    repo = _init_repo(tmp_path, extra_policy=gate)
    assert _qr(repo, "start", "--task-id", "gate-failure").returncode == 0

    check = _qr(repo, "check", "--task-id", "gate-failure")
    payload = json.loads(check.stdout)

    assert check.returncode == 1
    assert payload["status"] == "violation"
    assert payload["required_gate_failures"][0]["id"] == "intentional-failure"


def test_task_missing_record_is_invalid_invocation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    check = _qr(repo, "check", "--task-id", "missing")

    assert check.returncode == 2
    payload = json.loads(check.stdout)
    assert payload["status"] == "invalid"
    assert "Correct the task invocation" in payload["next_action"]


def test_task_rebaseline_is_explicit_and_preserves_lineage(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    start = _qr(repo, "start", "--task-id", "lineage")
    first_run = json.loads(start.stdout)["baseline_run_id"]
    config = repo / ".quality-runner.toml"
    config.write_text(config.read_text() + "\n# deliberate policy edit\n", encoding="utf-8")

    blocked = _qr(repo, "check", "--task-id", "lineage")
    assert blocked.returncode == 3
    assert any(
        item["code"] == "rebaseline_required" for item in json.loads(blocked.stdout)["blockers"]
    )

    rebaseline = _qr(
        repo,
        "rebaseline",
        "--task-id",
        "lineage",
        "--reason",
        "policy changed",
    )
    second_run = json.loads(rebaseline.stdout)["baseline_run_id"]
    record = json.loads((repo / ".quality-runner" / "tasks" / "lineage.json").read_text())

    assert rebaseline.returncode == 0
    assert second_run != first_run
    assert record["lineage"] == [first_run, second_run]
    assert _qr(repo, "check", "--task-id", "lineage").returncode == 0


def test_task_baseline_ref_scans_immutable_revision_for_pr_delta(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, large=True)

    start = _qr(repo, "start", "--task-id", "pr", "--baseline-ref", "HEAD")
    check = _qr(repo, "check", "--task-id", "pr")

    assert start.returncode == 0
    assert json.loads(start.stdout)["source"]["kind"] == "git_revision"
    assert check.returncode == 1
    assert json.loads(check.stdout)["delta"]["counts"]["new_enforced"] == 1


def test_task_rebaseline_preserves_immutable_pr_target(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    start = _qr(repo, "start", "--task-id", "pr-lineage", "--baseline-ref", "HEAD")
    original_source = json.loads(start.stdout)["source"]
    config = repo / ".quality-runner.toml"
    config.write_text(config.read_text() + "\n# policy refresh\n", encoding="utf-8")

    rebaseline = _qr(
        repo,
        "rebaseline",
        "--task-id",
        "pr-lineage",
        "--reason",
        "policy changed",
    )
    source = json.loads(rebaseline.stdout)["source"]

    assert rebaseline.returncode == 0
    assert source["kind"] == "git_revision"
    assert source["baseline_ref"] == original_source["head_sha"]
    assert source["head_sha"] == original_source["head_sha"]


def test_task_pr_check_evaluates_effective_merge_when_target_is_ahead(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path, large=True)
    _git(repo, "config", "user.email", "quality-runner@example.com")
    _git(repo, "config", "user.name", "Quality Runner")
    _git(repo, "add", "app.py", ".quality-runner.toml")
    _git(repo, "commit", "-m", "task base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "-c", "target")
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "commit", "-am", "fix target finding")
    target_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "-c", "task", base_sha)

    start = _qr(repo, "start", "--task-id", "target-ahead", "--baseline-ref", target_sha)
    check = _qr(repo, "check", "--task-id", "target-ahead")
    payload = json.loads(check.stdout)

    assert start.returncode == 0
    assert check.returncode == 0
    assert payload["status"] == "pass"
    assert payload["snapshot"]["source"]["kind"] == "merge_workspace"
    assert "app.py" not in payload["changed_paths"]
    assert payload["delta"]["counts"]["new_enforced"] == 0
