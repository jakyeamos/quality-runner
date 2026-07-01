from __future__ import annotations

import sys
import trace
from pathlib import Path
from types import CodeType

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".pre-cr" / "coverage.lcov"
PACKAGE_ROOT = ROOT / "quality_runner"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    tracer = trace.Trace(count=True, trace=False, ignoredirs=[])
    exit_code = tracer.runfunc(pytest.main, ["-q"])
    write_lcov(tracer.results().counts)
    return int(exit_code)


def write_lcov(counts: dict[tuple[str, int], int]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    records: list[str] = []
    for source_file in sorted(PACKAGE_ROOT.glob("*.py")):
        relative_path = source_file.relative_to(ROOT)
        executable_lines = _executable_lines(source_file)
        records.append(f"SF:{relative_path}")
        line_hits = 0
        for line_number in executable_lines:
            hit_count = counts.get((str(source_file), line_number), 0)
            if hit_count > 0:
                line_hits += 1
            records.append(f"DA:{line_number},{hit_count}")
        records.append(f"LF:{len(executable_lines)}")
        records.append(f"LH:{line_hits}")
        records.append("end_of_record")

    OUTPUT.write_text("\n".join(records) + "\n", encoding="utf-8")


def _executable_lines(source_file: Path) -> list[int]:
    source = source_file.read_text(encoding="utf-8")
    code = compile(source, str(source_file), "exec")
    return sorted(_line_starts(code))


def _line_starts(code: CodeType) -> set[int]:
    lines = {item[2] for item in code.co_lines() if item[2] is not None and item[2] > 0}
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            lines.update(_line_starts(constant))
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
