from __future__ import annotations

import json
from pathlib import Path
from typing import cast


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _code_quality_scan(repo_root: Path, *, config: dict[str, object] | None = None) -> dict:
    from quality_runner.code_quality import create_code_quality_scan

    return create_code_quality_scan(
        repo_root,
        scan={"run_id": "incremental-test"},
        config=config or {},
    )


def test_code_quality_cache_reuses_unchanged_files_and_records_work(
    tmp_path: Path, monkeypatch
) -> None:
    import quality_runner.code_quality as code_quality

    for index in range(4):
        _write(tmp_path / "src" / f"file-{index}.ts", f"const value{index}: any = {{}};\n")

    calls: list[str] = []
    original_scan_file = code_quality._scan_file

    def counted_scan_file(**kwargs: object) -> list[dict[str, object]]:
        calls.append(str(kwargs["relative_path"]))
        return original_scan_file(
            relative_path=cast(str, kwargs["relative_path"]),
            text=cast(str, kwargs["text"]),
            lines=cast(list[str], kwargs["lines"]),
            disabled_groups=cast(set[str], kwargs["disabled_groups"]),
            large_file_lines=cast(int, kwargs["large_file_lines"]),
            fat_router_lines=cast(int, kwargs["fat_router_lines"]),
        )

    monkeypatch.setattr(code_quality, "_scan_file", counted_scan_file)

    first = _code_quality_scan(tmp_path)
    second = _code_quality_scan(tmp_path)

    assert len(calls) == 4
    assert first["analysis_cache"]["cache_misses"] == 4
    assert second["analysis_cache"]["cache_hits"] == 4
    assert second["analysis_cache"]["cache_misses"] == 0
    assert second["analysis_cache"]["status"] == "warm"
    assert first["findings"] == second["findings"]
    assert (
        tmp_path / ".quality-runner" / "cache" / "incremental-analysis-v1" / "index.json"
    ).exists()


def test_editing_one_source_file_recomputes_only_that_file(tmp_path: Path, monkeypatch) -> None:
    import quality_runner.code_quality as code_quality

    _write(tmp_path / "src" / "changed.ts", "const changed: any = {};\n")
    _write(tmp_path / "src" / "stable.ts", "const stable = true;\n")
    _write(tmp_path / "src" / "third.ts", "const third = false;\n")
    _code_quality_scan(tmp_path)

    calls: list[str] = []
    original_scan_file = code_quality._scan_file

    def counted_scan_file(**kwargs: object) -> list[dict[str, object]]:
        calls.append(str(kwargs["relative_path"]))
        return original_scan_file(
            relative_path=cast(str, kwargs["relative_path"]),
            text=cast(str, kwargs["text"]),
            lines=cast(list[str], kwargs["lines"]),
            disabled_groups=cast(set[str], kwargs["disabled_groups"]),
            large_file_lines=cast(int, kwargs["large_file_lines"]),
            fat_router_lines=cast(int, kwargs["fat_router_lines"]),
        )

    monkeypatch.setattr(code_quality, "_scan_file", counted_scan_file)
    _write(tmp_path / "src" / "changed.ts", "const changed = true;\n")

    result = _code_quality_scan(tmp_path)

    assert calls == ["src/changed.ts"]
    assert result["analysis_cache"]["cache_hits"] == 2
    assert result["analysis_cache"]["cache_misses"] == 1
    assert result["analysis_cache"]["invalidation_reasons"] == {"source-content-changed": 1}
    assert result["analysis_cache"]["recomputed_path_samples"] == ["src/changed.ts"]
    assert all(finding["file"] != "src/changed.ts" for finding in result["findings"])


def test_scanner_configuration_and_version_changes_invalidate_entries(
    tmp_path: Path, monkeypatch
) -> None:
    import quality_runner.incremental_analysis_cache as cache_module

    _write(tmp_path / "src" / "one.ts", "const one: any = {};\n")
    _write(tmp_path / "src" / "two.ts", "const two: any = {};\n")
    _code_quality_scan(tmp_path)

    configured = _code_quality_scan(
        tmp_path,
        config={"structural_scan": {"disabled_rule_groups": ["harden"]}},
    )
    assert configured["analysis_cache"]["cache_misses"] == 2
    assert configured["analysis_cache"]["invalidation_reasons"] == {
        "scanner-configuration-changed": 2
    }

    monkeypatch.setattr(cache_module, "__version__", "0.6.0-cache-test")
    version_changed = _code_quality_scan(
        tmp_path,
        config={"structural_scan": {"disabled_rule_groups": ["harden"]}},
    )
    assert version_changed["analysis_cache"]["cache_misses"] == 2
    assert version_changed["analysis_cache"]["invalidation_reasons"] == {
        "quality-runner-version-changed": 2
    }


