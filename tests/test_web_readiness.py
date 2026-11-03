from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from quality_runner.cli import main
from quality_runner.config import load_repo_config
from quality_runner.fleet.maturity_dimensions import assess_maturity_dimensions
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


def _performance_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    repo, _ = _fixture(tmp_path)
    with (repo / ".quality-runner.toml").open("a", encoding="utf-8") as stream:
        stream.write("""
[[quality_runner.web_readiness.performance_budgets]]
id = "home-lcp"
metric = "lcp_ms"
maximum = 200
statistic = "median"
min_samples = 3
max_age_hours = 24
policy = "block"
owner = "web-team"
rationale = "Fixture acceptance contract"
method = "navigation"
scenario = { route = "/", journey = "home-load", device = "desktop", network = "local", cpu = "native", cache = "cold", dataset = "fixture-v1" }
""")
    _git(repo, "add", ".quality-runner.toml")
    _git(repo, "commit", "-qm", "Declare performance acceptance")
    head = _git(repo, "rev-parse", "HEAD")
    payload: dict[str, Any] = {
        "schema": "quality-runner-web-performance-evidence/v1",
        "observed_at": "2026-11-03T12:00:00Z",
        "target": {"commit": head, "build_mode": "production", "build_id": "sha256:" + "a" * 64},
        "tool": {"name": "browser-fixture", "version": "1.0"},
        "command": "node scripts/measure-performance.mjs",
        "measurements": [
            {
                "budget_id": "home-lcp",
                "metric": "lcp_ms",
                "method": "navigation",
                "scenario": {
                    "route": "/",
                    "journey": "home-load",
                    "device": "desktop",
                    "network": "local",
                    "cpu": "native",
                    "cache": "cold",
                    "dataset": "fixture-v1",
                },
                "samples": [100, 300, 200],
            }
        ],
    }
    path = tmp_path / "performance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return repo, path, payload


def _performance_report(repo: Path, evidence: Path | None) -> dict[str, Any]:
    return create_web_readiness_report(
        repo,
        config=load_repo_config(repo),
        performance_evidence_path=evidence,
        generated_at="2026-11-03T13:00:00Z",
    )


def _performance_check(report: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in report["checks"] if item["id"] == "performance:home-lcp")


