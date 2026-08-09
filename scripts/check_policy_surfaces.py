#!/usr/bin/env python3
"""Validate policy artifacts without misclassifying them as source code."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from quality_runner.policy_surfaces import validate_policy_surfaces

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--changed-files",
        default=None,
        help="Comma-separated changed paths; missing policy paths remain blocking evidence",
    )
    parser.add_argument("--json", action="store_true", help="Emit the machine-readable report")
    args = parser.parse_args()
    changed_files = (
        [item for item in args.changed_files.split(",") if item]
        if args.changed_files is not None
        else None
    )
    report = validate_policy_surfaces(args.root, paths=changed_files)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"policy surfaces: {report['status']}")
        for surface in report["surfaces"]:
            print(f"- {surface['path']}: {surface['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
