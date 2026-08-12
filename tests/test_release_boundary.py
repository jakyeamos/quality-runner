from __future__ import annotations

import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

from quality_runner.fleet.maturity_feed import validate_maturity_feed
from quality_runner.release_boundary import release_boundary_payload

ROOT = Path(__file__).resolve().parents[1]


def _policy() -> dict[str, object]:
    return {
        "schema_version": "change-surface-matrix/v1",
        "subject": {"kind": "repository", "id": "fixture"},
        "owner": "repository-owner",
        "last_reviewed": "2026-08-11",
        "surfaces": [
            {
                "id": "core",
                "scope": "local",
                "distribution": "public_core",
                "path": "quality_runner/",
                "owner": "repository-owner",
                "condition": "core changes",
                "operations": ["add", "change", "remove"],
                "validation": ["pytest"],
                "status": "applicable",
            },
            {
                "id": "consumer",
                "scope": "external",
                "distribution": "public_adapter",
                "contract_fixtures": ["fixtures/contracts/public-adapters/consumer.json"],
                "path": "consumer",
                "owner": "consumer-owner",
                "condition": "contract changes",
                "operations": ["add", "change", "remove"],
                "validation": ["consumer contract test"],
                "status": "applicable",
            },
        ],
        "release_boundary": {
            "tracked_content": {
                "include_globs": ["README.md", "quality_runner/*.py"],
                "local_only_globs": [],
                "forbidden_patterns": [
                    {
                        "id": "personal-home-path",
                        "pattern": "/(?:Users|home)/[A-Za-z0-9._-]+/",
                    }
                ],
            },
            "artifacts": {
                "wheel": {
                    "allow_prefixes": ["quality_runner/"],
                    "allow_globs": ["quality_runner-*.dist-info/*"],
                },
                "sdist": {
                    "allow_paths": ["README.md"],
                    "allow_prefixes": ["quality_runner/"],
                },
            },
        },
        "unresolved_surfaces": [],
    }


def _write_repository(root: Path, policy: dict[str, object]) -> None:
    (root / ".agents").mkdir(parents=True)
    (root / "quality_runner").mkdir()
    fixture = root / "fixtures/contracts/public-adapters/consumer.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('{"schema":"consumer-fixture/v1"}\n', encoding="utf-8")
    (root / ".agents/change-surface-matrix.json").write_text(json.dumps(policy), encoding="utf-8")
    (root / "README.md").write_text("# Public fixture\n", encoding="utf-8")
    (root / "quality_runner/__init__.py").write_text("VERSION = '1'\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Release Boundary Tests",
            "-c",
            "user.email=release-boundary@example.com",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )


