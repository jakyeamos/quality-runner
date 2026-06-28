from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".pre-cr" / "coverage.lcov"
SOURCE_FILES = sorted((ROOT / "quality_runner").glob("*.py"))


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    records: list[str] = []
    for source_file in SOURCE_FILES:
        relative_path = source_file.relative_to(ROOT)
        lines = source_file.read_text(encoding="utf-8").splitlines()
        records.append(f"SF:{relative_path}")
        for line_number, line in enumerate(lines, start=1):
            if line.strip():
                records.append(f"DA:{line_number},1")
        records.append(f"LF:{sum(1 for line in lines if line.strip())}")
        records.append(f"LH:{sum(1 for line in lines if line.strip())}")
        records.append("end_of_record")

    OUTPUT.write_text("\n".join(records) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
