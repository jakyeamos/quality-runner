from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_direct_gate_execution_requires_a_separate_disposable_root(tmp_path: Path) -> None:
    from quality_runner.gate_verification import verify_discovered_gates

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
    with pytest.raises(ValueError, match="separate disposable execution root"):
        verify_discovered_gates(
            repo_root=tmp_path,
            capability_map={
                "available": [
                    {
                        "id": "tests",
                        "type": "script",
                        "command": command,
                        "source": "local policy",
                    }
                ]
            },
            execute_discovered_gates=True,
            read_only_gates=True,
        )

    assert tracked_file.read_text(encoding="utf-8") == "original\n"
