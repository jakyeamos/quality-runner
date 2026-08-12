from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quality_runner.cli import main
from quality_runner.config import load_repo_config
from quality_runner.web_readiness import (
    DEPLOYMENT_EVIDENCE_SCHEMA,
    REPORT_SCHEMA,
    create_web_readiness_report,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _fixture(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "site"
    (repo / "src").mkdir(parents=True)
    (repo / "public").mkdir()
    (repo / "dist" / "assets").mkdir(parents=True)
    (repo / "src" / "app.html").write_text(
        """
        <html lang="en">
          <head>
            <title>Home</title>
            <link rel="icon" href="/favicon.ico">
            <meta name="description" content="Fixture">
            <meta property="og:image" content="/social.png">
          </head>
          <body><h1>Home</h1><img src="hero.png" alt="Hero"></body>
        </html>
        """,
        encoding="utf-8",
    )
    (repo / "src" / "404.html").write_text("<h1>Not found</h1>", encoding="utf-8")
    (repo / "public" / "favicon.ico").write_bytes(b"icon")
    (repo / "dist" / "assets" / "main.js").write_text("console.log('ok')", encoding="utf-8")
    (repo / ".quality-runner.toml").write_text(
        """
        [quality_runner.web_readiness]
        applicability = "public_web"
        reason = "Public product site"
        routes = ["/"]
        bundle_budget_gzip_bytes = 50000
        total_bundle_budget_gzip_bytes = 100000
        """,
        encoding="utf-8",
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Quality Runner Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    return repo, _git(repo, "rev-parse", "HEAD")


def _deployment_evidence(path: Path, head: str, *, console_errors: int = 0) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": DEPLOYMENT_EVIDENCE_SCHEMA,
                "observed_at": "2026-08-10T20:00:00Z",
                "target": {
                    "kind": "deployment",
                    "commit": head,
                    "url": "https://preview.example.invalid",
                    "provider": "fixture",
                    "deployment_id": "deploy-1",
                },
                "routes": [
                    {
                        "route": "/",
                        "status_code": 200,
                        "title": "Home",
                        "primary_heading_count": 1,
                        "html_lang": "en",
                        "missing_alt_count": 0,
                        "console_error_count": console_errors,
                        "network_error_count": 0,
                        "asset_error_count": 0,
                        "favicon_loaded": True,
                        "meta_description": "Fixture",
                        "og_image": "https://preview.example.invalid/social.png",
                    },
                    {
                        "route": "/__qr-not-found__",
                        "status_code": 404,
                        "not_found_probe": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_source_only_report_stays_unknown_until_runtime_evidence_exists(tmp_path: Path) -> None:
    repo, head = _fixture(tmp_path)
    report = create_web_readiness_report(repo, config=load_repo_config(repo))

    assert report["schema"] == REPORT_SCHEMA
    assert report["repository"]["head_sha"] == head
    assert report["status"] == "unknown"
    assert report["target"] == {"kind": "source", "commit": head}
    assert report["summary"]["unknown"] == 3
    assert any(
        check["id"] == "javascript_bundle_budget"
        and check["status"] == "passed"
        and check["verification_level"] == "artifact_inspected"
        for check in report["checks"]
    )


def test_deployment_evidence_produces_ready_commit_bound_report(tmp_path: Path) -> None:
    repo, head = _fixture(tmp_path)
    evidence = _deployment_evidence(tmp_path / "deployment.json", head)

    report = create_web_readiness_report(
        repo,
        config=load_repo_config(repo),
        deployment_evidence_path=evidence,
    )

    assert report["status"] == "ready"
    assert report["target"]["kind"] == "deployment"
    assert report["target"]["commit"] == head
    assert report["summary"]["minimum_verification_level"] == "artifact_inspected"
    assert any(
        check["id"] == "console_errors"
        and check["status"] == "passed"
        and check["verification_level"] == "deployment_verified"
        for check in report["checks"]
    )


def test_deployment_failure_blocks_and_wrong_commit_is_not_accepted(tmp_path: Path) -> None:
    repo, head = _fixture(tmp_path)
    failing = _deployment_evidence(tmp_path / "failing.json", head, console_errors=2)
    failed = create_web_readiness_report(
        repo,
        config=load_repo_config(repo),
        deployment_evidence_path=failing,
    )
    assert failed["status"] == "blocked"

    mismatched = _deployment_evidence(tmp_path / "mismatched.json", "0" * 40)
    blocked = create_web_readiness_report(
        repo,
        config=load_repo_config(repo),
        deployment_evidence_path=mismatched,
    )
    assert blocked["status"] == "blocked"
    assert any(
        check["id"] == "deployment_evidence" and check["status"] == "blocked"
        for check in blocked["checks"]
    )


def test_not_applicable_policy_is_explicit_and_cli_writes_stable_report(
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "library"
    repo.mkdir()
    (repo / ".quality-runner.toml").write_text(
        """
        [quality_runner.web_readiness]
        applicability = "not_applicable"
        reason = "Published Python library"
        """,
        encoding="utf-8",
    )

    assert main(["web-readiness", str(repo), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "not_applicable"
    assert payload["applicability"]["reason"] == "Published Python library"
    assert Path(payload["report_path"]).is_file()


def test_web_readiness_config_rejects_invalid_policy_without_inventing_applicability(
    tmp_path: Path,
) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        """
        [quality_runner.web_readiness]
        applicability = "everything"
        bundle_budget_gzip_bytes = 0
        """,
        encoding="utf-8",
    )
    config = load_repo_config(tmp_path)
    assert config["web_readiness"]["applicability"] == "unknown"
    assert config["web_readiness"]["bundle_budget_gzip_bytes"] == 200000
    assert len(config["warnings"]) == 2


def test_not_applicable_without_reason_remains_unknown(tmp_path: Path) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        """
        [quality_runner.web_readiness]
        applicability = "not_applicable"
        """,
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)
    assert config["web_readiness"]["applicability"] == "unknown"
    assert config["warnings"] == [
        {
            "code": "invalid_quality_runner_config_field",
            "message": (
                "quality_runner.web_readiness.reason is required when applicability "
                "is not_applicable"
            ),
        }
    ]
