from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quality_runner.cli import build_parser
from quality_runner.exclusion_preflight import (
    EXCLUSION_REPORT_SCHEMA,
    build_exclusion_packet,
    normalize_run_only_exclusion_paths,
    packet_sha256,
    run_exclusion_preflight_command,
    validate_exclusion_packet,
    validate_exclusion_report,
)
from quality_runner.workflow import inspect_payload


def _make_candidate(repo_root: Path, relative: str = "generated-output") -> None:
    candidate = repo_root / relative
    candidate.mkdir(parents=True)
    for index in range(3):
        (candidate / f"result-{index}.json").write_text('{"generated": true}\n', encoding="utf-8")


def _write_config(repo_root: Path) -> Path:
    path = repo_root / ".quality-runner.toml"
    path.write_text(
        "[quality_runner]\n"
        "gate_timeouts = { tests = 30 }\n"
        "[quality_runner.structural_scan]\n"
        "max_text_files = 500\n",
        encoding="utf-8",
    )
    return path


def _read_packet(result: dict[str, object]) -> dict[str, object]:
    artifact_paths = result["artifact_paths"]
    assert isinstance(artifact_paths, dict)
    packet_path = Path(str(artifact_paths["scan_exclusion_preflight_packet_json"]))
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _report_for(
    packet: dict[str, object], repo_root: Path, decision: str = "exclude"
) -> dict[str, object]:
    candidates = packet["candidates"]
    assert isinstance(candidates, list)
    decisions: list[dict[str, object]] = []
    for candidate in candidates:
        assert isinstance(candidate, dict)
        decisions.append(
            {
                "candidate_id": candidate["candidate_id"],
                "decision": decision,
                "rationale": "The packet evidence shows generated output that is not source-owned.",
                "evidence": ["generated marker", "local file-count estimate"],
                "confidence": "medium",
            }
        )
    return {
        "schema": EXCLUSION_REPORT_SCHEMA,
        "packet_sha256": packet_sha256(packet),
        "repo_root": str(repo_root.resolve()),
        "repo_fingerprint": packet["repo_fingerprint"],
        "reviewer": {"id": "test-supervising-agent", "kind": "agent"},
        "scope": "all-modules",
        "security_coverage_acknowledged": True,
        "decisions": decisions,
    }


def _module_report_for(
    packet: dict[str, object],
    repo_root: Path,
    *,
    module: str = "code_quality",
) -> dict[str, object]:
    candidates = packet["candidates"]
    assert isinstance(candidates, list)
    decisions: list[dict[str, object]] = []
    for candidate in candidates:
        assert isinstance(candidate, dict)
        is_target = candidate["path"] == "generated-output"
        decisions.append(
            {
                "candidate_id": candidate["candidate_id"],
                "decision": "exclude" if is_target else "include",
                "module_scope": module if is_target else "all-modules",
                "rationale": (
                    "Generated output is excluded from code-quality findings while security "
                    "coverage remains enabled."
                    if is_target
                    else "No exclusion is approved for this candidate."
                ),
                "evidence": ["generated marker", "module-specific security coverage policy"],
                "confidence": "high" if is_target else "medium",
            }
        )
    return {
        "schema": EXCLUSION_REPORT_SCHEMA,
        "packet_sha256": packet_sha256(packet),
        "repo_root": str(repo_root.resolve()),
        "repo_fingerprint": packet["repo_fingerprint"],
        "reviewer": {"id": "test-supervising-agent", "kind": "agent"},
        "scope": "module-scoped",
        "security_coverage_acknowledged": False,
        "decisions": decisions,
    }


