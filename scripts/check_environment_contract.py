#!/usr/bin/env python3
"""Validate Quality Runner's routed, evidence-first environment contract."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

PACKETS = (
    "architecture.md",
    "commands.md",
    "conventions.md",
    "security.md",
    "failure-modes.md",
    "examples.md",
    "done.md",
    "deployment.md",
)
REQUIRED_FILES = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    ".pre-cr.json",
    ".tracker/PROJECT_TRUTH.md",
    ".github/workflows/ci.yml",
)
LINK_RE = re.compile(r"\[[^]]+\]\(([^)]+)\)")
REVIEW_RE = re.compile(r"last_reviewed:\s*(\d{4}-\d{2}-\d{2})")
SECRET_MARKERS = (".env", ".pem", ".key", ".p12", ".pfx", "id_rsa", "credentials")
SAFE_EXAMPLES = {".env.example", ".env.template"}


def _relative_links(text: str) -> list[str]:
    links: list[str] = []
    for value in LINK_RE.findall(text):
        target = value.split("#", 1)[0].split("?", 1)[0].strip()
        if target and not target.startswith(("http://", "https://", "/")):
            links.append(target)
    return links


def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def check_secret_paths(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        name = Path(path).name.lower()
        if name in SAFE_EXAMPLES:
            continue
        if any(marker in name for marker in SECRET_MARKERS):
            findings.append(path)
    return findings


def _load_toml(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        errors.append(f"invalid {label}: {error}")
        return {}
    return value if isinstance(value, dict) else {}


def _check_links(root: Path, relative_path: str, errors: list[str]) -> int:
    path = root / relative_path
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8")
    count = 0
    root_resolved = root.resolve()
    for link in _relative_links(text):
        target = (path.parent / link).resolve()
        if root_resolved not in target.parents or not target.is_file():
            errors.append(f"broken context link in {relative_path}: {link}")
        count += 1
    return count


def _check_metadata(root: Path, errors: list[str]) -> dict[str, object]:
    pyproject = _load_toml(root / "pyproject.toml", "pyproject.toml", errors)
    project = pyproject.get("project", {})
    scripts = project.get("scripts", {}) if isinstance(project, dict) else {}
    if not isinstance(scripts, dict) or "quality-runner" not in scripts or "qr" not in scripts:
        errors.append("pyproject.toml must expose both quality-runner and qr console scripts")
    basedpyright = pyproject.get("tool", {}).get("basedpyright", {})
    checking_mode = basedpyright.get("typeCheckingMode") if isinstance(basedpyright, dict) else None
    if checking_mode not in {"standard", "strict"}:
        errors.append("basedpyright typeCheckingMode must be explicitly standard or strict")

    pre_cr_path = root / ".pre-cr.json"
    try:
        pre_cr = json.loads(pre_cr_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid .pre-cr.json: {error}")
        pre_cr = {}
    adapters = pre_cr.get("qualityAdapters", []) if isinstance(pre_cr, dict) else []
    environment_adapter = next(
        (
            adapter
            for adapter in adapters
            if isinstance(adapter, dict) and adapter.get("name") == "environment-contract"
        ),
        None,
    )
    if not isinstance(environment_adapter, dict) or environment_adapter.get("required") is not True:
        errors.append("required environment-contract pre-CR adapter is missing")
    expected_command = "python3 scripts/check_environment_contract.py"
    if (
        isinstance(environment_adapter, dict)
        and environment_adapter.get("command") != expected_command
    ):
        errors.append("environment-contract pre-CR adapter command is not canonical")

    workflow = root / ".github/workflows/ci.yml"
    workflow_text = workflow.read_text(encoding="utf-8") if workflow.is_file() else ""
    if "scripts/check_environment_contract.py" not in workflow_text:
        errors.append("CI must execute scripts/check_environment_contract.py")
    return {
        "basedpyright_mode": checking_mode,
        "required_pre_cr_adapter": isinstance(environment_adapter, dict)
        and environment_adapter.get("required") is True,
        "ci_environment_contract": "scripts/check_environment_contract.py" in workflow_text,
    }


def validate(
    root: Path,
    as_of: date,
    tracked_paths: list[str] | None = None,
) -> dict[str, object]:
    root = root.expanduser().resolve()
    errors: list[str] = []
    missing_files = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    errors.extend(f"missing required surface: {path}" for path in missing_files)

    router = root / "AGENTS.md"
    index = root / ".agents" / "context" / "README.md"
    if not router.is_file():
        errors.append("missing AGENTS.md")
    if not index.is_file():
        errors.append("missing .agents/context/README.md")
    link_count = 0
    if index.is_file():
        index_text = index.read_text(encoding="utf-8")
        reviewed = REVIEW_RE.search(index_text)
        if reviewed is None:
            errors.append("context index is missing last_reviewed")
        else:
            reviewed_date = date.fromisoformat(reviewed.group(1))
            if (as_of - reviewed_date).days > 35:
                errors.append(f"context index is stale: {reviewed_date.isoformat()}")
        for marker in ("minimum context", "do not recursively", "current truth"):
            if marker not in index_text.lower():
                errors.append(f"context index is missing routing marker: {marker}")
        link_count += _check_links(root, ".agents/context/README.md", errors)
    if router.is_file():
        router_text = router.read_text(encoding="utf-8").lower()
        for marker in ("approval", "credential", "remote", "target"):
            if marker not in router_text:
                errors.append(f"AGENTS.md is missing safety marker: {marker}")
        link_count += _check_links(root, "AGENTS.md", errors)

    missing_packets = [packet for packet in PACKETS if not (index.parent / packet).is_file()]
    errors.extend(f"missing context packet: {packet}" for packet in missing_packets)
    for packet in PACKETS:
        relative_path = f".agents/context/{packet}"
        if (root / relative_path).is_file():
            link_count += _check_links(root, relative_path, errors)

    metadata = _check_metadata(root, errors)
    paths = tracked_paths if tracked_paths is not None else _tracked_paths(root)
    secret_paths = check_secret_paths(paths)
    errors.extend(f"secret-like tracked path: {path}" for path in secret_paths)
    return {
        "schema_version": "environment-contract/v1",
        "as_of": as_of.isoformat(),
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "checks": {
            "required_files": len(REQUIRED_FILES) - len(missing_files),
            "required_files_total": len(REQUIRED_FILES),
            "context_packets": len(PACKETS) - len(missing_packets),
            "context_packets_required": len(PACKETS),
            "context_links": link_count,
            "tracked_secret_paths": len(secret_paths),
            **metadata,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    result = validate(args.root, args.as_of)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
