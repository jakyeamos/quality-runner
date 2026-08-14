from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.fleet.documentation_visibility import assess_developer_legibility
from quality_runner.fleet.legibility_evidence import collect_documents, collect_link_evidence

AS_OF = "2026-08-14T00:00:00+00:00"


def _assessment(root: Path) -> dict[str, Any]:
    documents = collect_documents(root)
    return assess_developer_legibility(
        root,
        documents,
        collect_link_evidence(root, documents),
        AS_OF,
    )


def test_visibility_audit_covers_document_links_source_anchors_diagrams_and_code_docs(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "docs/diagrams").mkdir(parents=True)
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "src/service.py").write_text(
        "# Public service entry point.\ndef start_service():\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Repository\n\nLast reviewed: 2026-08-14\n\n"
        "## Quick start\n\n```bash\npytest -q\n```\n\n"
        "See [architecture](docs/architecture.md), [the service](src/service.py#L1-L3), "
        "and [upstream](https://github.com/example/project/blob/0123456789abcdef0123456789abcdef01234567/src/service.py#L2-L2).\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/architecture.md").write_text(
        "# Infrastructure deployment\n\nLast reviewed: 2026-08-14\n\n"
        "![Deployment diagram](diagrams/deployment.mmd)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/diagrams/deployment.mmd").write_text(
        "flowchart LR\n  client --> service\n",
        encoding="utf-8",
    )

    result = _assessment(tmp_path)

    assert result["score"] == 3
    assert result["status"] == "enforced"
    assert result["traceability"]["valid_count"] == 2
    assert result["diagrams"]["linked_count"] == 1
    assert result["public_contracts"]["documented_count"] == 1
    assert {lane["id"] for lane in result["lanes"] if lane["applicable"]} == {
        "orientation",
        "navigation_traceability",
        "architecture_visibility",
        "semantic_naming",
        "public_contracts",
        "rationale_invariants",
        "executable_understanding",
        "ownership_freshness",
    }


def test_visibility_audit_blocks_invalid_document_and_source_links(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/service.py").write_text(
        "# Public service entry point.\ndef start_service():\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "[missing](docs/nope.md)\n[service](src/service.py#L20-L21)\n",
        encoding="utf-8",
    )

    result = _assessment(tmp_path)

    assert result["status"] == "blocked"
    assert result["score"] <= 2
    assert result["traceability"]["invalid_count"] == 1


def test_visibility_audit_keeps_diagrams_not_applicable_without_infrastructure_surface(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Small library\n\n[implementation](src/library.py#L1-L2)\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src/library.py").write_text(
        "# Library entry point.\ndef load_library():\n    return True\n",
        encoding="utf-8",
    )

    result = _assessment(tmp_path)

    diagram_lane = next(lane for lane in result["lanes"] if lane["id"] == "architecture_visibility")
    assert diagram_lane["applicable"] is False
    assert result["score"] <= 2


def test_legibility_cannot_reach_newcomer_verified_from_static_coverage(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Library purpose\n\n## Quick start\n```bash\npytest -q\n```\n"
        "## Architecture\nSee [source](src/library.py#L1-L3).\n"
        "Last reviewed: 2026-08-14\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src/library.py").write_text(
        "# Explain the caller contract.\ndef load_library():\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_library.py").write_text("def test_library():\n    assert True\n")

    result = _assessment(tmp_path)

    assert result["score"] <= 3
    assert result["newcomer_evidence"]["status"] == "missing"
