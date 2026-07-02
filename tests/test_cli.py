from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_support.quality_runner_fixtures import write_js_fixture

ROOT = Path(__file__).resolve().parents[1]


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
    assert payload["version"] == "0.2.0"
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
    assert "Quality Runner 0.2.0" in capsys.readouterr().out

    assert main(["doctor"]) == 0
    assert capsys.readouterr().out.strip() == "Quality Runner 0.2.0: ready"

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

    assert result.stdout.strip() == "0.2.0"
