from __future__ import annotations

from pathlib import Path

from quality_runner.code_quality_paths import _split_lines
from quality_runner.core.audit_contracts import ScannedTextFile


def read_text_file(root: Path, path: Path) -> ScannedTextFile:
    text = path.read_text(encoding="utf-8", errors="replace")
    return ScannedTextFile(
        path=path.relative_to(root).as_posix(),
        text=text,
        lines=_split_lines(text),
    )
