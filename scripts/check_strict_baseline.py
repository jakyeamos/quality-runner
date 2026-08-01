#!/usr/bin/env python3
"""Run the advisory BasedPyright strict ratchet.

The repository's certified type gate remains ``uv run --locked basedpyright``
in standard mode.  This command is the evidence-producing burndown lane.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from quality_runner.strict_baseline import build_baseline, compare_baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("docs/baselines/basedpyright-strict.json"),
    )
    parser.add_argument("--config", type=Path, default=Path("pyrightconfig.strict.json"))
    parser.add_argument(
        "--update", action="store_true", help="write the current scan as the baseline"
    )
    parser.add_argument("--reason", help="why the baseline is being created or replaced")
    args = parser.parse_args(argv)

    if args.update and not args.reason:
        parser.error("--update requires --reason")

    root = args.root.resolve()
    config = (root / args.config).resolve()
    baseline_path = (root / args.baseline).resolve()
    if not config.is_file():
        print(f"blocked: strict config not found: {config}", file=sys.stderr)
        return 3
    command = shutil.which("basedpyright")
    if command is None:
        print("blocked: basedpyright is not available on PATH", file=sys.stderr)
        return 3

    try:
        result = subprocess.run(
            [command, "--project", str(config), "--outputjson"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(result.stdout)
        baseline = build_baseline(
            payload,
            root=root,
            baseline_ref=_git_ref(root),
            config_path=str(config.relative_to(root)),
            config_sha256=_sha256(config),
            repository=_repository_identity(root),
            baseline_reason=args.reason,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"blocked: unable to produce strict scan evidence: {error}", file=sys.stderr)
        return 3

    if args.update:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            f"updated {baseline_path.relative_to(root)}: {len(baseline['occurrences'])} occurrences"
        )
        return 0

    try:
        existing = json.loads(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise ValueError("baseline must be a JSON object")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"blocked: unable to read strict baseline: {error}", file=sys.stderr)
        return 3

    delta = compare_baseline(
        existing,
        baseline,
        expected_config_sha256=_sha256(config),
        expected_tool_version=str(baseline.get("tool_version") or ""),
    )
    print(
        "strict baseline: "
        f"new={len(delta['new'])} "
        f"persisted={len(delta['persisted'])} "
        f"resolved={len(delta['resolved'])} "
        f"unknown={len(delta['unknown'])}"
    )
    for blocker in delta["blockers"]:
        print(f"blocked: {blocker}", file=sys.stderr)
    if delta["blockers"] or delta["unknown"]:
        return 3
    if delta["new"]:
        return 1
    return 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_ref(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "workspace"
    return result.stdout.strip() or "workspace"


def _repository_identity(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return root.name
    remote = result.stdout.strip().removesuffix(".git")
    return remote.rsplit("/", 1)[-1].rsplit(":", 1)[-1] or root.name


if __name__ == "__main__":
    raise SystemExit(main())
