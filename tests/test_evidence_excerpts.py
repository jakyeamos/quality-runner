from __future__ import annotations

from pathlib import Path


def test_remediation_reuses_redacted_source_per_file(tmp_path: Path, monkeypatch) -> None:
    from quality_runner import evidence_excerpts
    from quality_runner.slice_enrichment import enrich_remediation_slices

    source = tmp_path / "src" / "feature.ts"
    source.parent.mkdir(parents=True)
    source.write_text("const first = 1;\nconst second = 2;\n", encoding="utf-8")

    calls = 0
    redact = evidence_excerpts.redact_secret_like_source_lines

    def counted_redaction(lines: list[str]) -> list[str]:
        nonlocal calls
        calls += 1
        return redact(lines)

    monkeypatch.setattr(evidence_excerpts, "redact_secret_like_source_lines", counted_redaction)

    result = enrich_remediation_slices(
        [
            {
                "id": "slice-1",
                "findings": [
                    {
                        "id": "finding-1",
                        "category": "structural:simplify",
                        "severity": "warning",
                        "file": "src/feature.ts",
                        "line": 1,
                        "fingerprint": "fingerprint-1",
                    },
                    {
                        "id": "finding-2",
                        "category": "structural:simplify",
                        "severity": "warning",
                        "file": "src/feature.ts",
                        "line": 2,
                        "fingerprint": "fingerprint-2",
                    },
                ],
            }
        ],
        repo_root=tmp_path,
        git_state=None,
        code_quality_scan=None,
        run_id=None,
    )

    assert calls == 1
    assert result[0]["findings"][0]["evidence_excerpt"]["excerpt"] == "const first = 1;"
    assert result[0]["findings"][1]["evidence_excerpt"]["excerpt"] == "const second = 2;"


def test_source_excerpt_reader_reuses_shared_scope_analysis(tmp_path: Path, monkeypatch) -> None:
    from quality_runner import evidence_excerpts
    from quality_runner.evidence_excerpts import SourceExcerptReader
    from quality_runner.scan_scope import create_text_scan_scope

    source = tmp_path / "src" / "feature.ts"
    source.parent.mkdir(parents=True)
    source.write_text("const first = 1;\n", encoding="utf-8")
    scope = create_text_scan_scope(tmp_path, scan={}, config={})
    assert scope.source_analysis_cache is not None
    scope.source_analysis_cache.redacted_lines_for_source(
        source_text=scope.files[0].text,
        source_lines=scope.files[0].lines,
        redactor=lambda _lines: ["cached source"],
    )

    def unexpected_redaction(_lines: list[str]) -> list[str]:
        raise AssertionError("shared source analysis should serve this excerpt")

    monkeypatch.setattr(evidence_excerpts, "redact_secret_like_source_lines", unexpected_redaction)

    excerpt = SourceExcerptReader(tmp_path, source_scope=scope).read_line_excerpt(
        "src/feature.ts", 1
    )

    assert excerpt is not None
    assert excerpt["excerpt"] == "cached source"
