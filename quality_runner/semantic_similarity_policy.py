from __future__ import annotations

from typing import Any

DEFAULT_SIMILARITY_ENABLED = True
DEFAULT_SIMILARITY_BACKEND = "native"
DEFAULT_SIMILARITY_THRESHOLD = 0.87
DEFAULT_SIMILARITY_MIN_LINES = 8
DEFAULT_SIMILARITY_MAX_PAIRS = 25
DEFAULT_SIMILARITY_TIMEOUT_SECONDS = 30
DEFAULT_SIMILARITY_INCLUDE_TESTS = False


def similarity_policy_defaults(policy: dict[str, Any]) -> dict[str, Any]:
    similarity_enabled = policy.get("similarity_enabled")
    similarity_backend = policy.get("similarity_backend")
    similarity_threshold = policy.get("similarity_threshold")
    similarity_min_lines = policy.get("similarity_min_lines")
    similarity_max_pairs = policy.get("similarity_max_pairs")
    similarity_timeout_seconds = policy.get("similarity_timeout_seconds")
    similarity_include_tests = policy.get("similarity_include_tests")
    return {
        "similarity_enabled": similarity_enabled
        if isinstance(similarity_enabled, bool)
        else DEFAULT_SIMILARITY_ENABLED,
        "similarity_backend": similarity_backend
        if similarity_backend in {"native", "external"}
        else DEFAULT_SIMILARITY_BACKEND,
        "similarity_threshold": similarity_threshold
        if isinstance(similarity_threshold, (int, float)) and 0 <= float(similarity_threshold) <= 1
        else DEFAULT_SIMILARITY_THRESHOLD,
        "similarity_min_lines": similarity_min_lines
        if isinstance(similarity_min_lines, int) and similarity_min_lines > 0
        else DEFAULT_SIMILARITY_MIN_LINES,
        "similarity_max_pairs": similarity_max_pairs
        if isinstance(similarity_max_pairs, int) and similarity_max_pairs > 0
        else DEFAULT_SIMILARITY_MAX_PAIRS,
        "similarity_timeout_seconds": similarity_timeout_seconds
        if isinstance(similarity_timeout_seconds, int) and similarity_timeout_seconds > 0
        else DEFAULT_SIMILARITY_TIMEOUT_SECONDS,
        "similarity_include_tests": similarity_include_tests
        if isinstance(similarity_include_tests, bool)
        else DEFAULT_SIMILARITY_INCLUDE_TESTS,
    }