def test_suggest_packet_contains_deterministic_candidate_evidence(tmp_path: Path) -> None:
    _make_candidate(tmp_path)
    config_path = _write_config(tmp_path)
    before_config = config_path.read_text(encoding="utf-8")

    result = run_exclusion_preflight_command(tmp_path, action="suggest", run_id="suggest-001")

    assert result["status"] == "suggested"
    packet = _read_packet(result)
    assert packet["schema"] == "quality-runner-scan-exclusion-packet-v0.1"
    assert packet["config"]["gate_timeouts"] == {"tests": 30}  # type: ignore[index]
    assert packet["config"]["timeout_signals"]["structural_max_text_files"] == 500  # type: ignore[index]
    candidates = packet["candidates"]
    assert isinstance(candidates, list)
    candidate = next(item for item in candidates if item["path"] == "generated-output")
    evidence = candidate["evidence"]
    assert evidence["tracked_file_count"] is None  # type: ignore[index]
    assert evidence["file_count"] == 3  # type: ignore[index]
    assert evidence["extensions"] == {".json": 3}  # type: ignore[index]
    assert evidence["generated_markers"]  # type: ignore[index]
    assert candidate["proposed_scope"]["pattern"] == "generated-output/**"  # type: ignore[index]
    assert config_path.read_text(encoding="utf-8") == before_config


def test_report_validation_recomputes_effective_exclusion_fingerprint(tmp_path: Path) -> None:
    _make_candidate(tmp_path)
    packet = build_exclusion_packet(tmp_path, "fingerprint-001")
    report = _report_for(packet, tmp_path)

    (tmp_path / ".gitignore").write_text("generated-output/\n", encoding="utf-8")

    validation = validate_exclusion_report(packet, report, repo_root=tmp_path)

    assert validation["passed"] is False
    assert any("fingerprint" in error for error in validation["errors"])  # type: ignore[union-attr]


