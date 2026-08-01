from __future__ import annotations

from pathlib import Path

from quality_runner.application.verification_v1_artifacts import (
    write_security_review_slice_specs,
)
from quality_runner.discovery import inspect_repo
from quality_runner.refresh_timeout import resolve_refresh_timeout_contract
from quality_runner.refresh_workflow import run_refresh_payload
from quality_runner.scan_scope import create_text_scan_scope


def test_read_only_refresh_skips_verify_without_execution_consent(tmp_path: Path) -> None:
    calls: list[str] = []

    def inspect(**_: object) -> dict[str, object]:
        calls.append("inspect")
        return {"status": "inspected"}

    def run(**_: object) -> dict[str, object]:
        calls.append("run")
        return {"status": "planned"}

    def verify(**_: object) -> dict[str, object]:
        calls.append("verify")
        raise AssertionError("verification must not run without consent")

    payload = run_refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="consent-control",
        baseline_run_id=None,
        profile=None,
        ci_status_json=None,
        timeout_seconds=5,
        workflow_timeout_seconds=None,
        verify_timeout_seconds=None,
        workflow_timeout_reason=None,
        total_timeout_seconds=None,
        total_timeout_reason=None,
        checkout_most_advanced_branch=False,
        execute_discovered_gates=False,
        allow_mutating_gates=False,
        intent=None,
        inspect_callback=inspect,
        run_callback=run,
        verify_callback=verify,
        summary_callback=lambda **_: {"status": "blocked"},
    )

    assert calls == ["inspect", "run"]
    assert payload["runs"]["verify"]["skip_type"] == "execution-consent-required"  # type: ignore[index]


def test_refresh_preserves_explicit_scan_inclusions_across_phases(tmp_path: Path) -> None:
    captured: dict[str, dict[str, object]] = {}

    def inspect(**kwargs: object) -> dict[str, object]:
        captured["inspect"] = kwargs
        return {"status": "inspected"}

    def run(**kwargs: object) -> dict[str, object]:
        captured["run"] = kwargs
        return {"status": "planned"}

    payload = run_refresh_payload(
        repo_root=tmp_path,
        run_id_prefix="scope-propagation",
        baseline_run_id=None,
        profile=None,
        ci_status_json=None,
        timeout_seconds=5,
        workflow_timeout_seconds=None,
        verify_timeout_seconds=None,
        workflow_timeout_reason=None,
        total_timeout_seconds=None,
        total_timeout_reason=None,
        checkout_most_advanced_branch=False,
        execute_discovered_gates=False,
        allow_mutating_gates=False,
        intent=None,
        inspect_callback=inspect,
        run_callback=run,
        verify_callback=lambda **_: {"status": "blocked"},
        summary_callback=lambda **_: {"status": "blocked"},
        include_paths=("docs",),
        include_ignored_paths=("data",),
    )

    assert payload["status"] == "blocked"
    assert captured["inspect"]["include_paths"] == ("docs",)
    assert captured["inspect"]["include_ignored_paths"] == ("data",)
    assert captured["run"]["include_paths"] == ("docs",)
    assert captured["run"]["include_ignored_paths"] == ("data",)


def test_inventory_cache_reuses_clean_repository_inventory(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts": {"test": "true"}}\n', encoding="utf-8")

    first = inspect_repo(tmp_path, "inventory-one")
    second = inspect_repo(tmp_path, "inventory-two")

    assert first["inventory_cache"]["status"] == "miss"  # type: ignore[index]
    assert second["inventory_cache"]["status"] == "hit"  # type: ignore[index]
    assert second["run_id"] == "inventory-two"
    assert second["git_provenance"]["workflow_run_id"] == "inventory-two"  # type: ignore[index]


def test_gate_execution_inventory_cache_is_explicitly_disabled(tmp_path: Path) -> None:
    payload = inspect_repo(tmp_path, "inventory-disabled", cache_mode="disabled")

    assert payload["inventory_cache"]["status"] == "disabled"  # type: ignore[index]
    assert payload["inventory_cache"]["disabled_reason"] == "diagnostic-cache-disabled"  # type: ignore[index]
    assert not (tmp_path / ".quality-runner").exists()


def test_focus_scope_only_reads_changed_surface(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "changed.ts").write_text("export const changed = 1;\n", encoding="utf-8")
    (tmp_path / "src" / "untouched.ts").write_text(
        "export const untouched = 1;\n", encoding="utf-8"
    )
    scope = create_text_scan_scope(
        tmp_path,
        scan={"generated_code": []},
        config={},
        focus_paths=("src/changed.ts",),
    )

    assert [item.path for item in scope.files] == ["src/changed.ts"]
    assert scope.focus_paths == ("src/changed.ts",)


def test_phase_timeout_contract_has_independent_budgets() -> None:
    contract = resolve_refresh_timeout_contract(
        per_gate_timeout_seconds=30,
        workflow_timeout_seconds=90,
        verify_timeout_seconds=None,
        workflow_timeout_reason=None,
        total_timeout_seconds=300,
        total_timeout_reason=None,
        inspect_timeout_seconds=45,
        run_timeout_seconds=60,
    )

    assert contract["inspect_timeout_seconds"] == 45
    assert contract["run_timeout_seconds"] == 60
    assert contract["verify_timeout_seconds"] == 90


def test_security_review_slices_preserve_bounded_source_references(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    paths = write_security_review_slice_specs(
        run_dir,
        {
            "obligations": [
                {
                    "id": "security_api_route_auth_review",
                    "finding_id": "security-review-security-api-route-auth-review",
                    "status": "review-required",
                    "review_instructions": ["Check authentication before the handler."],
                    "completion_criteria": ["Record the review outcome."],
                    "candidate_refs": [
                        {"file": "app/api/example.ts", "line": 27, "category": "missing-auth"}
                    ],
                }
            ]
        },
        run_id="slice-run",
    )

    content = Path(paths["security-review-security_api_route_auth_review"]).read_text(
        encoding="utf-8"
    )
    assert "app/api/example.ts:27" in content
    assert "missing-auth" in content
