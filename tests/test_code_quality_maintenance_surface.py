from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.branch_diff import resolve_branch_diff
from quality_runner.code_quality import create_code_quality_scan
from quality_runner.config import load_repo_config


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _initialize(repo: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "quality-runner@example.test")
    _git(repo, "config", "user.name", "Quality Runner Tests")
    (repo / "src").mkdir()
    (repo / "src" / "status.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    (repo / "package.json").write_text(
        json.dumps({"name": "fixture", "dependencies": {}}) + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")


def _scan(
    repo: Path,
    *,
    scope_metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
    return create_code_quality_scan(
        repo,
        scan={"run_id": "maintenance-scan"},
        config=load_repo_config(repo),
        cache_mode="disabled",
        scope_metadata=scope_metadata,
    )


def test_worktree_maintenance_candidates_are_native_qr_findings(tmp_path: Path) -> None:
    _initialize(tmp_path)
    (tmp_path / "src" / "status.py").write_text(
        "FEATURE_FLAG = True\n\ndef public_status():\n    return 'legacy compatibility'\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "fixture", "dependencies": {"httpx": "1.0.0"}}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "generated.json").write_text(
        '{"legacy_config": "compatibility"}\n',
        encoding="utf-8",
    )

    result = _scan(tmp_path)

    maintenance_findings = [
        finding for finding in result["findings"] if finding["category"] == "maintenance-surface"
    ]
    rules = {finding["rule_id"] for finding in maintenance_findings}
    assert {
        "maintenance-new-dependency",
        "maintenance-public-surface",
        "maintenance-config-surface",
        "maintenance-compatibility-surface",
    } <= rules
    assert all(finding["id"].startswith("CQ-") for finding in maintenance_findings)
    assert all(finding["fingerprint"] for finding in maintenance_findings)
    assert not any(finding["file"].startswith("artifacts/") for finding in maintenance_findings)
    assert result["summary"]["findings_by_category"]["maintenance-surface"] == len(
        maintenance_findings
    )
    assert result["maintenance_surface"]["finding_count"] == len(maintenance_findings)
    assert result["maintenance_surface"]["status"] == "review_required"
    assert result["maintenance_surface"]["source_status"] == "ready"
    assert result["maintenance_surface"]["provenance"]["requested_head"] == "WORKTREE"
    assert result["maintenance_surface"]["projected_counts"] == {
        "maintenance-compatibility-surface": 1,
        "maintenance-config-surface": 1,
        "maintenance-new-dependency": 1,
        "maintenance-public-surface": 1,
    }


def test_branch_diff_scan_projects_committed_maintenance_findings(tmp_path: Path) -> None:
    _initialize(tmp_path)
    _git(tmp_path, "switch", "-c", "feature")
    (tmp_path / "src" / "public_api.py").write_text(
        "def public_status():\n    return 'ready'\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "add public surface")
    scope = resolve_branch_diff(tmp_path, base_ref="main", head_ref="feature")

    result = _scan(tmp_path, scope_metadata=scope.to_payload())

    assert any(
        finding["rule_id"] == "maintenance-public-surface"
        and finding["file"] == "src/public_api.py"
        for finding in result["findings"]
    )
    provenance = result["maintenance_surface"]["provenance"]
    assert provenance["requested_base"] == "main"
    assert provenance["requested_head"] == "WORKTREE"
    assert provenance["comparison_base_commit"] == scope.comparison_base_commit


def test_non_git_scan_keeps_maintenance_surface_unavailable_without_failing(
    tmp_path: Path,
) -> None:
    (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    result = _scan(tmp_path)

    assert result["maintenance_surface"]["status"] == "unavailable"
    assert result["maintenance_surface"]["finding_count"] == 0
    assert not any(finding["category"] == "maintenance-surface" for finding in result["findings"])


def test_explicitly_disabled_maintenance_group_emits_no_findings(tmp_path: Path) -> None:
    _initialize(tmp_path)
    (tmp_path / "src" / "public_api.py").write_text(
        "def public_status():\n    return 'ready'\n",
        encoding="utf-8",
    )
    config = load_repo_config(tmp_path)
    config["structural_scan"] = {"disabled_rule_groups": ["maintenance-surface"]}

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "maintenance-disabled"},
        config=config,
        cache_mode="disabled",
    )

    assert result["maintenance_surface"] == {
        "schema": "quality-runner-maintenance-surface-v0.1",
        "status": "disabled",
        "finding_count": 0,
    }
    assert not any(finding["category"] == "maintenance-surface" for finding in result["findings"])
