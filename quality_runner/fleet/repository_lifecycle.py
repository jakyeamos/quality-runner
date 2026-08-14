from __future__ import annotations

from pathlib import Path


def documented_archival_repository(root: Path) -> bool:
    text = _readme_text(root)
    return (
        "archival notice" in text
        and "generated library" in text
        and ("do not regenerate" in text or "retained" in text)
    )


def documented_deprecated_repository(root: Path) -> bool:
    text = _readme_text(root)
    retained = "retained for historical provenance" in text or "historical implementation" in text
    replacement = "active repository" in text or "active replacement" in text
    return "deprecated" in text and retained and replacement


def _readme_text(root: Path) -> str:
    try:
        return (root / "README.md").read_text(encoding="utf-8")[:20_000].lower()
    except OSError:
        return ""
