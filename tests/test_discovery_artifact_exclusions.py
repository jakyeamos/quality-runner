from __future__ import annotations

from pathlib import Path


def test_inspect_repo_excludes_artifact_surfaces_from_recursive_detection(
    tmp_path: Path,
) -> None:
    from quality_runner.discovery import inspect_repo

    infra = tmp_path / "infra" / "terraform"
    infra.mkdir(parents=True)
    (infra / "main.tf").write_text("terraform {}\n", encoding="utf-8")
    proto = tmp_path / "proto"
    proto.mkdir()
    (proto / "service.proto").write_text('syntax = "proto3";\n', encoding="utf-8")
    source_generated = tmp_path / "src" / "generated"
    source_generated.mkdir(parents=True)
    (source_generated / "client.py").write_text("# generated source\n", encoding="utf-8")

    artifact_cases = [
        (".next/server", "main.tf"),
        (".vercel/output/functions", "service.proto"),
        (".local/court-vision/generated", "client.py"),
        ("test-results/visual-smoke", "service.proto"),
        ("artifacts/generated", "client.py"),
        ("outputs/terraform", "main.tf"),
        ("reports/protobuf", "service.proto"),
    ]
    for directory, filename in artifact_cases:
        artifact_dir = tmp_path / directory
        artifact_dir.mkdir(parents=True)
        (artifact_dir / filename).write_text("artifact\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="artifact-surface-prune-001")

    surface_paths = {surface["path"] for surface in scan["repo_surfaces"]}
    assert {"infra/terraform", "proto/service.proto", "src/generated"} <= surface_paths
    assert all(
        not path.startswith(
            (
                ".next/",
                ".vercel/",
                ".local/",
                "test-results/",
                "artifacts/",
                "outputs/",
                "reports/",
            )
        )
        for path in surface_paths
    )
    assert scan["generated_code"] == [{"path": "src/generated", "evidence": "generated directory"}]
