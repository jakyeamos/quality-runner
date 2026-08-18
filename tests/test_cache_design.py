from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from quality_runner.config import load_repo_config
from quality_runner.fleet.cache_design import assess_cache_design, public_cache_design_projection

AS_OF = "2026-08-14T17:00:00+00:00"


def _config(*paths: dict[str, object]) -> dict[str, object]:
    return {"cache_design": {"paths": list(paths)}}


def _write_bytes(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * count)


def test_no_derived_storage_is_not_applicable(tmp_path: Path) -> None:
    assessment = assess_cache_design(tmp_path, {}, AS_OF)

    assert assessment["status"] == "not_applicable"
    assert assessment["score"] is None
    assert assessment["applicability"] == "not_applicable"


def test_raw_size_does_not_lower_a_bounded_cache_score(tmp_path: Path) -> None:
    _write_bytes(tmp_path / ".cache/blob", 2 * 1024 * 1024)
    assessment = assess_cache_design(
        tmp_path,
        _config(
            {
                "path": ".cache",
                "class": "tool_cache",
                "lifecycle": "bounded",
                "max_bytes": 8 * 1024 * 1024,
            }
        ),
        AS_OF,
    )

    assert assessment["score"] == 3
    assert assessment["status"] == "maintained"
    assert assessment["totals"]["logical_bytes"] == 2 * 1024 * 1024
    assert assessment["risk_flags"] == []


def test_small_unbounded_cache_scores_one(tmp_path: Path) -> None:
    _write_bytes(tmp_path / ".cache/one", 1)

    assessment = assess_cache_design(tmp_path, {}, AS_OF)

    assert assessment["score"] == 1
    assert assessment["risk_flags"] == ["unbounded_cache"]


def test_known_disposable_path_overridden_as_durable_scores_zero(tmp_path: Path) -> None:
    _write_bytes(tmp_path / ".cache/database.sqlite", 16)
    assessment = assess_cache_design(
        tmp_path,
        _config(
            {
                "path": ".cache",
                "class": "durable_state",
                "lifecycle": "durable",
                "reason": "This legacy path contains user-authored offline records.",
            }
        ),
        AS_OF,
    )

    assert assessment["score"] == 0
    assert assessment["risk_flags"] == ["durable_disposable_conflict"]


def test_pnpm_style_hard_link_is_attributed_as_shared(tmp_path: Path) -> None:
    store_file = tmp_path / "external-store/package"
    _write_bytes(store_file, 4096)
    linked_file = tmp_path / "node_modules/pkg/package"
    linked_file.parent.mkdir(parents=True)
    os.link(store_file, linked_file)

    assessment = assess_cache_design(tmp_path, {}, AS_OF)
    surface = next(item for item in assessment["surfaces"] if item["path"] == "node_modules")

    assert surface["shared_file_count"] == 1
    assert surface["shared_allocated_bytes"] > 0
    assert surface["exclusive_allocated_bytes"] == 0


def test_external_symlink_is_not_followed_and_yields_unknown(tmp_path: Path) -> None:
    external = tmp_path.parent / "external-cache"
    _write_bytes(external / "blob", 32)
    (tmp_path / ".cache").symlink_to(external, target_is_directory=True)

    assessment = assess_cache_design(tmp_path, {}, AS_OF)

    assert assessment["status"] == "unknown"
    assert assessment["score"] is None
    assert assessment["totals"]["logical_bytes"] == 0
    assert assessment["warnings"] == [".cache: symlinked derived-storage roots are not traversed"]


def test_unclassified_candidate_and_traversal_exhaustion_yield_unknown(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "custom-cache/blob", 32)
    ambiguous = assess_cache_design(tmp_path, {}, AS_OF)
    exhausted = assess_cache_design(tmp_path, {}, AS_OF, max_entries=0)

    assert ambiguous["status"] == "unknown"
    assert "unclassified_storage" in ambiguous["risk_flags"]
    assert exhausted["status"] == "unknown"
    assert "measurement_incomplete" in exhausted["risk_flags"]


def test_python_tool_caches_are_classified_without_ambiguity(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "src/package/__pycache__/module.pyc", 32)
    _write_bytes(tmp_path / ".pytest_cache/v/cache/nodeids", 32)

    assessment = assess_cache_design(tmp_path, {}, AS_OF)

    assert assessment["status"] == "validated"
    assert assessment["score"] == 2
    assert "unclassified_storage" not in assessment["risk_flags"]
    assert {item["source"] for item in assessment["surfaces"]} == {"pytest", "python"}


def test_two_snapshot_receipt_enables_level_four(tmp_path: Path) -> None:
    _write_bytes(tmp_path / ".quality-runner/cache/item", 32)
    receipt = tmp_path / ".quality-runner/cache-design-equivalence.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "quality-runner-cache-design-equivalence/v1",
                "automated_enforcement": True,
                "cold_warm_equivalent": True,
                "within_policy": True,
                "snapshots": [
                    {
                        "observed_at": "2026-08-13T17:00:00+00:00",
                        "allocated_bytes": 100,
                        "cache_hit_count": 2,
                    },
                    {
                        "observed_at": AS_OF,
                        "allocated_bytes": 120,
                        "cache_hit_count": 7,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assessment = assess_cache_design(tmp_path, {}, AS_OF)

    assert assessment["score"] == 4
    assert assessment["growth"]["allocated_bytes_delta"] == 20
    assert assessment["growth"]["cache_hit_count_delta"] == 5


def test_public_projection_contains_aggregates_but_no_repo_paths(tmp_path: Path) -> None:
    _write_bytes(tmp_path / ".cache/item", 32)
    assessment = assess_cache_design(tmp_path, {}, AS_OF)

    projection = public_cache_design_projection(assessment)

    assert projection["categories"]["tool_cache"]["file_count"] == 1
    assert "surfaces" not in projection
    assert str(tmp_path) not in json.dumps(projection)


def test_config_accepts_literal_bounded_paths_and_rejects_unsafe_overrides(
    tmp_path: Path,
) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        """
[quality_runner]

[[quality_runner.cache_design.paths]]
path = "var/cache"
class = "tool_cache"
lifecycle = "bounded"
max_bytes = 1024

[[quality_runner.cache_design.paths]]
path = "../outside"
class = "tool_cache"
lifecycle = "bounded"
max_entries = 8

[[quality_runner.cache_design.paths]]
path = ".cache"
class = "durable_state"
lifecycle = "durable"
""",
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["cache_design"] == {
        "paths": [
            {
                "path": "var/cache",
                "class": "tool_cache",
                "lifecycle": "bounded",
                "max_bytes": 1024,
            }
        ]
    }
    assert [warning["message"] for warning in config["warnings"]] == [
        "quality_runner.cache_design.paths[1].path must be a literal repository-relative path",
        "quality_runner.cache_design.paths[2].reason is required when a known disposable path is overridden as durable_state",
    ]


def test_unreadable_path_yields_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / ".cache"
    cache.mkdir()
    real_scandir = os.scandir

    def denied(path: object):
        if Path(path) == cache:
            raise PermissionError("fixture")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", denied)

    assessment = assess_cache_design(tmp_path, {}, AS_OF)

    assert assessment["status"] == "unknown"
    assert any("PermissionError" in warning for warning in assessment["warnings"])