def test_suggest_packet_includes_unowned_directory(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.py").write_text("print('tracked')\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
    unowned = tmp_path / "local-only"
    unowned.mkdir()
    (unowned / "notes.txt").write_text("local\n", encoding="utf-8")

    packet = build_exclusion_packet(tmp_path, "unowned-001")

    candidates = packet["candidates"]
    assert isinstance(candidates, list)
    candidate = next(item for item in candidates if item["path"] == "local-only")
    assert candidate["evidence"]["unowned"] is True  # type: ignore[index]
    assert candidate["suggested_decision"] == "defer"


def test_report_validation_rejects_protected_and_traversal_candidates(tmp_path: Path) -> None:
    _make_candidate(tmp_path, "src/generated-output")
    packet = build_exclusion_packet(tmp_path, "packet-001")
    candidates = packet["candidates"]
    assert isinstance(candidates, list)
    protected_candidate = next(
        item for item in candidates if item["path"] == "src/generated-output"
    )
    report = _report_for(packet, tmp_path)

    validation = validate_exclusion_report(packet, report, repo_root=tmp_path)

    assert validation["passed"] is False
    assert any("protected path" in error for error in validation["errors"])  # type: ignore[union-attr]
    assert protected_candidate["protected"] is True

    invalid_packet = json.loads(json.dumps(packet))
    invalid_packet["candidates"][0]["path"] = "../outside"  # type: ignore[index]
    assert any("traversal" in error for error in validate_exclusion_packet(invalid_packet))


def test_run_only_overlay_rejects_symlink_alias(tmp_path: Path) -> None:
    real_path = tmp_path / "real-output"
    real_path.mkdir()
    (real_path / "result.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "alias-output").symlink_to(real_path, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        normalize_run_only_exclusion_paths(tmp_path, ["alias-output"])


def test_apply_requires_explicit_flag_and_records_config_diff(tmp_path: Path) -> None:
    _make_candidate(tmp_path)
    config_path = _write_config(tmp_path)
    suggestion = run_exclusion_preflight_command(tmp_path, action="suggest", run_id="suggest-002")
    packet = _read_packet(suggestion)
    report_path = tmp_path / "review.json"
    report_path.write_text(
        json.dumps(_report_for(packet, tmp_path), indent=2) + "\n", encoding="utf-8"
    )
    packet_path = Path(str(suggestion["artifact_paths"]["scan_exclusion_preflight_packet_json"]))  # type: ignore[index]
    before = config_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="requires explicit --apply"):
        run_exclusion_preflight_command(
            tmp_path,
            action="apply",
            packet_path=packet_path,
            report_path=report_path,
        )
    assert config_path.read_text(encoding="utf-8") == before

    applied = run_exclusion_preflight_command(
        tmp_path,
        action="apply",
        run_id="apply-001",
        packet_path=packet_path,
        report_path=report_path,
        apply=True,
    )

    assert applied["status"] == "applied"
    assert "generated-output/**" in config_path.read_text(encoding="utf-8")
    assert applied["validation"]["passed"] is True  # type: ignore[index]
    config = applied["config"]
    assert config["changed"] is True  # type: ignore[index]
    assert config["diff"]  # type: ignore[index]
    manifest_path = Path(str(applied["artifact_paths"]["run_manifest_json"]))  # type: ignore[index]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "exclusion-preflight"
    assert manifest["scan_exclusion_preflight"]["stage"] == "apply"


def test_run_only_overlay_is_in_effective_scan_and_manifest(tmp_path: Path) -> None:
    _make_candidate(tmp_path)
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    config_path = tmp_path / ".quality-runner.toml"
    config_path.write_text(
        '[quality_runner]\nscan_exclusions = ["existing/**", "generated-output/**"]\n',
        encoding="utf-8",
    )
    before_config = config_path.read_text(encoding="utf-8")

    result = inspect_payload(
        tmp_path,
        run_id="overlay-001",
        agent_review_mode="off",
        scan_exclusion_overlay=["generated-output"],
    )

    artifact_paths = result["artifact_paths"]
    scan = json.loads(Path(artifact_paths["repo_scan_json"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(artifact_paths["run_manifest_json"]).read_text(encoding="utf-8"))
    assert "generated-output/**" in scan["scan_exclusions"]
    assert scan["scan_exclusion_preflight"]["scope"] == "all-modules"
    assert scan["scan_exclusion_preflight"]["configured_scan_exclusions"] == [
        "existing/**",
        "generated-output/**",
    ]
    assert "existing/**" in scan["scan_exclusion_preflight"]["effective_scan_exclusions"]
    assert "generated-output/**" in scan["scan_exclusion_preflight"]["effective_scan_exclusions"]
    assert Path(artifact_paths["scan_exclusion_overlay_json"]).exists()
    assert manifest["scan_exclusion_preflight"]["source"] == "cli-run-only-overlay"
    assert config_path.read_text(encoding="utf-8") == before_config


def test_module_scoped_report_validates_and_applies_without_security_exclusion(
    tmp_path: Path,
) -> None:
    _make_candidate(tmp_path)
    config_path = _write_config(tmp_path)
    suggestion = run_exclusion_preflight_command(tmp_path, action="suggest", run_id="module-001")
    packet = _read_packet(suggestion)
    report_path = tmp_path / "module-review.json"
    report_path.write_text(
        json.dumps(_module_report_for(packet, tmp_path), indent=2) + "\n",
        encoding="utf-8",
    )
    packet_path = Path(str(suggestion["artifact_paths"]["scan_exclusion_preflight_packet_json"]))  # type: ignore[index]

    validated = run_exclusion_preflight_command(
        tmp_path,
        action="validate",
        run_id="module-002",
        packet_path=packet_path,
        report_path=report_path,
    )

    assert validated["status"] == "validated"
    validation = validated["validation"]
    assert validation["passed"] is True  # type: ignore[index]
    assert validation["approved_patterns_by_module"] == {  # type: ignore[index]
        "code_quality": ["generated-output/**"]
    }

    applied = run_exclusion_preflight_command(
        tmp_path,
        action="apply",
        run_id="module-003",
        packet_path=packet_path,
        report_path=report_path,
        apply=True,
    )

    assert applied["status"] == "applied"
    config_text = config_path.read_text(encoding="utf-8")
    assert "[quality_runner.scan_exclusions_by_module]" in config_text
    assert 'code_quality = ["generated-output/**"]' in config_text
    assert 'scan_exclusions = ["generated-output/**"]' not in config_text
    assert applied["effective_scan_exclusions_by_module"]["security"]  # type: ignore[index]


def test_module_scoped_scan_exclusion_preserves_security_coverage(tmp_path: Path) -> None:
    output = tmp_path / "generated-output"
    output.mkdir()
    (output / "secrets.js").write_text(
        'const apiKey = "example-placeholder-not-a-real-secret";\n',
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text("print('source')\n", encoding="utf-8")
    config_path = tmp_path / ".quality-runner.toml"
    config_path.write_text(
        '[quality_runner.scan_exclusions_by_module]\ncode_quality = ["generated-output/**"]\n',
        encoding="utf-8",
    )

    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.config import load_repo_config
    from quality_runner.discovery import inspect_repo
    from quality_runner.security.scan import create_security_scan
    from quality_runner.standards import compile_standards

    config = load_repo_config(tmp_path)
    scan = inspect_repo(tmp_path, run_id="module-scan", config=config)
    standards = compile_standards(
        repo_root=tmp_path,
        scan=scan,
        profile="default",
        config=config,
    )
    code_quality = create_code_quality_scan(tmp_path, scan=scan, config=config)
    security = create_security_scan(
        tmp_path,
        scan=scan,
        config=config,
        standards_packet=standards,
    )

    assert "generated-output/**" in scan["scan_exclusions_by_module"]["code_quality"]  # type: ignore[index]
    assert "generated-output/**" not in scan["scan_exclusions_by_module"]["security"]  # type: ignore[index]
    assert all(
        item["path"] != "generated-output/secrets.js" for item in code_quality["accountability"]
    )
    assert any(item["file"] == "generated-output/secrets.js" for item in security["candidates"])


def test_run_only_module_overlay_is_reported_and_does_not_mutate_config(tmp_path: Path) -> None:
    output = tmp_path / "generated-output"
    output.mkdir()
    (output / "secrets.js").write_text(
        'const apiKey = "example-placeholder-not-a-real-secret";\n',
        encoding="utf-8",
    )
    config_path = _write_config(tmp_path)
    before_config = config_path.read_text(encoding="utf-8")

    result = inspect_payload(
        tmp_path,
        run_id="module-overlay-001",
        agent_review_mode="off",
        scan_exclusion_overlay={"code_quality": ["generated-output"]},
    )
    scan = json.loads(Path(result["artifact_paths"]["repo_scan_json"]).read_text(encoding="utf-8"))
    code_quality = json.loads(
        Path(result["artifact_paths"]["code_quality_scan_json"]).read_text(encoding="utf-8")
    )
    security = json.loads(
        Path(result["artifact_paths"]["security_scan_json"]).read_text(encoding="utf-8")
    )

    overlay = scan["scan_exclusion_preflight"]
    assert overlay["scope"] == "module-scoped"
    assert overlay["security_coverage"].startswith("Structural")
    assert overlay["effective_exclusion_patterns_by_module"] == {
        "code_quality": ["generated-output/**"]
    }
    assert all(
        item["path"] != "generated-output/secrets.js" for item in code_quality["accountability"]
    )
    assert any(item["file"] == "generated-output/secrets.js" for item in security["candidates"])
    assert config_path.read_text(encoding="utf-8") == before_config


def test_cli_exclusion_stages_and_run_overlay_are_wired() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "exclusions",
            "apply",
            ".",
            "--packet",
            "packet.json",
            "--report",
            "report.json",
            "--apply",
            "--json",
        ]
    )
    assert args.command == "exclusions"
    assert args.exclusions_action == "apply"
    assert args.apply is True

    run_args = parser.parse_args(["run", ".", "--scan-exclusion", "generated-output"])
    assert run_args.scan_exclusion == ["generated-output"]
    module_args = parser.parse_args(
        ["run", ".", "--scan-exclusion-module", "code_quality=generated-output"]
    )
    assert module_args.scan_exclusion_module == ["code_quality=generated-output"]
