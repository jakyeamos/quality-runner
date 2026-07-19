from __future__ import annotations

import os
import subprocess
import sys
import time
import trace
from pathlib import Path
from types import CodeType

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".pre-cr" / "coverage.lcov"
PACKAGE_ROOT = ROOT / "quality_runner"
GIT_LOCAL_ENV_VARS = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    for name in GIT_LOCAL_ENV_VARS:
        os.environ.pop(name, None)
    pytest_args = build_pytest_args(sys.argv[1:])
    print(
        f"[pre-cr-tests] starting pytest: {' '.join(pytest_args)}",
        file=sys.stderr,
        flush=True,
    )
    started = time.monotonic()
    tracer = trace.Trace(
        count=True,
        trace=False,
        ignoredirs=[sys.prefix, str(ROOT / ".venv")],
    )
    exit_code = tracer.runfunc(pytest.main, pytest_args)
    elapsed = time.monotonic() - started
    print(
        f"[pre-cr-tests] pytest finished in {elapsed:.1f}s with exit code {exit_code}",
        file=sys.stderr,
        flush=True,
    )
    write_lcov(tracer.results().counts)
    print(f"[pre-cr-tests] wrote coverage: {OUTPUT}", file=sys.stderr, flush=True)
    return int(exit_code)


def build_pytest_args(arguments: list[str]) -> list[str]:
    if "--changed-only" not in arguments:
        return ["-q", *arguments]

    remaining = [argument for argument in arguments if argument != "--changed-only"]
    selected_tests = changed_test_paths()
    return ["-q", *remaining, *selected_tests]


def changed_test_paths() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ["tests/test_lcov_script.py"]

    staged_paths = [Path(line) for line in result.stdout.splitlines() if line.strip()]
    selected: set[str] = set()
    for path in staged_paths:
        if path.parts and path.parts[0] == "tests" and path.name.startswith("test_"):
            selected.add(path.as_posix())
            continue
        if not path.parts or path.parts[0] not in {
            "quality_runner",
            "quality_evidence_contract",
            "repo_quality_certifier",
        }:
            continue
        stem = path.stem
        for candidate in sorted((ROOT / "tests").glob(f"test_{stem}.py")):
            selected.add(candidate.relative_to(ROOT).as_posix())
        for candidate in sorted((ROOT / "tests").glob(f"test_*{stem}*.py")):
            selected.add(candidate.relative_to(ROOT).as_posix())

    return sorted(selected) or ["tests/test_lcov_script.py"]


def write_lcov(counts: dict[tuple[str, int], int]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    records: list[str] = []
    for source_file in sorted(PACKAGE_ROOT.rglob("*.py")):
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
