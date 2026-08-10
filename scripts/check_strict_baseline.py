#!/usr/bin/env python3
"""Run the occurrence-aware BasedPyright strict ratchet.

The certified repository type gate remains ``uv run --locked basedpyright`` in
standard mode. This command is the evidence-producing strict burndown lane:
legacy diagnostics are explicitly blocked, while new diagnostics fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quality_runner.strict_baseline import build_baseline, compare_baseline  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("docs/baselines/basedpyright-strict.json"),
    )
    parser.add_argument("--config", type=Path, default=Path("pyrightconfig.strict.json"))
    parser.add_argument("--baseline-ref", help="repository ref represented by the baseline")
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
        current = build_baseline(
            payload,
            root=root,
            baseline_ref=args.baseline_ref or _git_ref(root),
            config_path=str(config.relative_to(root)),
            config_sha256=_sha256(config),
            repository=_repository_identity(root),
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"blocked: unable to produce strict scan evidence: {error}", file=sys.stderr)
        return 3

    if args.update:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        current["baseline_reason"] = args.reason
        baseline_path.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        state = "blocked" if current["occurrences"] else "passed"
        print(
            f"updated {baseline_path.relative_to(root)}: "
            f"state={state} legacy={len(current['occurrences'])}"
        )
        return 0

    try:
        existing_value = json.loads(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(existing_value, dict):
            raise ValueError("baseline must be a JSON object")
        existing = existing_value
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"blocked: unable to read strict baseline: {error}", file=sys.stderr)
        return 3

    delta = compare_baseline(
        existing,
        current,
        expected_config_sha256=_sha256(config),
        expected_tool_version=str(current.get("tool_version") or ""),
    )
    print(
        "strict baseline: "
        f"state={delta['state']} "
        f"new={len(delta['new'])} "
        f"legacy={delta['legacy_count']} "
        f"resolved={len(delta['resolved'])} "
        f"unknown={len(delta['unknown'])}"
    )
    for blocker in delta["blockers"]:
        print(f"blocked: {blocker}", file=sys.stderr)
    if delta["blockers"] or delta["unknown"]:
        return 3
    if delta["new"]:
        print("failed: new strict diagnostics are not allowed", file=sys.stderr)
        return 1
    if delta["legacy_count"]:
        print(
            f"blocked: {delta['legacy_count']} legacy strict diagnostics remain",
            file=sys.stderr,
        )
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
