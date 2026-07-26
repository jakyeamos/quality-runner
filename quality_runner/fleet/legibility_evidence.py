from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import (
    FRESHNESS_DAYS,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENTS,
    relative_path,
)

DOC_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "CONTRIBUTING.md",
    ".github/copilot-instructions.md",
    ".agents/context/README.md",
    ".context/README.md",
    "docs/README.md",
    "docs/architecture.md",
    "docs/development.md",
    "docs/contributing.md",
    "docs/deployment.md",
    "docs/runbook.md",
)


def collect_documents(root: Path) -> dict[str, str]:
    documents: dict[str, str] = {}
    for relative in DOC_FILES:
        path = root / relative
        if path.is_file():
            content = read_bounded(path)
            if content is not None:
                documents[relative] = content
    docs_root = root / "docs"
    if docs_root.is_dir():
        count = len(documents)
        for path in sorted(docs_root.rglob("*.md")):
            if count >= MAX_DOCUMENTS or path.is_symlink():
                break
            relative = path.relative_to(root).as_posix()
            if relative in documents:
                continue
            content = read_bounded(path)
            if content is not None:
                documents[relative] = content
                count += 1
    return documents


def read_bounded(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def collect_link_evidence(root: Path, documents: dict[str, str]) -> dict[str, Any]:
    links: list[dict[str, str]] = []
    invalid: list[str] = []
    pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    for relative, content in sorted(documents.items()):
        for target in pattern.findall(content):
            cleaned = target.strip().split(maxsplit=1)[0].strip("<>")
            if not cleaned or cleaned.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target_path = (root / relative).parent / cleaned.split("#", maxsplit=1)[0]
            normalized = relative_path(root, target_path)
            if target_path.exists():
                links.append({"source": relative, "target": normalized, "status": "valid"})
            else:
                invalid.append(f"{relative}->{normalized}")
                links.append({"source": relative, "target": normalized, "status": "invalid"})
    return {"links": links, "invalid": invalid, "invalid_count": len(invalid)}


def collect_freshness_evidence(documents: dict[str, str], as_of: str) -> dict[str, Any]:
    parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if parsed_as_of.tzinfo is None:
        parsed_as_of = parsed_as_of.replace(tzinfo=UTC)
    stale_paths: list[str] = []
    reviewed_paths: list[str] = []
    date_pattern = re.compile(r"(?i)(?:last\s+reviewed|reviewed|updated)\s*:\s*(\d{4}-\d{2}-\d{2})")
    for relative, content in documents.items():
        match = date_pattern.search(content)
        if not match:
            continue
        reviewed_paths.append(relative)
        try:
            reviewed = datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)
        except ValueError:
            stale_paths.append(relative)
            continue
        if parsed_as_of - reviewed > timedelta(days=FRESHNESS_DAYS):
            stale_paths.append(relative)
    return {
        "freshness_window_days": FRESHNESS_DAYS,
        "reviewed_paths": sorted(reviewed_paths),
        "stale_paths": sorted(stale_paths),
        "status": "stale" if stale_paths else "known" if reviewed_paths else "unknown",
    }


def term_evidence(documents: dict[str, str], matches: list[str]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for relative, content in sorted(documents.items()):
        lower = content.lower()
        found = [term for term in matches if term in lower]
        if found:
            evidence.append({"path": relative, "detail": f"matched terms: {', '.join(found[:4])}"})
    return evidence[:12]


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
