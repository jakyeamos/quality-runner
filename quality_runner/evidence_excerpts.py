from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from quality_runner.core.audit_contracts import ScannedTextFile, TextScanScope
from quality_runner.evidence_redaction import redact_secret_like_source_lines
from quality_runner.source_analysis_cache import SourceAnalysisCache


class SourceExcerptReader:
    def __init__(
        self,
        repo_root: Path,
        *,
        source_scope: TextScanScope | None = None,
        analysis_cache: SourceAnalysisCache | None = None,
    ) -> None:
        self._root = repo_root.expanduser().resolve()
        self._redacted_lines_by_path: dict[Path, list[str] | None] = {}
        self._source_files: Mapping[str, ScannedTextFile] = (
            {file_info.path: file_info for file_info in source_scope.files}
            if source_scope is not None
            else {}
        )
        scope_cache = (
            cast(SourceAnalysisCache, source_scope.source_analysis_cache)
            if source_scope is not None and source_scope.source_analysis_cache is not None
            else None
        )
        self._analysis_cache = analysis_cache or scope_cache or SourceAnalysisCache(self._root)

    def read_line_excerpt(
        self,
        file: str,
        line: int,
        *,
        context: int = 2,
    ) -> dict[str, Any] | None:
        if line < 1:
            return None
        candidate = self._root / file
        if candidate.is_symlink():
            return None
        path = candidate.resolve()
        if not path.is_relative_to(self._root) or not path.is_file():
            return None
        redacted_lines = self._redacted_lines(path)
        if redacted_lines is None or line > len(redacted_lines):
            return None
        index = line - 1
        before_start = max(0, index - context)
        after_end = min(len(redacted_lines), index + context + 1)
        return {
            "file": file,
            "line": line,
            "excerpt": redacted_lines[index],
            "context_before": redacted_lines[before_start:index],
            "context_after": redacted_lines[index + 1 : after_end],
        }

    def _redacted_lines(self, path: Path) -> list[str] | None:
        if path in self._redacted_lines_by_path:
            return self._redacted_lines_by_path[path]
        relative_path = path.relative_to(self._root).as_posix()
        source_file = self._source_files.get(relative_path)
        if source_file is not None:
            redacted_lines = self._analysis_cache.redacted_lines_for_source(
                source_text=source_file.text,
                source_lines=source_file.lines,
                redactor=redact_secret_like_source_lines,
            )
        else:
            redacted_lines = self._analysis_cache.redacted_lines_for_path(
                path,
                redactor=redact_secret_like_source_lines,
            )
        if redacted_lines is None:
            self._redacted_lines_by_path[path] = None
            return None
        self._redacted_lines_by_path[path] = redacted_lines
        return redacted_lines


def read_line_excerpt(
    repo_root: Path,
    file: str,
    line: int,
    *,
    context: int = 2,
) -> dict[str, Any] | None:
    return SourceExcerptReader(repo_root).read_line_excerpt(file, line, context=context)


def enrich_finding_evidence(
    repo_root: Path | None,
    finding: dict[str, Any],
    *,
    rule_id: str | None = None,
    excerpt_reader: SourceExcerptReader | None = None,
) -> dict[str, Any] | None:
    reader = excerpt_reader
    if reader is None and repo_root is not None:
        reader = SourceExcerptReader(repo_root)
    if reader is None:
        return None
    file = finding.get("file")
    line = finding.get("line")
    if not isinstance(file, str) or not isinstance(line, int):
        return None
    excerpt = reader.read_line_excerpt(file, line)
    if excerpt is None:
        return None
    if isinstance(rule_id, str) and rule_id:
        excerpt["rule_id"] = rule_id
    elif isinstance(finding.get("rule_id"), str):
        excerpt["rule_id"] = finding["rule_id"]
    fingerprint = finding.get("fingerprint")
    if isinstance(fingerprint, str) and fingerprint:
        excerpt["fingerprint"] = fingerprint
    return excerpt
