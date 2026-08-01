from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class CacheStats:
    considered_files: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    recomputed_files: int = 0
    write_failures: int = 0
    pruned_entries: int = 0
    invalidation_reasons: Counter[str] = field(default_factory=Counter)
    recomputed_paths: list[str] = field(default_factory=list)
    index_writes: int = 0
    source_bytes_read: int = 0
