from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from quality_runner import __version__
from test_support.quality_runner_fixtures import write_js_fixture

ROOT = Path(__file__).resolve().parents[1]


def _install_fake_pnpm(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = repo_root / "fake-bin"
    bin_dir.mkdir()
    fake_pnpm = bin_dir / "pnpm"
    fake_pnpm.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import os",
                "import subprocess",
                "import sys",
                "if len(sys.argv) >= 3 and sys.argv[1] == 'run':",
                "    scripts = json.load(open('package.json', encoding='utf-8'))['scripts']",
                "    env = dict(os.environ)",
                "    env['PATH'] = os.path.abspath('node_modules/.bin') + os.pathsep + env.get('PATH', '')",
                "    raise SystemExit(subprocess.run(scripts[sys.argv[2]], shell=True, env=env).returncode)",
                "raise SystemExit(0)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_pnpm.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_commit_all(repo_root: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=quality-runner@example.com",
            "-c",
            "user.name=Quality Runner",
            "commit",
            "-m",
            message,
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return _git(repo_root, "rev-parse", "HEAD")


def test_cli_run_json_writes_artifacts(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(tmp_path),
            "--run-id",
            "cli-run",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-run-result-v0.1"
    assert payload["status"] == "planned"
    assert payload["run_id"] == "cli-run"
    assert payload["implementation_allowed"] is False
    assert Path(payload["artifact_paths"]["agent_handoff_md"]).exists()
    standards = json.loads(Path(payload["artifact_paths"]["standards_json"]).read_text())
    assert standards["profile"] == "default"


def test_cli_prune_artifacts_defaults_to_preview_and_applies_policy(tmp_path: Path) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.artifacts]\nretention_runs = 1\n",
        encoding="utf-8",
    )
    runs_dir = tmp_path / ".quality-runner" / "runs"
    (runs_dir / "old").mkdir(parents=True)
    (runs_dir / "new").mkdir()
    os.utime(runs_dir / "old", (100, 100))
    os.utime(runs_dir / "new", (200, 200))

    preview = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "prune-artifacts",
            str(tmp_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    preview_payload = json.loads(preview.stdout)
    assert preview_payload["apply"] is False
    assert preview_payload["would_delete_run_ids"] == ["old"]
    assert (runs_dir / "old").exists()

    applied = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "prune-artifacts",
            str(tmp_path),
            "--apply",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    applied_payload = json.loads(applied.stdout)
    assert applied_payload["status"] == "pruned"
    assert applied_payload["deleted_run_ids"] == ["old"]
    assert not (runs_dir / "old").exists()


def test_cli_run_interactive_excludes_expensive_paths_by_default(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    for index in range(120):
        path = tmp_path / "data" / f"row-{index}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(tmp_path),
            "--run-id",
            "cli-interactive-default",
            "--json",
            "--interactive",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        input="\n",
        text=True,
    )

    payload = json.loads(result.stdout)
    code_quality = json.loads(Path(payload["artifact_paths"]["code_quality_scan_json"]).read_text())
    scanned_paths = {item["path"] for item in code_quality["accountability"]}

    assert "Exclude these paths from this run? [Y/n]" in result.stderr
    assert "include_ignored_paths" in result.stderr
    assert "data" not in scanned_paths


def test_cli_run_interactive_can_include_expensive_paths_once(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    for index in range(120):
        path = tmp_path / "data" / f"row-{index}.ts"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("const included: any = {};\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(tmp_path),
            "--run-id",
            "cli-interactive-include",
            "--json",
            "--interactive",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        input="n\n",
        text=True,
    )

    payload = json.loads(result.stdout)
    code_quality = json.loads(Path(payload["artifact_paths"]["code_quality_scan_json"]).read_text())
    scanned_paths = {item["path"] for item in code_quality["accountability"]}

    assert "Scanning these paths for this run only." in result.stderr
    assert "data/row-0.ts" in scanned_paths


def test_cli_inspect_json_writes_inspection_artifacts(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "inspect",
            str(tmp_path),
            "--run-id",
            "cli-inspect",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-inspect-result-v0.1"
    assert payload["status"] == "inspected"
    assert payload["run_id"] == "cli-inspect"
    assert Path(payload["artifact_paths"]["repo_scan_json"]).exists()
    assert "quality_audit_json" not in payload["artifact_paths"]


def test_cli_inspect_accepts_ci_status_json(tmp_path: Path) -> None:
    ci_status = tmp_path / "ci-status.json"
    ci_status.write_text(json.dumps({"checks": [{"name": "Lint", "status": "completed"}]}))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "inspect",
            str(tmp_path),
            "--run-id",
            "cli-ci-inspect",
            "--ci-status-json",
            str(ci_status),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    repo_scan = json.loads(Path(payload["artifact_paths"]["repo_scan_json"]).read_text())
    assert repo_scan["ci_checks"] == [
        {
            "name": "Lint",
            "status": "completed",
            "conclusion": None,
            "url": None,
            "source": "ci-status.json",
        }
    ]


def test_cli_verify_gates_json_executes_discovered_gates(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": f"{sys.executable} -c 'import sys; sys.exit(0)'"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint"]\n',
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git_commit_all(tmp_path, "fixture")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "verify-gates",
            str(tmp_path),
            "--run-id",
            "cli-verify-gates",
            "--execute-gates",
            "--worktree-mode",
            "disposable",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    verification = json.loads(Path(payload["artifact_paths"]["gate_verification_json"]).read_text())

    assert payload["schema"] == "quality-runner-verify-gates-result-v0.1"
    assert payload["status"] == "passed"
    assert verification["gates"][0]["status"] == "passed"


def test_cli_verify_gates_requires_explicit_execution_consent(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel.txt"
    program = f"from pathlib import Path; Path({str(sentinel)!r}).write_text('ran')"
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": f"{sys.executable} -c {shlex.quote(program)}"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint"]\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "verify-gates",
            str(tmp_path),
            "--run-id",
            "cli-consent-required",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    verification = json.loads(Path(payload["artifact_paths"]["gate_verification_json"]).read_text())

    assert payload["status"] == "blocked"
    assert verification["execute_discovered_gates"] is False
    assert verification["gates"][0]["skip_type"] == "execution-consent-required"
    assert not sentinel.exists()


def test_cli_verify_gates_rejects_execution_in_the_source_worktree(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "verify-gates",
            str(tmp_path),
            "--execute-gates",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "requires --worktree-mode disposable" in result.stderr


def test_cli_rollout_rejects_execution_without_disposable_worktrees(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "rollout",
            "--repo",
            str(tmp_path),
            "--execute-gates",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "requires --worktree-mode disposable" in result.stderr


def test_cli_refresh_help_names_statuses_action_groups_and_timeout_reasons() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "refresh", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "gates-blocked" in result.stdout
    assert "gates-failed" in result.stdout
    assert "gates-clean" in result.stdout
    assert "action_groups" in result.stdout
    assert "--handoff-output" in result.stdout
    assert "--total-timeout-reason" in result.stdout


def test_cli_rollout_help_names_repo_list_outputs_and_safety_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "rollout", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Repo list formats" in result.stdout
    assert "rollout-ledger.json" in result.stdout
    assert "controller-report JSON" in result.stdout
    assert "--repo" in result.stdout
    assert "--allow-mutating-gates" in result.stdout
    assert "--total-timeout-reason" in result.stdout


def test_cli_inspect_can_checkout_most_advanced_branch(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    _git(tmp_path, "init", "-b", "main")
    _git_commit_all(tmp_path, "Initial commit")
    _git(tmp_path, "switch", "-c", "old-feature")
    (tmp_path / "old-feature.txt").write_text("old\n", encoding="utf-8")
    _git_commit_all(tmp_path, "Old feature")
    _git(tmp_path, "switch", "main")
    _git(tmp_path, "switch", "-c", "advanced-feature")
    (tmp_path / "advanced-one.txt").write_text("one\n", encoding="utf-8")
    _git_commit_all(tmp_path, "Advanced one")
    (tmp_path / "advanced-two.txt").write_text("two\n", encoding="utf-8")
    _git_commit_all(tmp_path, "Advanced two")
    _git(tmp_path, "switch", "old-feature")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "inspect",
            str(tmp_path),
            "--run-id",
            "cli-branch-checkout",
            "--checkout-most-advanced-branch",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    manifest = json.loads(Path(payload["artifact_paths"]["run_manifest_json"]).read_text())
    assert _git(tmp_path, "branch", "--show-current") == "advanced-feature"
    assert manifest["git"]["branch"] == "advanced-feature"


def test_cli_doctor_json_reports_ready() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "doctor", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-doctor-result-v0.1"
    assert payload["status"] == "ready"
    assert payload["version"] == __version__
    assert payload["environment"]["python_executable"]


def test_cli_init_writes_starter_config(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "init",
            str(tmp_path),
            "--required-capability",
            "lint",
            "--required-capability",
            "tests",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    config_path = tmp_path / ".quality-runner.toml"

    assert payload == {
        "schema": "quality-runner-init-result-v0.1",
        "status": "created",
        "config_path": str(config_path),
        "implementation_allowed": False,
    }
    assert config_path.read_text(encoding="utf-8") == (
        '[quality_runner]\ndefault_profile = "default"\nrequired_capabilities = ["lint", "tests"]\n'
    )


def test_cli_init_refuses_existing_config_without_force(tmp_path: Path) -> None:
    (tmp_path / ".quality-runner.toml").write_text("[quality_runner]\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "init", str(tmp_path), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert result.stdout == ""


def test_cli_status_json_reports_config_and_latest_run(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\ndefault_profile = "default"\n',
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(tmp_path),
            "--run-id",
            "cli-status-run",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "status", str(tmp_path), "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-status-result-v0.1"
    assert payload["status"] == "ready"
    assert payload["config"]["path"] == ".quality-runner.toml"
    assert payload["latest_run"]["run_id"] == "cli-status-run"
    assert payload["latest_run"]["has_handoff"] is True
    assert payload["latest_run"]["has_gate_verification"] is False


def test_cli_status_reports_latest_verify_gate_failure(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": f"{sys.executable} -c 'import sys; sys.exit(1)'"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint"]\n',
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git_commit_all(tmp_path, "fixture")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "verify-gates",
            str(tmp_path),
            "--run-id",
            "cli-status-verify",
            "--execute-gates",
            "--worktree-mode",
            "disposable",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "status", str(tmp_path), "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["status"] == "blocked"
    assert payload["latest_run"]["run_id"] == "cli-status-verify"
    assert payload["latest_run"]["has_gate_verification"] is True
    assert payload["latest_run"]["gate_verification_status"] == "failed"


def test_cli_summarize_run_reports_final_artifact_summary_and_delta(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(tmp_path),
            "--run-id",
            "summary-baseline",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "verify-gates",
            str(tmp_path),
            "--run-id",
            "summary-final",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "summarize-run",
            str(tmp_path),
            "--run-id",
            "summary-final",
            "--baseline-run-id",
            "summary-baseline",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["schema"] == "quality-runner-run-summary-v0.1"
    assert payload["run_id"] == "summary-final"
    assert payload["status"] in {"passed-with-findings", "blocked", "failed"}
    assert "recommended_classification" in payload
    assert "gate_results" in payload
    assert "missing_capabilities" in payload
    assert "finding_counts" in payload
    assert payload["delta"]["baseline_run_id"] == "summary-baseline"
    assert "missing_capabilities" in payload["delta"]
    assert "findings_total" in payload["delta"]
    persisted = tmp_path / ".quality-runner" / "runs" / "summary-final" / "run-summary.json"
    assert json.loads(persisted.read_text(encoding="utf-8"))["run_id"] == "summary-final"


def test_cli_refresh_runs_read_only_sequence_and_persists_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_pnpm(tmp_path, monkeypatch)

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "format": "eslint --fix .",
                    "test": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["formatter", "tests"]\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "refresh",
            str(tmp_path),
            "--run-id-prefix",
            "cli-refresh",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-refresh-result-v0.1"
    assert payload["runs"]["inspect"]["run_id"] == "cli-refresh-inspect"
    assert payload["runs"]["run"]["run_id"] == "cli-refresh-run"
    assert payload["runs"]["verify"]["run_id"] == "cli-refresh-verify"
    assert payload["summary"]["recommended_classification"] == "execution-consent-required"
    inspect_code = json.loads(
        (
            tmp_path / ".quality-runner" / "runs" / "cli-refresh-inspect" / "code-quality-scan.json"
        ).read_text()
    )
    run_code = json.loads(
        (
            tmp_path / ".quality-runner" / "runs" / "cli-refresh-run" / "code-quality-scan.json"
        ).read_text()
    )
    assert inspect_code["analysis_cache"]["persisted"] is True
    assert run_code["analysis_cache"]["cache_hits"] > 0
    assert run_code["analysis_cache"]["cache_misses"] == 0
    persisted = tmp_path / ".quality-runner" / "runs" / "cli-refresh-verify" / "run-summary.json"
    assert json.loads(persisted.read_text(encoding="utf-8"))["run_id"] == "cli-refresh-verify"


def test_cli_refresh_can_export_handoff_in_same_command(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    output_path = tmp_path / "remediation-plan.md"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "refresh",
            str(tmp_path),
            "--run-id-prefix",
            "cli-refresh-handoff",
            "--handoff-output",
            str(output_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    canonical_handoff = (
        tmp_path / ".quality-runner" / "runs" / "cli-refresh-handoff-verify" / "agent-handoff.md"
    )

    assert payload["schema"] == "quality-runner-refresh-result-v0.1"
    assert payload["handoff_export"]["schema"] == "quality-runner-export-handoff-result-v0.1"
    assert payload["handoff_export"]["run_id"] == "cli-refresh-handoff-verify"
    assert payload["handoff_export"]["source_path"] == str(canonical_handoff)
    assert payload["handoff_export"]["output_path"] == str(output_path)
    assert output_path.read_text(encoding="utf-8") == canonical_handoff.read_text(encoding="utf-8")
    assert output_path.read_text(encoding="utf-8").startswith("# Quality Runner Agent Handoff\n")


def test_cli_refresh_human_summary_includes_handoff_output(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    output_path = tmp_path / "remediation-plan.md"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "refresh",
            str(tmp_path),
            "--run-id-prefix",
            "cli-refresh-human-handoff",
            "--handoff-output",
            str(output_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert f"handoff: {output_path}" in result.stdout
    assert output_path.read_text(encoding="utf-8").startswith("# Quality Runner Agent Handoff\n")


def test_cli_refresh_workflow_timeout_records_reason(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": f"{sys.executable} -c 'import time; time.sleep(5)'",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["tests"]\n',
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git_commit_all(tmp_path, "fixture")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "refresh",
            str(tmp_path),
            "--run-id-prefix",
            "cli-refresh-timeout",
            "--timeout-seconds",
            "30",
            "--verify-timeout-seconds",
            "1",
            "--workflow-timeout-reason",
            "controller deadline exceeded during verify",
            "--execute-gates",
            "--worktree-mode",
            "disposable",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    payload = json.loads(result.stdout)
    run_dir = tmp_path / ".quality-runner" / "runs" / "cli-refresh-timeout-verify"
    gate_verification = json.loads((run_dir / "gate-verification.json").read_text())
    timeout_artifact = json.loads((run_dir / "workflow-timeout.json").read_text())

    assert payload["status"] == "blocked"
    assert payload["summary"]["recommended_classification"] == "workflow-timeout-blocker"
    assert payload["timeout_contract"]["per_gate_timeout_seconds"] == 30
    assert payload["timeout_contract"]["verify_timeout_seconds"] == 1
    assert payload["timeout_contract"]["verify_timeout_source"] == "explicit"
    assert payload["timeout_contract"]["total_timeout_seconds"] is None
    assert payload["phase_timings"]["verify"]["status"] == "timeout"
    assert payload["runs"]["verify"]["timeout"]["reason"] == (
        "controller deadline exceeded during verify"
    )
    assert payload["runs"]["verify"]["timeout"]["timeout_scope"] == "verify-phase"
    assert gate_verification["failure_type"] == "workflow-timeout"
    assert gate_verification["reason"] == "controller deadline exceeded during verify"
    assert gate_verification["timeout_scope"] == "verify-phase"
    assert timeout_artifact["reason"] == "controller deadline exceeded during verify"
    assert timeout_artifact["timeout_scope"] == "verify-phase"


def test_cli_export_handoff_prints_latest_handoff(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(tmp_path),
            "--run-id",
            "cli-export-run",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "export-handoff", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Quality Runner Agent Handoff\n")
    assert "remediate-missing-formatter" in result.stdout


def test_cli_export_handoff_writes_selected_run_to_output(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(tmp_path),
            "--run-id",
            "cli-export-output",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output_path = tmp_path / "handoff.md"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "export-handoff",
            str(tmp_path),
            "--run-id",
            "cli-export-output",
            "--output",
            str(output_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-export-handoff-result-v0.1"
    assert payload["status"] == "exported"
    assert payload["run_id"] == "cli-export-output"
    assert payload["output_path"] == str(output_path)
    assert output_path.read_text(encoding="utf-8").startswith("# Quality Runner Agent Handoff\n")


def test_cli_main_new_commands_in_process(tmp_path: Path, capsys) -> None:
    from quality_runner.cli import main

    assert (
        main(
            [
                "init",
                str(tmp_path),
                "--required-capability",
                "lint",
                "--json",
            ]
        )
        == 0
    )
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["status"] == "created"

    assert main(["status", str(tmp_path)]) == 0
    assert "latest run: none" in capsys.readouterr().out

    write_js_fixture(tmp_path)
    assert main(["run", str(tmp_path), "--run-id", "direct-cli-run", "--json"]) == 0
    capsys.readouterr()

    assert main(["status", str(tmp_path), "--json"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["latest_run"]["run_id"] == "direct-cli-run"

    report_path = tmp_path / "worker-report.json"
    report_path.write_text(
        json.dumps(
            {
                "repo_path": str(tmp_path),
                "branch_name": "qr/example",
                "status": "blocked",
                "baseline_artifact_path": str(tmp_path / ".quality-runner" / "runs"),
                "final_qr": {"run_id": "direct-cli-run", "status": "blocked"},
                "files_changed": [],
                "verification": [{"command": "quality-runner run .", "result": "blocked"}],
                "commit_hash": None,
                "push_status": "not-pushed",
                "git_status_short": "",
                "blockers": ["fixture blocker"],
            }
        ),
        encoding="utf-8",
    )
    assert main(["validate-report", str(report_path), "--json"]) == 0
    validation_payload = json.loads(capsys.readouterr().out)
    assert validation_payload["status"] == "accepted"

    assert main(["controller-report", "normalize", str(report_path), "--json"]) == 0
    normalized_payload = json.loads(capsys.readouterr().out)
    assert normalized_payload["schema"] == "quality-runner-controller-report-v0.1"
    assert normalized_payload["status"] == "blocked"

    assert main(["controller-report", "lint", str(report_path), "--strict", "--json"]) == 0
    lint_payload = json.loads(capsys.readouterr().out)
    assert lint_payload["status"] == "accepted"
    assert lint_payload["normalized_report"]["repo_path"] == str(tmp_path)

    controller_report_path = tmp_path / "direct-controller-report.json"
    assert (
        main(
            [
                "summarize-run",
                str(tmp_path),
                "--run-id",
                "direct-cli-run",
                "--baseline-run-id",
                "direct-cli-run",
                "--controller-report",
                "--branch-name",
                "qr/example",
                "--report-output",
                str(controller_report_path),
                "--lint-report",
                "--validate-report",
                "--json",
            ]
        )
        == 0
    )
    controller_report_payload = json.loads(capsys.readouterr().out)
    assert controller_report_payload["schema"] == "quality-runner-controller-report-v0.1"
    assert controller_report_payload["branch_name"] == "qr/example"
    assert controller_report_payload["baseline_artifact_path"].endswith(
        "/.quality-runner/runs/direct-cli-run"
    )
    assert isinstance(controller_report_payload["target_head"], str)
    assert controller_report_payload["commit_created_by_task"] is False
    assert controller_report_payload["self_checks"] == [
        {
            "command": f"quality-runner controller-report lint {controller_report_path.resolve()} --strict --json",
            "errors": [],
            "status": "accepted",
        },
        {
            "command": f"quality-runner validate-report {controller_report_path.resolve()} --json",
            "errors": [],
            "status": "accepted",
        },
    ]
    persisted_report = json.loads(controller_report_path.read_text(encoding="utf-8"))
    assert persisted_report["self_checks"] == controller_report_payload["self_checks"]

    rejected_report_path = tmp_path / "rejected-worker-report.json"
    rejected_payload = json.loads(report_path.read_text(encoding="utf-8"))
    rejected_payload["status"] = "complete"
    rejected_payload["commit_hash"] = "abc1234"
    rejected_payload["push_status"] = "pushed"
    rejected_payload["git_status_short"] = " M package.json"
    rejected_report_path.write_text(json.dumps(rejected_payload), encoding="utf-8")

    assert main(["validate-report", str(rejected_report_path), "--json"]) == 1
    rejected_validation = json.loads(capsys.readouterr().out)
    assert rejected_validation["status"] == "rejected"

    assert main(["export-handoff", str(tmp_path), "--run-id", "direct-cli-run"]) == 0
    assert capsys.readouterr().out.startswith("# Quality Runner Agent Handoff\n")

    output_path = tmp_path / "direct-handoff.md"
    assert (
        main(
            [
                "export-handoff",
                str(tmp_path),
                "--run-id",
                "direct-cli-run",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    assert f"handoff: {output_path.resolve()}" in capsys.readouterr().out
    assert output_path.exists()


def test_cli_main_reports_human_summaries_in_process(tmp_path: Path, capsys) -> None:
    from quality_runner.cli import main

    assert main([]) == 0
    assert f"Quality Runner {__version__}" in capsys.readouterr().out

    assert main(["doctor"]) == 0
    assert capsys.readouterr().out.strip() == f"Quality Runner {__version__}: ready"

    write_js_fixture(tmp_path)
    assert main(["inspect", str(tmp_path), "--run-id", "human-inspect"]) == 0
    inspect_output = capsys.readouterr().out
    assert "status: inspected" in inspect_output
    assert "repo scan:" in inspect_output

    assert main(["run", str(tmp_path), "--run-id", "human-run"]) == 0
    run_output = capsys.readouterr().out
    assert "status: planned" in run_output
    assert "handoff:" in run_output
    assert "audit:" in run_output


def test_cli_main_reports_export_errors_in_process(tmp_path: Path, capsys) -> None:
    from quality_runner.cli import main

    assert main(["export-handoff", str(tmp_path)]) == 1
    captured = capsys.readouterr()

    assert "no Quality Runner runs found" in captured.err
    assert captured.out == ""


def test_cli_main_rejects_file_repo_path_in_process(tmp_path: Path, capsys) -> None:
    from quality_runner.cli import main

    repo_file = tmp_path / "not-a-repo"
    repo_file.write_text("content", encoding="utf-8")

    assert main(["status", str(repo_file)]) == 1
    captured = capsys.readouterr()

    assert "repo root is not a directory" in captured.err
    assert captured.out == ""


def test_cli_main_reports_init_conflict_in_process(tmp_path: Path, capsys) -> None:
    from quality_runner.cli import main

    (tmp_path / ".quality-runner.toml").write_text("[quality_runner]\n", encoding="utf-8")

    assert main(["init", str(tmp_path), "--json"]) == 1
    captured = capsys.readouterr()

    assert "already exists" in captured.err
    assert captured.out == ""


def test_cli_invalid_repo_path_fails_without_traceback(tmp_path: Path) -> None:
    missing_repo = tmp_path / "missing"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(missing_repo),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "repo root does not exist" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_cli_version_preserves_bare_version_output() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == __version__
