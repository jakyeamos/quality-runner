from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_verify_gates_read_only_mode_restores_tracked_mutations(tmp_path: Path) -> None:
    from quality_runner.workflow import verify_gates_payload

    tracked_file = tmp_path / "tracked.txt"
    tracked_file.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=quality-runner@example.com",
            "-c",
            "user.name=Quality Runner",
            "commit",
            "-m",
            "Initial commit",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    command = (
        f"{sys.executable} -c "
        "\"from pathlib import Path; Path('tracked.txt').write_text('mutated\\\\n')\""
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["tests"]',
                "",
                "[[quality_runner.gates]]",
                'id = "tests"',
                f"command = {json.dumps(command)}",
                'ecosystem = "python"',
                'source = "local policy"',
                'owner = "qa"',
                "required = true",
                'severity = "blocker"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = verify_gates_payload(
        repo_root=tmp_path,
        run_id="read-only-tracked-mutation",
        read_only_gates=True,
    )
    verification = json.loads(Path(payload["artifact_paths"]["gate_verification_json"]).read_text())
    handoff = json.loads(Path(payload["artifact_paths"]["agent_handoff_json"]).read_text())
    handoff_markdown = Path(payload["artifact_paths"]["agent_handoff_md"]).read_text()

    assert tracked_file.read_text(encoding="utf-8") == "original\n"
    assert payload["status"] == "blocked"
    gate = verification["gates"][0]
    assert gate["status"] == "failed"
    assert gate["failure_type"] == "read-only-mutation"
    assert gate["exit_code"] == 0
    mutation_diagnostics = gate["diagnostics"]["read_only_mutation"]
    assert {
        key: value for key, value in mutation_diagnostics.items() if key != "scan_exclusions"
    } == {
        "restored": True,
        "tracked_files": ["tracked.txt"],
        "untracked_or_ignored_files": [],
        "manifest_complete": True,
        "allowed_paths": [".quality-runner", ".quality-runner/runs/", ".quality-runner/worktrees/"],
    }
    assert mutation_diagnostics["scan_exclusions"]
    assert "mutated tracked files" in gate["recommended_action"]
    assert handoff["status"] == "gates-blocked"
    assert handoff["gate_verification"]["recommended_classification"] == "read-only-gate-blocker"
    assert handoff["gate_verification"]["primary_blocker_class"] == "read-only-policy"
    assert handoff["gate_verification"]["blocker_groups"] == [
        {"class": "read-only-policy", "gate_ids": ["tests"]}
    ]
    assert handoff["gate_verification"]["blockers"][0]["blocker_class"] == "read-only-policy"
    assert handoff["next_slice"]["title"] == "Resolve read-only gate policy blockers"
    assert "Primary blocker class: read-only-policy" in handoff_markdown
    assert "- read-only-policy: tests" in handoff_markdown
    assert "### Action Groups" in handoff_markdown
    assert "  - For tests, gate mutated tracked files during read-only verification" in (
        handoff_markdown
    )