def test_dependency_state_change_invalidates_other_source_files(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", '{"name":"fixture","dependencies":{"one":"1.0.0"}}\n')
    _write(tmp_path / "src" / "one.ts", "const one = true;\n")
    _write(tmp_path / "src" / "two.ts", "const two = false;\n")
    _code_quality_scan(tmp_path)

    _write(tmp_path / "package.json", '{"name":"fixture","dependencies":{"one":"2.0.0"}}\n')
    result = _code_quality_scan(tmp_path)

    assert result["analysis_cache"]["cache_misses"] == 3
    assert result["analysis_cache"]["invalidation_reasons"]["dependency-state-changed"] == 3


def test_corrupt_entries_and_index_recompute_fail_closed(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "one.ts", "const one: any = {};\n")
    _code_quality_scan(tmp_path)

    cache_root = tmp_path / ".quality-runner" / "cache" / "incremental-analysis-v1"
    index_path = cache_root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    entry = index["entries"]["code-quality:src/one.ts"]
    entry_path = cache_root / "entries" / f"{entry['cache_key']}.json"

    del entry["content_sha256"]
    index_path.write_text(json.dumps(index), encoding="utf-8")
    malformed_index = _code_quality_scan(tmp_path)
    assert malformed_index["analysis_cache"]["invalidation_reasons"] == {
        "cache-index-corrupt": 1
    }

    index = json.loads(index_path.read_text(encoding="utf-8"))
    entry = index["entries"]["code-quality:src/one.ts"]
    entry_path = cache_root / "entries" / f"{entry['cache_key']}.json"
    entry_path.unlink()

    missing_entry = _code_quality_scan(tmp_path)
    assert missing_entry["analysis_cache"]["invalidation_reasons"] == {"missing-entry": 1}

    entry_path.write_text("{not-json", encoding="utf-8")
    corrupt_entry = _code_quality_scan(tmp_path)
    assert corrupt_entry["analysis_cache"]["invalidation_reasons"] == {"corrupt-entry": 1}

    index_path.write_text("{interrupted", encoding="utf-8")
    corrupt_index = _code_quality_scan(tmp_path)
    assert corrupt_index["analysis_cache"]["invalidation_reasons"] == {"cache-index-corrupt": 1}


def test_prior_run_artifacts_are_not_scan_inputs_or_cache_entries(tmp_path: Path) -> None:
    for index in range(76):
        run_dir = tmp_path / ".quality-runner" / "runs" / f"prior-{index:03d}"
        _write(run_dir / "code-quality-scan.json", '{"finding":"const artifact: any = {};"}\n')
        _write(run_dir / "nested" / "artifact.ts", "const artifact: any = {};\n")
    _write(tmp_path / "src" / "source.ts", "const source: any = {};\n")

    result = _code_quality_scan(tmp_path)

    assert {item["path"] for item in result["accountability"]} == {"src/source.ts"}
    assert {finding["file"] for finding in result["findings"]} == {"src/source.ts"}
    assert all(
        ".quality-runner" not in path
        for path in result["analysis_cache"]["recomputed_path_samples"]
    )
    assert not list(
        (tmp_path / ".quality-runner" / "cache" / "incremental-analysis-v1" / "entries").glob(
            "*prior*"
        )
    )


def test_security_cache_reuses_unchanged_file_results(tmp_path: Path, monkeypatch) -> None:
    import quality_runner.security.scan as security_scan

    _write(tmp_path / "package.json", '{"name":"security-fixture"}\n')
    _write(tmp_path / "src" / "unsafe.js", "const result = eval(userInput);\n")
    calls: list[str] = []
    original_scan_candidates = security_scan.scan_security_candidates

    def counted_scan_candidates(**kwargs: object) -> list[dict[str, object]]:
        files = cast(list[dict[str, object]], kwargs["scanned_files"])
        calls.extend(str(item["path"]) for item in files)
        return original_scan_candidates(
            scanned_files=files,
            disabled_groups=cast(list[str], kwargs["disabled_groups"]),
            surfaces=cast(dict[str, bool], kwargs["surfaces"]),
        )

    monkeypatch.setattr(security_scan, "scan_security_candidates", counted_scan_candidates)
    first = security_scan.create_security_scan(tmp_path, scan={"run_id": "security"}, config={})
    second = security_scan.create_security_scan(tmp_path, scan={"run_id": "security"}, config={})

    assert len(calls) == 2
    assert first["candidates"] == second["candidates"]
    assert second["analysis_cache"]["cache_hits"] == 2
    assert second["analysis_cache"]["cache_misses"] == 0


def test_refresh_retention_preserves_all_current_phase_runs(tmp_path: Path) -> None:
    from quality_runner.workflow import refresh_payload

    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.artifacts]\nretention_runs = 3\n",
        encoding="utf-8",
    )
    _write(tmp_path / "src" / "source.ts", "const source = true;\n")

    for prefix in ("refresh-old-1", "refresh-old-2", "refresh-current"):
        refresh_payload(repo_root=tmp_path, run_id_prefix=prefix)

    runs = sorted(
        path.name for path in (tmp_path / ".quality-runner" / "runs").iterdir() if path.is_dir()
    )
    assert runs == [
        "refresh-current-inspect",
        "refresh-current-run",
        "refresh-current-verify",
    ]
    artifact = json.loads(
        (
            tmp_path
            / ".quality-runner"
            / "runs"
            / "refresh-current-run"
            / "code-quality-scan.json"
        ).read_text(encoding="utf-8")
    )
    assert artifact["analysis_cache"]["schema"] == (
        "quality-runner-incremental-analysis-cache-v0.1"
    )
