from __future__ import annotations

from pathlib import Path


def test_source_analysis_cache_reuses_content_hash_across_instances(tmp_path: Path) -> None:
    from quality_runner.source_analysis_cache import SourceAnalysisCache

    calls = 0

    def redact(lines: list[str]) -> list[str]:
        nonlocal calls
        calls += 1
        return [line.replace("secret", "[REDACTED]") for line in lines]

    source_text = "const secret = 'value';\n"
    first = SourceAnalysisCache(tmp_path)
    assert first.redacted_lines_for_source(
        source_text=source_text,
        source_lines=source_text.splitlines(),
        redactor=redact,
    ) == ["const [REDACTED] = 'value';"]

    second = SourceAnalysisCache(tmp_path)
    assert second.redacted_lines_for_source(
        source_text=source_text,
        source_lines=source_text.splitlines(),
        redactor=redact,
    ) == ["const [REDACTED] = 'value';"]

    assert calls == 1
    assert list((tmp_path / ".quality-runner" / "cache" / "source-analysis-v1").glob("*.json"))


def test_source_analysis_cache_invalidates_changed_content(tmp_path: Path) -> None:
    from quality_runner.source_analysis_cache import SourceAnalysisCache

    calls = 0

    def redact(lines: list[str]) -> list[str]:
        nonlocal calls
        calls += 1
        return list(lines)

    cache = SourceAnalysisCache(tmp_path)
    first_text = "const first = 1;\n"
    second_text = "const second = 2;\n"

    cache.redacted_lines_for_source(
        source_text=first_text,
        source_lines=first_text.splitlines(),
        redactor=redact,
    )
    result = cache.redacted_lines_for_source(
        source_text=second_text,
        source_lines=second_text.splitlines(),
        redactor=redact,
    )

    assert result == ["const second = 2;"]
    assert calls == 2
