from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.evidence_redaction import redact_secret_like_source_lines


def read_line_excerpt(
    repo_root: Path,
    file: str,
    line: int,
    *,
    context: int = 2,
) -> dict[str, Any] | None:
    if line < 1:
        return None
    path = (repo_root / file).resolve()
    root = repo_root.expanduser().resolve()
    if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if line > len(lines):
        return None
    redacted_lines = redact_secret_like_source_lines(lines)
    index = line - 1
    before_start = max(0, index - context)
    after_end = min(len(lines), index + context + 1)
    return {
        "file": file,
        "line": line,
        "excerpt": redacted_lines[index],
        "context_before": redacted_lines[before_start:index],
        "context_after": redacted_lines[index + 1 : after_end],
    }


def enrich_finding_evidence(
    repo_root: Path | None,
    finding: dict[str, Any],
    *,
    rule_id: str | None = None,
) -> dict[str, Any] | None:
    if repo_root is None:
        return None
    file = finding.get("file")
    line = finding.get("line")
    if not isinstance(file, str) or not isinstance(line, int):
        return None
    excerpt = read_line_excerpt(repo_root, file, line)
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
