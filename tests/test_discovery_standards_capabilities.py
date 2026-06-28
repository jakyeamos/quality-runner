from __future__ import annotations

import json
from pathlib import Path

from test_support.quality_runner_fixtures import write_js_fixture


def test_inspect_repo_detects_js_quality_surfaces(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    write_js_fixture(tmp_path)

    scan = inspect_repo(tmp_path, run_id="scan-001")

    assert scan["schema"] == "quality-runner-repo-scan-v0.1"
    assert scan["package_manager"] == "pnpm"
    assert scan["languages"] == ["javascript"]
    assert scan["scripts"]["lint"] == "eslint ."
    assert scan["pre_cr_config"] == ".pre-cr.json"
    assert scan["truth_file"] == ".tracker/PROJECT_TRUTH.md"


def test_inspect_repo_does_not_infer_package_manager_from_policy_text(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Always use pnpm.\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="policy-only-001")

    assert scan["package_manager"] is None


def test_compile_standards_does_not_warn_for_unknown_package_manager(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="unknown-package-manager-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    assert scan["package_manager"] is None
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "package_manager_mismatch" not in requirement_ids


def test_inspect_repo_does_not_mark_tests_required_from_latest(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "AGENTS.md").write_text("Use the latest stable toolchain.\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="latest-001")

    assert scan["quality_contract"]["required_terms"]["tests"] is False


def test_inspect_repo_warns_on_invalid_package_json(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="invalid-package-001")

    assert scan["scripts"] == {}
    assert scan["warnings"] == [
        {
            "code": "invalid_package_json",
            "message": "package.json could not be parsed as JSON",
            "path": "package.json",
        }
    ]


def test_package_json_warnings_propagate_to_standards_and_capabilities(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="invalid-package-002")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    expected_warning = {
        "code": "invalid_package_json",
        "message": "package.json could not be parsed as JSON",
        "path": "package.json",
    }
    assert expected_warning in packet["warnings"]
    assert expected_warning in capability_map["warnings"]


def test_inspect_repo_expands_home_before_validating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from quality_runner.discovery import inspect_repo

    home = tmp_path / "home"
    repo = home / "repo"
    repo.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    scan = inspect_repo(Path("~/repo"), run_id="home-001")

    assert scan["repo_root"] == str(repo.resolve())


def test_inspect_repo_rejects_missing_repo_root(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    missing_root = tmp_path / "missing"

    try:
        inspect_repo(missing_root, run_id="missing-001")
    except FileNotFoundError as error:
        assert str(error) == f"repo root does not exist: {missing_root}"
    else:
        raise AssertionError("inspect_repo accepted a missing repo root")


def test_inspect_repo_rejects_file_repo_root(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    file_root = tmp_path / "not-a-directory"
    file_root.write_text("content", encoding="utf-8")

    try:
        inspect_repo(file_root, run_id="file-001")
    except NotADirectoryError as error:
        assert str(error) == f"repo root is not a directory: {file_root}"
    else:
        raise AssertionError("inspect_repo accepted a file repo root")


def test_compile_standards_preserves_profile_and_local_provenance(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    write_js_fixture(tmp_path)
    scan = inspect_repo(tmp_path, run_id="scan-001")

    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    assert packet["schema"] == "quality-runner-standards-packet-v0.1"
    assert packet["profile"] == "jakyeamos"
    sources = {source["path"] for source in packet["sources"]}
    assert "AGENTS.md" in sources
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "use_pnpm" in requirement_ids
    assert "truth_file_current" in requirement_ids


def test_compile_standards_rejects_unsupported_profiles(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="scan-001")

    try:
        compile_standards(repo_root=tmp_path, scan=scan, profile="someone-else")
    except ValueError as error:
        assert str(error) == "unsupported standards profile: someone-else"
    else:
        raise AssertionError("compile_standards accepted an unsupported profile")


def test_compile_standards_handles_malformed_package_manager() -> None:
    from quality_runner.standards import compile_standards

    packet = compile_standards(
        repo_root=Path("/tmp"),
        scan={"package_manager": []},
        profile="jakyeamos",
    )

    assert {
        "code": "invalid_package_manager",
        "message": "scan package_manager must be a string or null",
        "path": "package_manager",
    } in packet["warnings"]
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "package_manager_mismatch" in requirement_ids


def test_detect_capabilities_includes_standards_warnings() -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.standards import compile_standards

    scan = {"package_manager": []}
    packet = compile_standards(repo_root=Path("/tmp"), scan=scan, profile="jakyeamos")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert {
        "code": "invalid_package_manager",
        "message": "scan package_manager must be a string or null",
        "path": "package_manager",
    } in capability_map["warnings"]


def test_detect_capabilities_records_missing_expected_surfaces(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="empty-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["schema"] == "quality-runner-capability-map-v0.1"
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "lint" in missing_ids
    assert "tests" in missing_ids
    assert "truth_file" in missing_ids


def test_detect_capabilities_records_pre_cr_script_with_stable_id(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"pre-cr": "pre-cr"}}),
        encoding="utf-8",
    )
    scan = inspect_repo(tmp_path, run_id="pre-cr-script-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    available_ids = {item["id"] for item in capability_map["available"]}
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "pre_cr" in available_ids
    assert "pre_cr" not in missing_ids
    assert "pre_pr" in missing_ids


def test_detect_capabilities_records_pre_cr_config_with_stable_id(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / ".pre-cr.json").write_text("{}", encoding="utf-8")
    scan = inspect_repo(tmp_path, run_id="pre-cr-config-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    available_ids = {item["id"] for item in capability_map["available"]}
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "pre_cr" in available_ids
    assert "pre_cr" not in missing_ids


def test_detect_capabilities_treats_malformed_scripts_as_missing() -> None:
    from quality_runner.capabilities import detect_capabilities

    capability_map = detect_capabilities(
        scan={"schema": "quality-runner-repo-scan-v0.1", "scripts": "not-a-dict"},
        standards_packet={"profile": "jakyeamos"},
    )

    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "lint" in missing_ids
    assert "tests" in missing_ids