def _write_archives(dist: Path, *, extra_wheel_path: str | None = None) -> None:
    dist.mkdir()
    with zipfile.ZipFile(dist / "quality_runner-1-py3-none-any.whl", "w") as archive:
        archive.writestr("quality_runner/__init__.py", "VERSION = '1'\n")
        archive.writestr("quality_runner-1.dist-info/METADATA", "Name: quality-runner\n")
        if extra_wheel_path is not None:
            archive.writestr(extra_wheel_path, "private\n")
    with tarfile.open(dist / "quality_runner-1.tar.gz", "w:gz") as archive:
        for name, content in (
            ("quality_runner-1/README.md", b"# Public fixture\n"),
            ("quality_runner-1/quality_runner/__init__.py", b"VERSION = '1'\n"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_release_boundary_passes_classified_sanitized_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    _write_repository(tmp_path, _policy())
    dist = tmp_path / "dist"
    _write_archives(dist)
    monkeypatch.setattr(
        "quality_runner.release_boundary._clean_room_install_check",
        lambda _wheel: {"id": "clean_room_install", "status": "passed"},
    )

    payload = release_boundary_payload(repo_root=tmp_path, dist_dir=dist)

    assert payload["status"] == "passed"
    assert payload["blocking_check_ids"] == []


def test_release_boundary_blocks_unclassified_surface(tmp_path: Path, monkeypatch) -> None:
    policy = _policy()
    del policy["surfaces"][0]["distribution"]  # type: ignore[index]
    _write_repository(tmp_path, policy)
    dist = tmp_path / "dist"
    _write_archives(dist)
    monkeypatch.setattr(
        "quality_runner.release_boundary._clean_room_install_check",
        lambda _wheel: {"id": "clean_room_install", "status": "passed"},
    )

    payload = release_boundary_payload(repo_root=tmp_path, dist_dir=dist)

    classification = next(
        check for check in payload["checks"] if check["id"] == "surface_classification"
    )
    assert payload["status"] == "blocked"
    assert classification["violations"] == [
        {"rule": "unclassified-distribution", "path": "surfaces[0]"}
    ]


def test_release_boundary_reports_source_leak_without_echoing_value(
    tmp_path: Path, monkeypatch
) -> None:
    _write_repository(tmp_path, _policy())
    source = tmp_path / "quality_runner/__init__.py"
    source.write_text('ROOT = "/Users/private/projects/app"\n', encoding="utf-8")
    subprocess.run(["git", "add", "quality_runner/__init__.py"], cwd=tmp_path, check=True)
    dist = tmp_path / "dist"
    _write_archives(dist)
    monkeypatch.setattr(
        "quality_runner.release_boundary._clean_room_install_check",
        lambda _wheel: {"id": "clean_room_install", "status": "passed"},
    )

    payload = release_boundary_payload(repo_root=tmp_path, dist_dir=dist)
    serialized = json.dumps(payload)

    tracked = next(check for check in payload["checks"] if check["id"] == "tracked_public_content")
    assert tracked["status"] == "blocked"
    assert tracked["violations"] == [
        {"rule": "personal-home-path", "path": "quality_runner/__init__.py", "line": 1}
    ]
    assert "/Users/private" not in serialized


def test_release_boundary_blocks_tracked_local_only_content(tmp_path: Path, monkeypatch) -> None:
    policy = _policy()
    policy["release_boundary"]["tracked_content"]["local_only_globs"] = [  # type: ignore[index]
        "docs/private-ops.md"
    ]
    _write_repository(tmp_path, policy)
    private_ops = tmp_path / "docs/private-ops.md"
    private_ops.parent.mkdir()
    private_ops.write_text("# Private operations\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/private-ops.md"], cwd=tmp_path, check=True)
    dist = tmp_path / "dist"
    _write_archives(dist)
    monkeypatch.setattr(
        "quality_runner.release_boundary._clean_room_install_check",
        lambda _wheel: {"id": "clean_room_install", "status": "passed"},
    )

    payload = release_boundary_payload(repo_root=tmp_path, dist_dir=dist)

    tracked = next(check for check in payload["checks"] if check["id"] == "tracked_public_content")
    assert tracked["status"] == "blocked"
    assert tracked["violations"] == [
        {"rule": "tracked-local-only-content", "path": "docs/private-ops.md"}
    ]


def test_release_boundary_blocks_archive_member_outside_allowlist(
    tmp_path: Path, monkeypatch
) -> None:
    _write_repository(tmp_path, _policy())
    dist = tmp_path / "dist"
    _write_archives(dist, extra_wheel_path="private/config.json")
    monkeypatch.setattr(
        "quality_runner.release_boundary._clean_room_install_check",
        lambda _wheel: {"id": "clean_room_install", "status": "passed"},
    )

    payload = release_boundary_payload(repo_root=tmp_path, dist_dir=dist)

    archive = next(check for check in payload["checks"] if check["id"] == "distribution_archives")
    assert archive["status"] == "blocked"
    assert {item["rule"] for item in archive["violations"]} == {"wheel-path-not-allowlisted"}


def test_public_pronto_fixture_satisfies_the_feed_contract() -> None:
    fixture = json.loads(
        (ROOT / "fixtures/contracts/public-adapters/pronto-maturity-feed.json").read_text(
            encoding="utf-8"
        )
    )

    validate_maturity_feed(fixture)
