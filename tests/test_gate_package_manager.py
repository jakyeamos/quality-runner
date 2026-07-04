from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


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


def test_verify_gates_runs_package_scripts_through_detected_package_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.workflow import verify_gates_payload

    _install_fake_pnpm(tmp_path, monkeypatch)

    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    fake_lint = bin_dir / "fake-lint"
    fake_lint.write_text("#!/bin/sh\necho package-bin-ok\n", encoding="utf-8")
    fake_lint.chmod(0o755)
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10.0.0", "scripts": {"lint": "fake-lint"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="package-manager-gates")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "passed"
    assert verification["gates"][0]["command"] == "pnpm run lint"
    assert "package-bin-ok\n" in verification["gates"][0]["stdout_tail"]


def test_verify_gates_read_only_mode_skips_mutating_formatter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.workflow import verify_gates_payload

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

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="read-only-mutating",
        read_only_gates=True,
    )
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )
    plan = json.loads(Path(payload["artifact_paths"]["gate_execution_plan_json"]).read_text())

    assert payload["status"] == "blocked"
    assert verification["status"] == "blocked"
    assert verification["gates"][0]["status"] == "skipped"
    assert verification["gates"][0]["skip_type"] == "mutating-gate-not-run"
    assert verification["gates"][0]["mutating_risk"] == "mutating"
    assert verification["gates"][1]["status"] == "passed"
    assert plan[0]["local_execution_status"] == "mutating-skipped"


def test_verify_gates_classifies_dependency_setup_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.workflow import verify_gates_payload

    _install_fake_pnpm(tmp_path, monkeypatch)

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "lint": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                    "test": (
                        f"{sys.executable} -c "
                        "\"import sys; "
                        "print('ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY', file=sys.stderr); "
                        "sys.exit(1)\""
                    ),
                    "build": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint", "tests", "build"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="dependency-setup")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "blocked"
    assert verification["gates"][0]["id"] == "lint"
    assert verification["gates"][0]["status"] == "passed"
    assert verification["gates"][1]["id"] == "tests"
    assert verification["gates"][1]["failure_type"] == "dependency-setup-blocker"
    assert verification["gates"][1]["diagnostics"]["dependency_setup"]["package_manager"] == "pnpm"
    assert verification["gates"][2]["status"] == "skipped"
    assert verification["gates"][2]["skip_type"] == "dependency-setup-blocked"


def test_verify_gates_classifies_pnpm_ignored_builds_as_dependency_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.workflow import verify_gates_payload

    _install_fake_pnpm(tmp_path, monkeypatch)

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "lint": (
                        f"{sys.executable} -c "
                        "\"import sys; "
                        "print('[ERR_PNPM_IGNORED_BUILDS] Ignored build scripts: sharp'); "
                        "print('Run \\'pnpm approve-builds\\' to pick which dependencies should be allowed'); "
                        "sys.exit(1)\""
                    ),
                    "test": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["lint", "tests"]\n',
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="pnpm-ignored-builds")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )
    handoff = json.loads(Path(payload["artifact_paths"]["agent_handoff_json"]).read_text())
    handoff_markdown = Path(payload["artifact_paths"]["agent_handoff_md"]).read_text()

    assert payload["status"] == "blocked"
    assert verification["gates"][0]["failure_type"] == "dependency-setup-blocker"
    assert verification["gates"][1]["skip_type"] == "dependency-setup-blocked"
    assert handoff["gate_verification"]["primary_blocker_class"] == "dependency-setup"
    assert "Setup: `pnpm approve-builds`" in handoff_markdown


def test_verify_gates_uses_per_gate_timeout_config_and_skips_covered_aggregate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.workflow import verify_gates_payload

    _install_fake_pnpm(tmp_path, monkeypatch)

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "lint": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                    "pre-cr": "pnpm run lint",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["lint", "pre_cr"]',
                "",
                "[quality_runner.gate_timeouts]",
                "lint = 9",
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="aggregate-skip")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )

    assert payload["status"] == "passed"
    assert verification["gate_timeouts"] == {"lint": 9}
    assert [(gate["id"], gate["status"]) for gate in verification["gates"]] == [
        ("lint", "passed"),
        ("pre_cr", "skipped"),
    ]
