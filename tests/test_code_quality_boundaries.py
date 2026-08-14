from __future__ import annotations

from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_code_quality_scan_ignores_shadow_vendor_cache_and_build_variants(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / ".aios" / "shadow-worktrees" / "copy" / "src" / "shadow.ts",
        "const shadow: any = {};\n",
    )
    _write(
        tmp_path / ".worktrees" / "feature-copy" / "src" / "copy.ts",
        "const copy: any = {};\n",
    )
    _write(
        tmp_path / ".claude" / "worktrees" / "feature-copy" / "src" / "copy.ts",
        "const claude_copy: any = {};\n",
    )
    _write(
        tmp_path / ".codex" / "worktrees" / "feature-copy" / "src" / "copy.ts",
        "const codex_copy: any = {};\n",
    )
    for agent_dir in (".aider", ".continue", ".cursor"):
        _write(tmp_path / agent_dir / "scratch.ts", "const scratch: any = {};\n")
    _write(
        tmp_path / "apps" / "dashboard" / ".next-broken-20260323-1" / "server" / "_error.js",
        "eval(userInput);\n",
    )
    _write(
        tmp_path
        / ".tmp"
        / "uv-bootstrap"
        / "lib"
        / "python3.14"
        / "site-packages"
        / "pip"
        / "x.py",
        "value = any([True])\n",
    )
    _write(
        tmp_path / "packages" / "web" / "node_modules" / "lib" / "index.ts",
        "const dependency: any = {};\n",
    )
    _write(tmp_path / ".pnpm-store" / "index.ts", "const store: any = {};\n")
    _write(
        tmp_path / ".uv-cache" / "archive-v0" / "setuptools" / "dist.py",
        "value = any([True])\n",
    )
    _write(tmp_path / "data" / "fixture.json", '{"value": "not source"}\n')
    _write(tmp_path / "logs" / "run.md", "const logged: any = {};\n")
    _write(tmp_path / "staging" / "takeout" / "raw.md", "const staged: any = {};\n")
    _write(tmp_path / "tmcp-benchmark" / "tasks" / "case.md", "const benchmark: any = {};\n")
    _write(tmp_path / "apps" / "web" / "public" / "dashboard_data" / "row.json", "{}\n")
    _write(tmp_path / "src" / "data" / "model.ts", "const model: any = {};\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    scanned_paths = {item["path"] for item in result["accountability"]}
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}
    finding_files = {finding["file"] for finding in result["findings"]}

    assert scanned_paths == {"src/data/model.ts", "src/index.ts"}
    assert skipped[".aios"] == "scan exclusion"
    assert skipped[".claude/worktrees"] == "scan exclusion"
    assert skipped[".codex/worktrees"] == "scan exclusion"
    assert skipped[".aider"] == "scan exclusion"
    assert skipped[".continue"] == "scan exclusion"
    assert skipped[".cursor"] == "scan exclusion"
    assert skipped[".worktrees"] == "ignored directory"
    assert skipped["apps/dashboard/.next-broken-20260323-1"] == "ignored directory"
    assert skipped[".tmp"] == "ignored directory"
    assert skipped[".pnpm-store"] == "ignored directory"
    assert skipped[".uv-cache"] == "artifact directory"
    assert skipped["data"] == "ignored directory"
    assert skipped["logs"] == "ignored directory"
    assert skipped["staging"] == "ignored directory"
    assert skipped["tmcp-benchmark"] == "ignored directory"
    assert skipped["packages/web/node_modules"] == "ignored directory"
    assert skipped["apps/web/public"] == "ignored directory"
    assert finding_files == {"src/data/model.ts", "src/index.ts"}


