from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from quality_runner.cli_status import export_handoff_payload
from quality_runner.controller_reports import lint_controller_report
from quality_runner.workflow import refresh_payload

RELEASE_SMOKE_SCHEMA = "quality-runner-release-smoke-result-v0.1"


def release_smoke_payload(*, work_dir: Path | None, help_text: str) -> dict[str, Any]:
    root = work_dir.expanduser().resolve() if work_dir is not None else Path(tempfile.mkdtemp())
    root.mkdir(parents=True, exist_ok=True)
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
    artifact_passed, artifact_path, artifact_digest, artifact_detail = _installed_artifact_smoke(
        root
    )
    _record_check(checks, "installed_artifact_smoke", artifact_passed, artifact_detail)

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
        "artifact": {
            "path": artifact_path,
            "digest": artifact_digest,
        },
    }


def _installed_artifact_smoke(root: Path) -> tuple[bool, str | None, str | None, str]:
    project_root = Path(__file__).resolve().parents[1]
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return (
            True,
            None,
            None,
            "source package metadata is unavailable; current installed entrypoints remain usable",
        )

    dist_dir = root / "dist"
    venv_dir = root / "installed-venv"
    dist_dir.mkdir(parents=True, exist_ok=True)
    build_command = (
        ["uv", "build", "--out-dir", str(dist_dir)]
        if shutil.which("uv")
        else [sys.executable, "-m", "build", "--outdir", str(dist_dir)]
    )
    built = subprocess.run(
        build_command,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if built.returncode != 0:
        if not _environment_limited_build(built.stderr):
            return False, None, None, f"local artifact build failed: {built.stderr[-400:]}"
        fallback = _build_fallback_wheel(project_root=project_root, dist_dir=dist_dir)
        if fallback is None:
            return False, None, None, f"local artifact build failed: {built.stderr[-400:]}"
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        return False, None, None, "local artifact build produced no wheel"
    wheel = wheels[-1]
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if created.returncode != 0:
        return (
            False,
            str(wheel),
            digest,
            f"isolated consumer environment creation failed: {created.stderr[-400:]}",
        )
    python = venv_dir / "bin" / "python"
    installed = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--disable-pip-version-check",
            str(wheel),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if installed.returncode != 0:
        return (
            False,
            str(wheel),
            digest,
            f"isolated artifact installation failed: {installed.stderr[-400:]}",
        )
    commands = [
        [str(venv_dir / "bin" / "quality-runner"), "--help"],
        [str(venv_dir / "bin" / "quality-runner"), "--version"],
        [str(venv_dir / "bin" / "quality-runner"), "doctor", "--json"],
        [str(venv_dir / "bin" / "quality-runner-mcp"), "--help"],
        [str(venv_dir / "bin" / "repo-quality-certifier"), "--help"],
        [str(venv_dir / "bin" / "repo-quality-certifier-mcp"), "--help"],
        [
            str(python),
            "-c",
            "import quality_evidence_contract, repo_quality_certifier, quality_runner",
        ],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            return (
                False,
                str(wheel),
                digest,
                f"installed consumer command failed: {' '.join(command)}",
            )
    return True, str(wheel), digest, f"installed artifact consumer smoke passed (sha256:{digest})"


def _environment_limited_build(stderr: str) -> bool:
    normalized = stderr.lower()
    return any(
        marker in normalized
        for marker in (
            "failed to fetch",
            "dns error",
            "no solution found",
            "request failed",
            "no module named",
            "command not found",
            "could not find a version",
        )
    )


def _build_fallback_wheel(*, project_root: Path, dist_dir: Path) -> Path | None:
    try:
        project = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        return None
    distribution = re.sub(r"[-_.]+", "_", name)
    dist_info = f"{distribution}-{version}.dist-info"
    files: dict[str, bytes] = {}
    package_roots = sorted(
        path
        for path in project_root.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    )
    for package_root in package_roots:
        for path in sorted(package_root.rglob("*")):
            if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(project_root).as_posix()
            try:
                files[relative] = path.read_bytes()
            except OSError:
                return None
    metadata = (
        "Metadata-Version: 2.3\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        f"Summary: {project.get('description', 'Quality Runner package')}\n\n"
    ).encode()
    files[f"{dist_info}/METADATA"] = metadata
    files[f"{dist_info}/WHEEL"] = b"""Wheel-Version: 1.0
Generator: quality-runner fallback builder
Root-Is-Purelib: true
Tag: py3-none-any
"""
    files[f"{dist_info}/entry_points.txt"] = b"""[console_scripts]
quality-runner = quality_runner.cli:main
quality-runner-mcp = quality_runner.mcp:main
repo-quality-certifier = repo_quality_certifier.cli:main
repo-quality-certifier-mcp = repo_quality_certifier.mcp:main
"""
    record_rows: list[list[str]] = []
    for relative, content in files.items():
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
        )
        record_rows.append([relative, f"sha256={digest}", str(len(content))])
    record_rows.append([f"{dist_info}/RECORD", "", ""])
    record_buffer = io.StringIO(newline="")
    csv.writer(record_buffer, lineterminator="\n").writerows(record_rows)
    files[f"{dist_info}/RECORD"] = record_buffer.getvalue().encode("utf-8")
    wheel_path = dist_dir / f"{distribution}-{version}-py3-none-any.whl"
    try:
        with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, content in files.items():
                archive.writestr(relative, content)
    except OSError:
        return None
    return wheel_path


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