@pytest.mark.parametrize(
    "metric,method,statistic,samples",
    [
        ("lcp_ms", "navigation", "median", [100, 300, 200]),
        ("inp_ms", "interaction", "max", [100, 200, 150]),
        ("js_transfer_bytes", "navigation", "median", [100, 300, 200]),
    ],
)
def test_cli_imports_repeated_lab_measurements(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    metric: str,
    method: str,
    statistic: str,
    samples: list[int],
) -> None:
    from datetime import UTC, datetime

    repo, evidence, payload = _performance_fixture(tmp_path)
    config_path = repo / ".quality-runner.toml"
    config_path.write_text(
        config_path.read_text()
        .replace('metric = "lcp_ms"', f'metric = "{metric}"')
        .replace('method = "navigation"', f'method = "{method}"')
        .replace('statistic = "median"', f'statistic = "{statistic}"'),
        encoding="utf-8",
    )
    _git(repo, "add", ".quality-runner.toml")
    _git(repo, "commit", "--allow-empty", "-qm", "Declare metric scenario")
    payload["target"]["commit"] = _git(repo, "rev-parse", "HEAD")
    payload["measurements"][0].update(metric=metric, method=method, samples=samples)
    payload["observed_at"] = datetime.now(UTC).isoformat()
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    deployment = _deployment_evidence(tmp_path / "deployment.json", _git(repo, "rev-parse", "HEAD"))
    args = [
        "web-readiness",
        str(repo),
        "--performance-evidence",
        str(evidence),
        "--deployment-evidence",
        str(deployment),
        "--json",
    ]
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    check = _performance_check(report)
    assert check["status"] == "passed"
    assert check["verification_level"] == "browser_rendered"
    assert check["evidence"][0]["value"] == 200
    assert check["evidence"][0]["minimum"] == 100
    assert check["evidence"][0]["maximum"] == max(samples)
    assert check["evidence"][0]["sample_count"] == 3

    payload["measurements"][0]["samples"] = [201, 301, 401]
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    assert main(args) == 1
    assert _performance_check(json.loads(capsys.readouterr().out))["status"] == "failed"

    assert main(["web-readiness", str(repo), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "unknown"


@pytest.mark.parametrize(
    "case",
    [
        "commit",
        "development",
        "missing-build",
        "stale",
        "future",
        "bad-date",
        "timezone",
        "context",
        "metric",
        "method",
        "boolean",
        "nan",
        "negative",
        "too-few",
        "duplicate",
        "missing-tool",
        "missing-command",
        "field",
        "dirty",
        "huge-integer",
        "aggregate-overflow",
        "nested-json",
    ],
)
def test_invalid_evidence_never_passes(tmp_path: Path, case: str) -> None:
    repo, path, payload = _performance_fixture(tmp_path)
    measurement = payload["measurements"][0]
    if case == "commit":
        payload["target"]["commit"] = "0" * 40
    elif case == "development":
        payload["target"]["build_mode"] = "development"
    elif case == "missing-build":
        del payload["target"]["build_id"]
    elif case in {"stale", "future", "bad-date", "timezone"}:
        payload["observed_at"] = {
            "stale": "2026-11-01T12:00:00Z",
            "future": "2026-11-04T12:00:00Z",
            "bad-date": "not-a-date",
            "timezone": "2026-11-03T12:00:00",
        }[case]
    elif case == "context":
        measurement["scenario"]["cache"] = "warm"
    elif case == "metric":
        measurement["metric"] = "cls"
    elif case == "method":
        measurement["method"] = "interaction"
    elif case in {"boolean", "nan", "negative", "too-few"}:
        measurement["samples"] = {
            "boolean": [True, 100, 100],
            "nan": [float("nan"), 100, 100],
            "negative": [-1, 100, 100],
            "too-few": [100],
        }[case]
    elif case == "aggregate-overflow":
        measurement["samples"] = [1e308] * 4
    elif case == "huge-integer":
        measurement["samples"] = [10**400, 100, 100]
    elif case == "nested-json":
        path.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
        assert _performance_check(_performance_report(repo, path))["status"] == "blocked"
        return
    elif case == "duplicate":
        payload["measurements"].append(dict(measurement))
    elif case == "missing-tool":
        payload["tool"] = {"name": "browser-fixture"}
    elif case == "missing-command":
        del payload["command"]
    elif case == "field":
        measurement["method"] = "field"
    elif case == "dirty":
        (repo / "src" / "app.html").write_text("changed source", encoding="utf-8")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _performance_check(_performance_report(repo, path))["status"] == "blocked"


@pytest.mark.parametrize("policy", ["warn", "block"])
def test_missing_evidence_respects_declared_policy(tmp_path: Path, policy: str) -> None:
    repo, _, _ = _performance_fixture(tmp_path)
    config = load_repo_config(repo)
    config["web_readiness"]["performance_budgets"][0]["policy"] = policy
    report = create_web_readiness_report(repo, config=config)
    check = _performance_check(report)
    assert check["status"] == "unknown"
    assert check["policy"] == policy


@pytest.mark.parametrize(
    "field,value",
    [
        ("maximum", -1),
        ("maximum", True),
        ("maximum", float("inf")),
        ("min_samples", 0),
        ("max_age_hours", 0),
        ("statistic", "p75"),
        ("policy", "ignore"),
        ("owner", ""),
        ("rationale", ""),
        ("scenario", {}),
        ("metric", "score"),
        ("metric", "inp_ms"),
        ("id", ""),
        ("duplicate", None),
    ],
)
def test_invalid_budget_remains_blocking(tmp_path: Path, field: str, value: object) -> None:
    from quality_runner.web_readiness_config import parse_web_readiness_section

    repo, _, _ = _performance_fixture(tmp_path)
    config = load_repo_config(repo)["web_readiness"]
    if field == "duplicate":
        config["performance_budgets"].append(dict(config["performance_budgets"][0]))
    else:
        config["performance_budgets"][0][field] = value
    warnings: list[dict[str, str]] = []
    parsed = parse_web_readiness_section(config, warnings)
    report = create_web_readiness_report(repo, config={"web_readiness": parsed})
    assert warnings
    assert any(
        item["id"] == "performance_policy" and item["status"] == "blocked"
        for item in report["checks"]
    )


def test_artifact_defaults_are_labeled_without_changing_legacy_results(tmp_path: Path) -> None:
    from quality_runner.web_readiness_config import parse_web_readiness_section

    repo, _ = _fixture(tmp_path)
    config = parse_web_readiness_section({"applicability": "public_web"}, [])
    report = create_web_readiness_report(repo, config={"web_readiness": config})
    check = next(item for item in report["checks"] if item["id"] == "javascript_bundle_budget")
    assert check["status"] == "passed"
    assert check["evidence"][0]["budget_origin"] == "legacy_defaults"
    assert check["evidence"][0]["measurement_scope"] == "build_artifact_inventory"
    assert "route transfer" in check["detail"].lower()


def test_fleet_performance_keeps_unmeasured_budgets_unknown(tmp_path: Path) -> None:
    repo, _, _ = _performance_fixture(tmp_path)
    assessments = assess_maturity_dimensions(
        root=repo,
        repository={},
        scan={},
        documents={},
        config=load_repo_config(repo),
        as_of="2026-11-03T13:00:00Z",
    )
    assert assessments["performance"]["status"] == "unknown"
