from __future__ import annotations

import json
from pathlib import Path

from quality_runner.cli import main
from quality_runner.security.codex import (
    compare_codex_evidence,
    export_codex_handoff,
    import_codex_evidence,
    validate_codex_document,
)


def _report(*, coverage: dict[str, object], findings: list[dict[str, object]]) -> dict[str, object]:
    return {
        "source": {"provider": "codex-security", "report": "test"},
        "revision": {"commit": "abc123"},
        "coverage": coverage,
        "findings": findings,
    }


def _finding(*, finding_id: str = "F-1") -> dict[str, object]:
    return {
        "id": finding_id,
        "rule_id": "sql-injection",
        "severity": "high",
        "summary": "User input reaches a query",
        "locations": [{"file": "src/api.py", "line": 42}],
        "validation": "confirmed in the validation sandbox",
    }


def test_import_uses_quality_finding_contract_and_stable_hash() -> None:
    artifact = import_codex_evidence(
        _report(
            coverage={"status": "complete", "scope": "repository"},
            findings=[_finding()],
        )
    )

    assert artifact["contract_schema"] == "quality-evidence-v0.1"
    assert artifact["findings"][0]["schema"] == "quality-finding-v0.1"
    assert artifact["findings"][0]["match_key"] == "provider:f-1"
    assert validate_codex_document(artifact)["passed"] is True

    reordered = import_codex_evidence(
        _report(
            coverage={"scope": "repository", "complete": True},
            findings=[_finding()],
        )
    )
    assert reordered["evidence_hash"] == artifact["evidence_hash"]


def test_disappeared_finding_is_unknown_without_complete_follow_up_coverage() -> None:
    baseline = import_codex_evidence(
        _report(
            coverage={"status": "complete", "scope": "repository"},
            findings=[_finding()],
        )
    )
    partial_follow_up = import_codex_evidence(
        _report(coverage={"status": "partial", "scope": "changed"}, findings=[])
    )
    complete_follow_up = import_codex_evidence(
        _report(coverage={"status": "complete"}, findings=[])
    )

    partial_comparison = compare_codex_evidence(baseline, partial_follow_up)
    complete_comparison = compare_codex_evidence(baseline, complete_follow_up)
    assert partial_comparison["matches"][0]["status"] == "unknown"
    assert partial_comparison["summary"]["follow_up_coverage_complete"] is False
    assert complete_comparison["matches"][0]["status"] == "resolved"


def test_semantic_alias_matches_when_provider_id_changes() -> None:
    baseline = import_codex_evidence(
        _report(coverage={"complete": True, "scope": "repository"}, findings=[_finding()])
    )
    changed_id = _finding(finding_id="new-provider-id")
    current = import_codex_evidence(
        _report(coverage={"complete": True, "scope": "repository"}, findings=[changed_id])
    )

    comparison = compare_codex_evidence(baseline, current)
    assert comparison["summary"]["present"] == 1
    assert comparison["summary"]["new"] == 0
    assert comparison["summary"]["unknown"] == 0
    assert comparison["matches"][0]["match_key"].startswith("semantic:")


def test_export_is_hash_bound_and_retains_unknown_findings() -> None:
    baseline = import_codex_evidence(
        _report(coverage={"complete": True, "scope": "repository"}, findings=[_finding()])
    )
    current = import_codex_evidence(_report(coverage={"status": "unknown"}, findings=[]))
    comparison = compare_codex_evidence(baseline, current)
    handoff = export_codex_handoff(comparison)

    assert handoff["status"] == "unknown"
    assert handoff["findings"][0]["status"] == "unknown"
    assert validate_codex_document(handoff)["passed"] is True

    handoff["comparison"]["summary"]["unknown"] = 0
    assert validate_codex_document(handoff)["passed"] is False


def test_security_cli_round_trip_writes_hash_bound_artifacts(tmp_path: Path, capsys) -> None:
    source_path = tmp_path / "codex.json"
    evidence_path = tmp_path / "evidence.json"
    current_path = tmp_path / "current.json"
    comparison_path = tmp_path / "comparison.json"
    handoff_path = tmp_path / "handoff.json"
    source_path.write_text(
        json.dumps(
            _report(
                coverage={"complete": True, "scope": "repository"},
                findings=[_finding()],
            )
        ),
        encoding="utf-8",
    )
    current_path.write_text(
        json.dumps(_report(coverage={"status": "partial", "scope": "changed"}, findings=[])),
        encoding="utf-8",
    )

    assert (
        main(
            ["security", "import-codex", str(source_path), "--output", str(evidence_path), "--json"]
        )
        == 0
    )
    assert (
        main(
            ["security", "import-codex", str(current_path), "--output", str(current_path), "--json"]
        )
        == 0
    )
    assert (
        main(
            [
                "security",
                "compare",
                str(evidence_path),
                str(current_path),
                "--output",
                str(comparison_path),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(["security", "export", str(comparison_path), "--output", str(handoff_path), "--json"])
        == 0
    )
    assert main(["security", "validate", str(handoff_path), "--json"]) == 0

    output = capsys.readouterr().out
    assert '"status": "unknown"' in output
