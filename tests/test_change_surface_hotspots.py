from __future__ import annotations

import subprocess
from pathlib import Path

from quality_runner.fleet.change_surface_hotspots import assess_change_surface_hotspots

AS_OF = "2026-08-14T00:00:00+00:00"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _fixture_repo(root: Path, commits: int = 12) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "hotspots@example.com")
    _git(root, "config", "user.name", "Hotspot Fixture")
    (root / "src").mkdir()
    (root / "src/core.py").write_text(
        "# Core entry point.\n"
        "SHARED_CONCEPT = 'Shared concept'\n"
        "def load_core():\n"
        "    return SHARED_CONCEPT\n",
        encoding="utf-8",
    )
    (root / "src/helper.py").write_text(
        "# Helper entry point.\n"
        "SHARED_CONCEPT = 'Shared concept'\n"
        "def load_helper():\n"
        "    return SHARED_CONCEPT\n",
        encoding="utf-8",
    )
    (root / "src/consumer.py").write_text(
        "from .core import load_core\n"
        "from .helper import load_helper\n\n"
        "def consume():\n"
        "    return load_core(), load_helper()\n",
        encoding="utf-8",
    )
    _git(root, "add", "src")
    _git(root, "commit", "-m", "fixture")
    for index in range(commits - 1):
        for name in ("core.py", "helper.py", "consumer.py"):
            path = root / "src" / name
            path.write_text(
                path.read_text(encoding="utf-8") + f"# revision {index}\n", encoding="utf-8"
            )
        _git(root, "add", "src")
        _git(root, "commit", "-m", f"revision {index}")


def test_hotspot_audit_requires_multiple_evidence_families(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)

    result = assess_change_surface_hotspots(tmp_path, AS_OF)

    assert result["summary"]["history_commit_count"] == 12
    assert result["summary"]["multi_signal_hotspot_count"] > 0
    core = next(item for item in result["hotspots"] if item["path"] == "src/core.py")
    assert "logical_cochange" in core["evidence_families"]
    assert "repeated_concepts" in core["evidence_families"]
    assert result["status"] in {"attention", "validated"}


def test_hotspot_audit_preserves_unknown_when_history_is_too_short(tmp_path: Path) -> None:
    _fixture_repo(tmp_path, commits=2)

    result = assess_change_surface_hotspots(tmp_path, AS_OF)

    assert result["status"] == "unknown"
    assert result["score"] == 2
    assert "at least 10" in result["message"]
