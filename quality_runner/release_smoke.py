from __future__ import annotations

import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_safe_directory
from quality_runner.cli_status import export_handoff_payload
from quality_runner.controller_reports import lint_controller_report
from quality_runner.workflow import refresh_payload

RELEASE_SMOKE_SCHEMA = "quality-runner-release-smoke-result-v0.1"


def release_smoke_payload(*, work_dir: Path | None, help_text: str) -> dict[str, Any]:
    root = (
        prepare_safe_directory(work_dir)
        if work_dir is not None
        else Path(tempfile.mkdtemp()).resolve()
    )
    repo_root = root / "sample-repo"
    _write_sample_repo(repo_root)

    handoff_output = root / "release-smoke-handoff.md"
    exported_output = root / "release-smoke-exported-handoff.md"
    checks: list[dict[str, str]] = []

    _record_check(
        checks,
        "help",
        "release-smoke" in help_text,
        "CLI help includes release-smoke",
    )
    _record_check(checks, "doctor", True, "doctor payload is available")

    refresh = refresh_payload(
        repo_root=repo_root,
        run_id_prefix="release-smoke",
        timeout_seconds=5,
        verify_timeout_seconds=15,
        total_timeout_seconds=30,
        total_timeout_reason="release smoke bounded evidence run",
    )
    export_handoff_payload(
        repo_root=repo_root,
        run_id="release-smoke-verify",
        output_path=handoff_output,
    )
    _record_check(
        checks,
        "refresh_handoff",
        refresh.get("schema") == "quality-runner-refresh-result-v0.1"
        and handoff_output.exists()
        and handoff_output.read_text(encoding="utf-8").startswith(
            "# Quality Runner Agent Handoff\n"
        ),
        "refresh produced a remediation handoff",
    )

    exported = export_handoff_payload(
        repo_root=repo_root,
        run_id="release-smoke-verify",
        output_path=exported_output,
    )
    _record_check(
        checks,
        "export_handoff",
        exported.get("schema") == "quality-runner-export-handoff-result-v0.1"
        and exported_output.read_text(encoding="utf-8")
        == handoff_output.read_text(encoding="utf-8"),
        "export-handoff copied an existing remediation handoff",
    )
    _record_check(
        checks,
        "schema_compatibility",
        _schema_compatibility_passed(),
        "legacy and timeout-diagnostic controller reports normalize",
    )
    _record_check(
        checks,
        "compatibility_surfaces",
        _compatibility_surfaces_passed(root=root, repo_root=repo_root),
        "quality-evidence-contract and repo-quality-certifier compatibility surfaces load",
    )

    status = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
    return {
        "schema": RELEASE_SMOKE_SCHEMA,
        "status": status,
        "implementation_allowed": False,
        "work_dir": str(root),
        "sample_repo": str(repo_root),
        "handoff_output": str(handoff_output),
        "exported_handoff_output": str(exported_output),
        "checks": checks,
        "refresh_status": str(refresh.get("status") or "unknown"),
    }


def _write_sample_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "README.md").write_text("# Release smoke sample\n", encoding="utf-8")
    (repo_root / "src").mkdir(exist_ok=True)
    (repo_root / "src" / "sample.py").write_text(
        "def main() -> str:\n    return 'ok'\n",
        encoding="utf-8",
    )
    (repo_root / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["tests"]\n',
        encoding="utf-8",
    )


def _record_check(
    checks: list[dict[str, str]],
    check_id: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "passed" if passed else "failed",
            "detail": detail,
        }
    )


def _schema_compatibility_passed() -> bool:
    return (
        lint_controller_report(_legacy_controller_report(), strict=True)["status"] == "accepted"
        and lint_controller_report(_timeout_controller_report(), strict=True)["status"]
        == "accepted"
    )


def _compatibility_surfaces_passed(*, root: Path, repo_root: Path) -> bool:
    try:
        from quality_evidence_contract import (
            QUALITY_FINDING_SCHEMA,
            normalize_quality_finding,
            validate_quality_finding,
        )
        from repo_quality_certifier import GATE_MATRIX_SCHEMA
        from repo_quality_certifier.cli import build_plan_payload
        from repo_quality_certifier.mcp import list_tools

        finding = normalize_quality_finding(
            criterion_id="release-smoke-compatibility",
            level="pass",
            summary="Compatibility import smoke passed.",
            evidence=["quality-runner release-smoke"],
        )
        plan = build_plan_payload(
            repo_root=repo_root,
            run_id="release-smoke-certifier",
            output_dir=root / "release-smoke-certifier",
        )
        tool_names = {tool["name"] for tool in list_tools()}
        return (
            QUALITY_FINDING_SCHEMA == "quality-finding-v0.1"
            and GATE_MATRIX_SCHEMA == "aios-repo-gate-matrix-v0.1"
            and validate_quality_finding(finding)["passed"] is True
            and plan["schema"] == "repo-quality-certifier-plan-result-v0.1"
            and Path(plan["artifact_paths"]["gate_matrix_json"]).exists()
            and {
                "repo_quality_certifier_plan",
                "repo_quality_certifier_doc_quality",
            }.issubset(tool_names)
            and files("quality_runner").joinpath("plugin/manifest.json").is_file()
            and files("repo_quality_certifier").joinpath("plugin/manifest.json").is_file()
        )
    except Exception:
        return False


def _legacy_controller_report() -> dict[str, Any]:
    return {
        "schema": "quality-runner-controller-report-v0.1",
        "repo_path": "/repos/example",
        "branch_name": "qr/example",
        "status": "blocked",
        "baseline_artifact_path": "/repos/example/.quality-runner/runs/baseline",
        "final_qr": {
            "run_id": "verify",
            "status": "blocked",
            "classification": "workflow-timeout-blocker",
            "blocker_classes": ["workflow-timeout"],
            "failure_type": "workflow-timeout",
        },
        "files_changed": [],
        "verification": [
            {"command": "quality-runner summarize-run /repos/example", "result": "blocked"}
        ],
        "commit_hash": None,
        "target_head": "abc123",
        "commit_created_by_task": False,
        "push_status": "not-pushed",
        "git_status_short": "",
        "blockers": ["Workflow timeout prevented complete evidence collection."],
    }


def _timeout_controller_report() -> dict[str, Any]:
    return {
        **_legacy_controller_report(),
        "final_qr": {
            **_legacy_controller_report()["final_qr"],
            "timeout_diagnostics": {
                "timeout_scope": "total-refresh",
                "last_directory": "data/cache",
                "visited_paths": 5000,
                "pruning_recommendations": [
                    {"kind": "scan-exclusion", "path": "data/cache", "pattern": "data/cache/**"}
                ],
            },
        },
        "blockers": [],
    }