def test_code_quality_scan_reports_estimated_cost_for_skipped_paths(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    for index in range(3):
        _write(tmp_path / "data" / f"row-{index}.json", "{}\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})
    skipped = {item["path"]: item for item in result["skipped_files"]}

    assert skipped["data"]["estimated_text_files"] == 3
    assert skipped["data"]["estimated_scan_seconds"] > 0
    assert skipped["data"]["include_config_hint"] == (
        '[quality_runner.structural_scan] include_ignored_paths = ["data"]'
    )
    assert result["summary"]["skipped_estimated_text_files"] == 3
    assert result["summary"]["skipped_estimated_scan_seconds"] > 0


def test_code_quality_scan_skips_top_level_artifact_output_dirs(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "src" / "index.ts", "const source: any = {};\n")
    _write(tmp_path / ".local" / "court-vision" / "scratch.ts", "const local: any = {};\n")
    _write(tmp_path / "artifacts" / "audit" / "report.ts", "const artifact: any = {};\n")
    _write(tmp_path / "outputs" / "run" / "summary.md", "const output: any = {};\n")
    _write(tmp_path / "reports" / "figures" / "chart.ts", "const report: any = {};\n")
    _write(tmp_path / "figures" / "chart.ts", "const figure: any = {};\n")
    _write(tmp_path / "plots" / "chart.ts", "const plot: any = {};\n")

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    scanned_paths = {item["path"] for item in result["accountability"]}
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}
    finding_files = {finding["file"] for finding in result["findings"]}

    assert scanned_paths == {"src/index.ts"}
    assert skipped[".local"] == "artifact directory"
    assert skipped["artifacts"] == "artifact directory"
    assert skipped["outputs"] == "artifact directory"
    assert skipped["reports"] == "artifact directory"
    assert skipped["figures"] == "artifact directory"
    assert skipped["plots"] == "artifact directory"
    assert finding_files == {"src/index.ts"}


def test_code_quality_scan_skips_generated_lock_and_build_metadata_files(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "src" / "index.ts", "const source: any = {};\n")
    _write(tmp_path / "pnpm-lock.yaml", "lockfileVersion: 9\n# const lock: any = {}\n")
    _write(tmp_path / "package-lock.json", '{"packages": {"x": "const lock: any = {}"}}\n')
    _write(tmp_path / "src" / "lib" / "generated-leaderboard.ts", "const generated: any = {};\n")
    _write(tmp_path / "tsconfig.tsbuildinfo", '{"program": "generated"}\n')

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    scanned_paths = {item["path"] for item in result["accountability"]}
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}

    assert scanned_paths == {"src/index.ts"}
    assert skipped["pnpm-lock.yaml"] == "generated file"
    assert skipped["package-lock.json"] == "generated file"
    assert skipped["src/lib/generated-leaderboard.ts"] == "generated file"
    assert skipped["tsconfig.tsbuildinfo"] == "generated file"


def test_code_quality_scan_stops_at_configured_file_budget(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    for index in range(5):
        _write(tmp_path / "src" / f"file-{index}.ts", f"const value{index}: any = {{}};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-budget"},
        config={"structural_scan": {"max_text_files": 2}},
    )

    scanned_paths = [item["path"] for item in result["accountability"]]
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}

    assert scanned_paths == ["src/file-0.ts", "src/file-1.ts"]
    assert skipped == {
        "src/file-2.ts": "scan budget exceeded",
        "src/file-3.ts": "scan budget exceeded",
        "src/file-4.ts": "scan budget exceeded",
    }
    assert result["summary"]["scan_budget"] == {
        "max_text_files": 2,
        "scanned_text_files": 2,
        "budget_exceeded": True,
        "skipped_text_files": 3,
    }


def test_code_quality_scan_can_include_default_ignored_paths(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "data" / "model.ts", "const included: any = {};\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={"structural_scan": {"include_ignored_paths": ["data"]}},
    )

    scanned_paths = {item["path"] for item in result["accountability"]}
    finding_files = {finding["file"] for finding in result["findings"]}

    assert {"data/model.ts", "src/index.ts"} <= scanned_paths
    assert "data/model.ts" in finding_files
    assert all(item["path"] != "data" for item in result["skipped_files"])


def test_quality_runner_source_files_stay_under_default_large_file_threshold() -> None:
    from quality_runner.code_quality import DEFAULT_LARGE_FILE_LINES

    repo_root = Path(__file__).resolve().parents[1]
    oversized: dict[str, int] = {}
    for path in sorted((repo_root / "quality_runner").rglob("*.py")):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > DEFAULT_LARGE_FILE_LINES:
            oversized[path.relative_to(repo_root).as_posix()] = line_count

    assert oversized == {}
