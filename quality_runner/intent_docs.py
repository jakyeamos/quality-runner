from __future__ import annotations

from pathlib import Path


def discover_intent_docs(repo_root: Path) -> list[dict[str, str]]:
    root = repo_root.expanduser().resolve()
    docs: list[dict[str, str]] = []

    for doc_type, candidates in _INTENT_DOC_CANDIDATES:
        for candidate in candidates:
            path = root / candidate
            if path.is_file() and not path.is_symlink():
                docs.append({"type": doc_type, "path": candidate})
                break

    docs.extend(_discover_adrs(root))
    return sorted(docs, key=lambda item: (item["type"], item["path"]))


def intent_docs_markdown_lines(intent_docs: object) -> list[str]:
    if not isinstance(intent_docs, list) or not intent_docs:
        return []
    lines = ["## Relevant Repo Intent Docs", ""]
    for doc in intent_docs:
        if not isinstance(doc, dict):
            continue
        doc_type = doc.get("type")
        path = doc.get("path")
        if isinstance(doc_type, str) and isinstance(path, str) and doc_type and path:
            lines.append(f"- {doc_type}: `{path}`")
    lines.append("")
    return lines


_INTENT_DOC_CANDIDATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("product", ("PRODUCT.md", "docs/PRODUCT.md")),
    ("design", ("DESIGN.md", "docs/DESIGN.md")),
    ("context", ("CONTEXT.md", "docs/CONTEXT.md")),
)


def _discover_adrs(root: Path) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    for directory in ("docs/adr", "docs/adrs", "adr"):
        adr_dir = root / directory
        if not adr_dir.is_dir() or adr_dir.is_symlink():
            continue
        for path in sorted(adr_dir.glob("*.md")):
            if path.is_file() and not path.is_symlink():
                docs.append(
                    {
                        "type": "adr",
                        "path": str(path.relative_to(root)),
                    }
                )
    return docs
