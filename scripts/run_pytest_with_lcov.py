from __future__ import annotations

import sys
import trace
from pathlib import Path

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
        lines = source_file.read_text(encoding="utf-8").splitlines()
        records.append(f"SF:{relative_path}")
        line_total = 0
        line_hits = 0
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            line_total += 1
            hit_count = counts.get((str(source_file), line_number), 0)
            if hit_count > 0:
                line_hits += 1
            records.append(f"DA:{line_number},{hit_count}")
        records.append(f"LF:{line_total}")
        records.append(f"LH:{line_hits}")
        records.append("end_of_record")

    OUTPUT.write_text("\n".join(records) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
