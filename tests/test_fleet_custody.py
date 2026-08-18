from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quality_runner.cli import build_parser
from quality_runner.fleet.custody import custody_validation_payload
from quality_runner.fleet.workspace_policy import fleet_workspace_target_payload

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Quality Runner Test")
    _git(repo, "config", "user.email", "quality-runner@example.invalid")
    (repo / "README.md").write_text("custody\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "initial")
    return repo


def _receipt_root(repo: Path) -> Path:
    return (
        Path(_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        / "isolated-change-workflow"
        / "tasks"
    )


def test_custody_validation_is_read_only_and_reports_unleased_worktree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    lane = tmp_path / "unleased"
    _git(repo, "worktree", "add", "-b", "codex/unleased", str(lane), "HEAD")

    before = _git(repo, "status", "--porcelain=v2")
    payload = custody_validation_payload(repo, as_of="2026-08-16T20:00:00Z")
    after = _git(repo, "status", "--porcelain=v2")

    assert payload["schema_version"] == "quality-runner-custody-validation/v1"
    assert payload["read_only"] is True
    assert payload["implementation_allowed"] is False
    assert before == after
    assert str(lane.resolve()) in payload["unleased_worktrees"]
    assert payload["status"] == "attention_required"


def test_custody_policy_separates_canonical_workspace_from_temporary_lane(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    policy_dir = repo / ".agents"
    policy_dir.mkdir()
    (policy_dir / "workspace-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "workspace-policy/v1",
                "repository_id": "fixture-supporting",
                "repository_role": "supporting_project",
                "canonical_workspaces": [
                    {
                        "id": "working",
                        "role": "working",
                        "ref": _git(repo, "branch", "--show-current"),
                        "protected": True,
                    }
                ],
                "retention_exceptions": [],
            }
        ),
        encoding="utf-8",
    )
    lane = tmp_path / "temporary"
    _git(repo, "worktree", "add", "-b", "codex/temporary", str(lane), "HEAD")

    payload = custody_validation_payload(repo, as_of="2026-08-16T20:00:00Z")

    policy = payload["workspace_policy"]
    assert policy["repository_role"] == "supporting_project"
    assert policy["baseline_target"] == 1
    assert policy["canonical_observed"] == 1
    assert policy["temporary_observed"] == 1
    assert policy["lease_required_for"] == "temporary"
    assert str(lane.resolve()) in payload["unleased_worktrees"]


def test_invalid_workspace_policy_is_explicit_and_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    policy_dir = repo / ".agents"
    policy_dir.mkdir()
    (policy_dir / "workspace-policy.json").write_text(
        json.dumps({"schema_version": "workspace-policy/unsupported"}),
        encoding="utf-8",
    )

    payload = custody_validation_payload(repo, as_of="2026-08-16T20:00:00Z")

    assert payload["status"] == "attention_required"
    assert payload["workspace_policy"]["status"] == "invalid"
    assert payload["workspace_policy"]["disposition"] == "policy_invalid"
    assert payload["workspace_policy"]["canonical_protection"] == "unresolved"
    assert payload["implementation_allowed"] is False
    assert payload["workspace_policy"]["drift"][0].startswith("policy-invalid:")


def test_clean_expired_signed_shape_is_adoptable_but_identity_is_unverified(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "codex/adoptable", str(lane), "HEAD")
    head = _git(lane, "rev-parse", "HEAD")
    _receipt_root(repo).mkdir(parents=True)
    (_receipt_root(repo) / "adoptable.json").write_text(
        json.dumps(
            {
                "schema_version": "isolated-change-task/v2",
                "task_id": "adoptable",
                "worktree": str(lane),
                "branch": "codex/adoptable",
                "head_sha": head,
                "base_sha": head,
                "state": "active",
                "last_activity_at": "2000-01-01T00:00:00Z",
                "lease_expires_at": "2000-01-01T00:00:00Z",
                "integrity": {"algorithm": "hmac-sha256", "digest": "0" * 64},
            }
        ),
        encoding="utf-8",
    )

    payload = custody_validation_payload(repo, as_of="2026-08-16T20:00:00Z")
    lane_payload = payload["lanes"][0]

    assert lane_payload["state"] == "adoptable"
    assert lane_payload["disposition"] == "adoption_ready"
    assert "receipt_integrity_unverified" in lane_payload["dispositions"]
    assert "adoption_ready" in lane_payload["dispositions"]
    assert payload["integrity"]["hmac_identity"] == "not_verified_by_quality_runner"


def test_malformed_and_legacy_receipts_have_granular_dispositions(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    root = _receipt_root(repo)
    root.mkdir(parents=True)
    (root / "malformed.json").write_text("not-json\n", encoding="utf-8")
    (root / "legacy.json").write_text(
        json.dumps(
            {
                "schema_version": "isolated-change-task/v1",
                "task_id": "legacy",
                "state": "active",
            }
        ),
        encoding="utf-8",
    )
    (root / "invalid-integrity.json").write_text(
        json.dumps(
            {
                "schema_version": "isolated-change-task/v2",
                "task_id": "invalid-integrity",
                "state": "active",
            }
        ),
        encoding="utf-8",
    )

    payload = custody_validation_payload(repo, as_of="2026-08-16T20:00:00Z")
    by_task = {item["task_id"]: item for item in payload["lanes"]}

    assert by_task["malformed"]["state"] == "unknown"
    assert by_task["malformed"]["disposition"] == "receipt_malformed"
    assert by_task["legacy"]["state"] == "unknown"
    assert by_task["legacy"]["disposition"] == "legacy_unsigned_receipt"
    assert by_task["invalid-integrity"]["state"] == "unknown"
    assert by_task["invalid-integrity"]["disposition"] == "receipt_integrity_invalid"
    assert "integrity" in by_task["invalid-integrity"]["next_action"]
    assert not any(item["state"] == "adoptable" for item in payload["lanes"])
    assert payload["disposition_counts"]["receipt_malformed"] == 1
    assert payload["disposition_counts"]["legacy_unsigned_receipt"] == 1
    assert payload["disposition_counts"]["receipt_integrity_invalid"] == 1


def test_custody_cli_parser_exposes_read_only_validation() -> None:
    args = build_parser().parse_args(
        ["fleet", "custody", "validate", "/tmp/example-repository", "--json"]
    )

    assert args.fleet_action == "custody"
    assert args.custody_action == "validate"
    assert args.repository == "/tmp/example-repository"


def test_workspace_target_calculates_baseline_and_active_lane_total(tmp_path: Path) -> None:
    manifest = tmp_path / "workspace-fleet.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "workspace-fleet-manifest/v1",
                "repositories": [
                    {
                        "policy": {
                            "schema_version": "workspace-policy/v1",
                            "repository_id": "production-a",
                            "repository_role": "production_product",
                            "canonical_workspaces": [
                                {
                                    "id": "release",
                                    "role": "release",
                                    "ref": "main",
                                    "protected": True,
                                },
                                {
                                    "id": "integration",
                                    "role": "integration",
                                    "ref": "dev",
                                    "protected": True,
                                },
                            ],
                            "retention_exceptions": [],
                        },
                        "active_temporary_lanes": 7,
                    },
                    {
                        "policy": {
                            "schema_version": "workspace-policy/v1",
                            "repository_id": "supporting-a",
                            "repository_role": "supporting_project",
                            "canonical_workspaces": [
                                {
                                    "id": "working",
                                    "role": "working",
                                    "ref": "main",
                                    "protected": True,
                                }
                            ],
                            "retention_exceptions": [
                                {
                                    "lane_id": "wip-1",
                                    "reason": "awaiting product owner",
                                    "retained_by": "reconciliation-1",
                                    "review_by": "2026-09-01T00:00:00Z",
                                }
                            ],
                        },
                        "active_temporary_lanes": 2,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = fleet_workspace_target_payload(manifest, as_of="2026-08-16T20:00:00Z")

    assert payload["production_count"] == 1
    assert payload["supporting_count"] == 1
    assert payload["baseline_target"] == 3
    assert payload["active_temporary_lanes"] == 9
    assert payload["retained_lane_count"] == 1
    assert payload["managed_target_total"] == 13
    assert payload["status"] == "observed"


def test_workspace_target_cli_parser_is_read_only() -> None:
    args = build_parser().parse_args(
        ["fleet", "workspace-target", "calculate", "--manifest", "/tmp/fleet.json", "--json"]
    )

    assert args.fleet_action == "workspace-target"
    assert args.workspace_target_action == "calculate"
    assert args.manifest == "/tmp/fleet.json"


def test_public_custody_fixture_preserves_state_disposition_separation() -> None:
    fixture = json.loads(
        (ROOT / "fixtures/contracts/public-adapters/pronto-custody-validation.json").read_text(
            encoding="utf-8"
        )
    )

    assert fixture["schema_version"] == "quality-runner-custody-validation/v1"
    assert fixture["read_only"] is True
    assert fixture["implementation_allowed"] is False
    assert all("state" in lane and "disposition" in lane for lane in fixture["lanes"])
    assert fixture["lanes"][0]["state"] == "unknown"
    assert fixture["lanes"][0]["disposition"] == "legacy_unsigned_receipt"
    assert fixture["lanes"][1]["state"] == "adoptable"
    assert fixture["lanes"][1]["disposition"] == "adoption_ready"
