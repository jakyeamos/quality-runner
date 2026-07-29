from __future__ import annotations

from pathlib import Path

from quality_runner.artifacts import write_json
from quality_runner.code_quality import create_code_quality_scan
from quality_runner.delivery_contract import (
    preflight_delivery_contract,
    prepare_delivery_contract,
    reconcile_delivery_contract,
    refresh_delivery_contract,
)


def _write_fixture(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "main.ts").write_text(
        "export const value: any = {};\n",
        encoding="utf-8",
    )


def test_external_cache_does_not_write_target_checkout(tmp_path: Path) -> None:
    external = tmp_path / "external-cache"
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fixture(repo)

    result = create_code_quality_scan(
        repo,
        scan={"run_id": "external-cache"},
        config={},
        cache_mode="external",
        cache_root=external,
    )

    assert result["analysis_cache"]["cache_mode"] == "external"  # type: ignore[index]
    assert (external).exists()
    assert not (repo / ".quality-runner" / "cache").exists()


def test_balanced_scan_records_deferred_global_checks(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "balanced"},
        config={},
        analysis_mode="balanced",
        cache_mode="disabled",
    )

    assert result["coverage"] == "partial"
    assert {item["check"] for item in result["deferred_checks"]} == {
        "similarity",
        "ponytail",
        "bundle",
        "unwired",
        "architecture",
    }


def test_balanced_warm_scan_reuses_cached_file_results_without_source_reads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_fixture(tmp_path)
    import quality_runner.incremental_analysis_cache as cache_module

    reads: list[str] = []
    original_read = cache_module._read_source_text

    def counted_read(path: Path) -> str:
        reads.append(str(path))
        return original_read(path)

    monkeypatch.setattr(cache_module, "_read_source_text", counted_read)
    first = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "warm-one"},
        config={},
        analysis_mode="balanced",
        cache_mode="repo",
    )
    first_read_count = len(reads)
    second = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "warm-two"},
        config={},
        analysis_mode="balanced",
        cache_mode="repo",
    )

    assert first_read_count == 1
    assert len(reads) == first_read_count
    assert second["analysis_cache"]["cache_hits"] == 1  # type: ignore[index]
    assert second["analysis_cache"]["source_bytes_read"] == 0  # type: ignore[index]
    assert first["findings"] == second["findings"]


def test_delivery_contract_lifecycle_uses_immutable_contract_ids(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    prepared = prepare_delivery_contract(
        tmp_path,
        run_id="delivery-prepare",
        phase_id="phase-1",
        plan_id="plan-1",
        intent="Improve the planning loop",
        cache_mode="disabled",
    )
    prepared_path = Path(prepared["contract_path"])
    assert prepared["schema"] == "quality-runner-delivery-contract-v0.1"
    assert prepared["contract_stage"] == "prepare"
    assert prepared["performance"]["schema"] == "quality-runner-performance-v0.1"  # type: ignore[index]
    assert prepared_path.is_file()

    refreshed = refresh_delivery_contract(
        tmp_path,
        contract_path=prepared_path,
        run_id="delivery-refresh",
        context_refs=["context.md"],
        research_refs=["research.md"],
        cache_mode="disabled",
    )
    assert refreshed["contract_stage"] == "refresh"
    assert refreshed["contract_id"] != prepared["contract_id"]
    assert refreshed["parent_contract_id"] == prepared["contract_id"]


def test_preflight_reads_contract_and_plan_without_rescanning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_fixture(tmp_path)
    contract = prepare_delivery_contract(
        tmp_path,
        run_id="delivery-preflight",
        cache_mode="disabled",
    )
    contract_path = Path(contract["contract_path"])
    plan_path = tmp_path / "PLAN.md"
    plan_path.write_text(
        "# Plan\n\n" + "\n".join(str(item["id"]) for item in contract["obligations"]),
        encoding="utf-8",
    )

    def fail_scan(**_: object) -> dict[str, object]:
        raise AssertionError("preflight must not rescan")

    monkeypatch.setattr("quality_runner.delivery_contract.run_payload", fail_scan)
    result = preflight_delivery_contract(
        tmp_path,
        contract_path=contract_path,
        plan_path=plan_path,
    )

    assert result["plan_scanned"] is False
    assert result["status"] == "ready"
    assert result["blockers"] == []


def test_reconcile_blocks_missing_hard_evidence_and_accepts_matching_receipt(
    tmp_path: Path,
) -> None:
    _write_fixture(tmp_path)
    contract = prepare_delivery_contract(
        tmp_path,
        run_id="delivery-reconcile",
        cache_mode="disabled",
    )
    contract_path = Path(contract["contract_path"])
    hard_obligations = [
        item for item in contract["obligations"] if item.get("kind") == "hard"
    ]
    missing_path = tmp_path / "missing-result.json"
    write_json(
        missing_path,
        {
            "schema": "quality-runner-delivery-result-v0.1",
            "source_fingerprints": contract["source_fingerprints"],
            "obligation_results": [],
        },
    )
    blocked = reconcile_delivery_contract(
        tmp_path,
        contract_path=contract_path,
        result_path=missing_path,
        run_id="delivery-reconcile",
    )
    assert blocked["status"] == ("blocked" if hard_obligations else "reconciled")
    if hard_obligations:
        assert any(item["type"] == "missing_evidence" for item in blocked["blockers"])

    result_path = tmp_path / "complete-result.json"
    write_json(
        result_path,
        {
            "schema": "quality-runner-delivery-result-v0.1",
            "source_fingerprints": contract["source_fingerprints"],
            "obligation_results": [
                {
                    "obligation_id": item["id"],
                    "status": "passed",
                    "evidence_refs": ["verification.log"],
                }
                for item in contract["obligations"]
            ],
        },
    )
    reconciled = reconcile_delivery_contract(
        tmp_path,
        contract_path=contract_path,
        result_path=result_path,
        run_id="delivery-reconcile",
    )
    assert reconciled["status"] == "reconciled"
