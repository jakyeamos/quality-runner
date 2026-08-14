from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from quality_runner.cache_limits import allocated_bytes, prune_lru_files, prune_lru_tree


def _entry(path: Path, content: str, mtime_ns: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_lru_pruning_enforces_byte_and_entry_limits_atomically(tmp_path: Path) -> None:
    cache = tmp_path / "owned"
    oldest = _entry(cache / "oldest.json", "a" * 16, 1)
    middle = _entry(cache / "middle.json", "b" * 16, 2)
    newest = _entry(cache / "newest.json", "c" * 16, 3)

    result = prune_lru_files(
        owned_root=cache,
        cache_dir=cache,
        candidates=(oldest, middle, newest),
        max_entries=2,
        max_bytes=allocated_bytes(middle) + allocated_bytes(newest),
    )

    assert result.removed == (oldest,)
    assert not oldest.exists()
    assert middle.is_file() and newest.is_file()
    assert not list(cache.glob(".qr-prune-*"))


def test_pruning_cannot_escape_owned_root_through_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    victim = _entry(outside / "victim.json", "keep", 1)
    owned = tmp_path / "owned"
    owned.symlink_to(outside, target_is_directory=True)

    result = prune_lru_files(
        owned_root=owned,
        cache_dir=owned,
        candidates=(owned / "victim.json",),
        max_entries=0,
        max_bytes=0,
    )

    assert result.removed == ()
    assert victim.read_text(encoding="utf-8") == "keep"


def test_recursive_lru_skips_external_symlink_targets(tmp_path: Path) -> None:
    owned = tmp_path / "owned"
    nested = _entry(owned / "nested/cache.json", "remove", 1)
    outside = _entry(tmp_path / "outside/keep.json", "keep", 1)
    (owned / "external").symlink_to(outside.parent, target_is_directory=True)

    result = prune_lru_tree(owned_root=owned, max_entries=0, max_bytes=0)

    assert nested in result.removed
    assert outside.read_text(encoding="utf-8") == "keep"


def test_inventory_cache_concurrent_writers_remain_valid_and_bounded(
    tmp_path: Path, monkeypatch
) -> None:
    from quality_runner import inventory_cache

    monkeypatch.setattr(inventory_cache, "_MAX_REPOSITORY_IDENTITIES", 8)
    monkeypatch.setattr(inventory_cache, "_MAX_CACHE_BYTES", 16 * 1024 * 1024)
    cache = tmp_path / "inventory"
    cache.mkdir()

    threads = [
        threading.Thread(
            target=inventory_cache._write,
            args=(cache / f"{index:02d}.json", {"schema": "quality-runner-scan-v0.1"}),
        )
        for index in range(16)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    entries = list(cache.glob("*.json"))
    assert len(entries) <= 8
    assert all(isinstance(json.loads(path.read_text(encoding="utf-8")), dict) for path in entries)


def test_cache_namespace_limits_match_the_maturity_contract() -> None:
    from quality_runner import (
        incremental_analysis_cache,
        inventory_cache,
        semantic_similarity_cache,
        source_analysis_cache,
    )

    assert incremental_analysis_cache._MAX_CACHE_BYTES == 64 * 1024 * 1024
    assert source_analysis_cache._MAX_CACHE_BYTES == 64 * 1024 * 1024
    assert semantic_similarity_cache._MAX_CACHE_BYTES == 64 * 1024 * 1024
    assert inventory_cache._MAX_CACHE_BYTES == 16 * 1024 * 1024
    assert inventory_cache._MAX_REPOSITORY_IDENTITIES == 8
