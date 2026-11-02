from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _repo(root: Path, *, limit: int = 100) -> Path:
    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "Fixture")
    (root / ".gitignore").write_text(".quality-runner*\n")
    for name in ("app.py", "other.py", "third.py"):
        (root / name).write_text("value = 1\n")
    _git(root, "add", ".gitignore", "app.py", "other.py", "third.py")
    _git(root, "commit", "--quiet", "-m", "original source")
    (root / ".quality-runner.toml").write_text(
        f"""[quality_runner.structural_scan]
max_text_files = {limit}
large_file_lines = 5
similarity_enabled = false
[quality_runner.prevention]
required_modules = ["code_quality", "security"]
[[quality_runner.prevention.rules]]
detector = "code_quality"
rule_id = "large-source-file"
state = "behavior-verified"
owner = "fixture"
rationale = "Keep the regression's source size bounded."
paths = ["*.py"]
confidence_threshold = 0.3
evidence_refs = ["positive:large.py", "negative:small.py", "ambiguous:generated.py"]
"""
    )
    return root


def _qr(repo: Path, action: str, *args: str) -> tuple[int, dict]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "task",
            action,
            str(repo),
            "--task-id",
            "recovery",
            "--json",
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "QUALITY_RUNNER_DOGFOOD_STATE_DIR": str(repo / ".quality-runner/dogfood"),
        },
    )
    assert result.stdout, result.stderr
    return result.returncode, json.loads(result.stdout)


def _baseline(repo: Path, run_id: str) -> Path:
    return repo / ".quality-runner/runs" / run_id / "task-baseline.json"


def test_ignored_policy_controls_baseline_and_check_coverage(tmp_path: Path) -> None:
    repo = _repo(tmp_path, limit=2)
    code, started = _qr(repo, "start")
    assert code == 0
    assert started["coverage"]["code_quality"] == "partial"
    code, checked = _qr(repo, "release-check")
    assert code == 3
    assert checked["normalized_findings"]["coverage"]["code_quality"] == "partial"
    assert checked["release_readiness"]["eligible"] is False

    policy = repo / ".quality-runner.toml"
    policy.write_text(policy.read_text().replace("max_text_files = 2", "max_text_files = 100"))
    code, renewed = _qr(repo, "rebaseline", "--preserve-source", "--reason", "complete coverage")
    assert code == 0
    assert set(renewed["coverage"].values()) == {"complete"}
    code, checked = _qr(repo, "release-check")
    assert code == 0
    assert checked["release_readiness"]["eligible"] is True


def test_source_preserving_rebaseline_keeps_original_delta(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _, started = _qr(repo, "start")
    original = _baseline(repo, started["baseline_run_id"])
    original_bytes = original.read_bytes()
    original_data = json.loads(original_bytes)
    (repo / "app.py").write_text("\n".join(f"value_{i} = {i}" for i in range(8)) + "\n")
    policy = repo / ".quality-runner.toml"
    policy.write_text(policy.read_text() + "\n# reviewed policy update\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "--quiet", "-m", "current implementation")
    code, blocked = _qr(repo, "release-check")
    assert code == 3
    assert any(b["code"] == "rebaseline_required" for b in blocked["blockers"])

    code, renewed = _qr(repo, "rebaseline", "--preserve-source", "--reason", "reviewed policy")
    assert code == 0
    new_data = json.loads(_baseline(repo, renewed["baseline_run_id"]).read_text())
    assert new_data["snapshot"] == original_data["snapshot"]
    assert new_data["source"] == original_data["source"]
    assert original.read_bytes() == original_bytes
    assert new_data["supersedes"] == started["baseline_run_id"]
    assert new_data["analysis_policy_overlay"] is True
    assert (
        new_data["evidence"]["configuration_hash"]
        == hashlib.sha256(policy.read_bytes()).hexdigest()
    )
    code, checked = _qr(repo, "release-check")
    assert code == 1
    assert checked["delta"]["counts"]["new_enforced"] == 1
    assert checked["release_readiness"]["eligible"] is False


@pytest.mark.parametrize("dirty_kind", ["edit", "untracked", "deleted", "executable"])
def test_source_preserving_rebaseline_refuses_unrecoverable_source(
    tmp_path: Path, dirty_kind: str
) -> None:
    repo = _repo(tmp_path)
    if dirty_kind == "edit":
        (repo / "app.py").write_text("uncommitted = True\n")
    elif dirty_kind == "untracked":
        (repo / "untracked.py").write_text("untracked = True\n")
    elif dirty_kind == "deleted":
        (repo / "app.py").unlink()
    else:
        (repo / "app.py").chmod(0o755)
    _, started = _qr(repo, "start")
    record = repo / ".quality-runner/tasks/recovery.json"
    before = record.read_bytes()
    old_baseline = _baseline(repo, started["baseline_run_id"]).read_bytes()
    code, rejected = _qr(repo, "rebaseline", "--preserve-source", "--reason", "reviewed policy")
    assert code == 3
    assert "original source" in rejected["error"]["message"]
    assert record.read_bytes() == before
    assert _baseline(repo, started["baseline_run_id"]).read_bytes() == old_baseline


def test_ignored_policy_symlink_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    policy = repo / ".quality-runner.toml"
    target = repo / "policy.toml"
    policy.rename(target)
    policy.symlink_to("policy.toml")
    code, result = _qr(repo, "start")
    assert code == 3
    assert "regular file" in result["error"]["message"]


def test_release_receipt_cannot_cross_rebaseline_lineage(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    large = "\n".join(f"value_{i} = {i}" for i in range(8)) + "\n"
    (repo / "app.py").write_text(large)
    assert _qr(repo, "start")[0] == 0
    code, old_check = _qr(repo, "release-check")
    assert code == 0
    assert old_check["release_readiness"]["eligible"] is True
    (repo / "app.py").write_text("value = 1\n")
    assert _qr(repo, "rebaseline", "--reason", "explicit new workspace baseline")[0] == 0
    (repo / "app.py").write_text(large)

    code, checked = _qr(repo, "release-check")
    assert code == 1
    assert checked["delta"]["counts"]["new_enforced"] == 1
    assert checked["release_readiness"]["eligible"] is False


def test_legacy_analysis_contract_cannot_reuse_a_passing_receipt(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _, started = _qr(repo, "start")
    assert _qr(repo, "release-check")[0] == 0
    baseline_file = _baseline(repo, started["baseline_run_id"])
    legacy = json.loads(baseline_file.read_text())
    del legacy["evidence"]["task_analysis_contract"]
    baseline_file.write_text(json.dumps(legacy))

    code, checked = _qr(repo, "release-check")
    assert code == 3
    assert checked["release_readiness"]["eligible"] is False
    assert any("task analysis contract" in b["message"] for b in checked["blockers"])
