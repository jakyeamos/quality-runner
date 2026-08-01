from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from quality_runner import __version__
from quality_runner.artifacts import (
    existing_artifact_dir,
    prepare_artifact_dir,
    safe_child_file,
    write_json,
)
from quality_runner.config import load_repo_config
from quality_runner.scan_exclusions import (
    ALWAYS_EXCLUDED_PATH_PARTS,
    effective_scan_exclusions_by_module,
    matches_scan_exclusion,
    scan_exclusion_contract,
)


def load_gate_execution_plan(repo_root: Path, run_id: str) -> list[object] | None:
    root = repo_root.expanduser().resolve()
    try:
        run_dir = existing_artifact_dir(root, run_id)
        path = safe_child_file(run_dir, "gate-execution-plan.json", require_exists=True)
    except (FileNotFoundError, OSError, ValueError):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, list) else None


def build_timeout_identity(
    repo_root: Path,
    *,
    profile: str | None,
    gate_plan: object | None = None,
) -> dict[str, object]:
    root = repo_root.expanduser().resolve()
    config = load_repo_config(root)
    exclusion_contract = scan_exclusion_contract(root, config)
    effective_by_module = effective_scan_exclusions_by_module(root, config)
    static_payload: dict[str, object] = {
        "repo_root": str(root),
        "quality_runner_version": __version__,
        "profile": profile or "default",
        "config_sha256": file_sha256(root / ".quality-runner.toml"),
        "gitignore_sha256": exclusion_contract["gitignore_sha256"],
        "scan_exclusion_fingerprint": exclusion_contract["fingerprint"],
        "effective_scan_exclusions_by_module": effective_by_module,
        "scan_policy": json_safe(
            {
                "structural_scan": config.get("structural_scan"),
                "gate_timeouts": config.get("gate_timeouts"),
                "required_capabilities": config.get("required_capabilities"),
                "gates": config.get("gates"),
            }
        ),
        "included_file_inventory": included_file_inventory(
            root,
            effective_by_module.get("all-modules", []),
        ),
        "exclusion_preflight": exclusion_preflight_status(
            root,
            config=config,
            effective_by_module=effective_by_module,
        ),
    }
    gate_plan_sha256 = canonical_sha256(gate_plan) if gate_plan is not None else None
    full_payload = {
        "static": static_payload,
        "gate_plan_sha256": gate_plan_sha256,
    }
    return {
        "static": static_payload,
        "static_sha256": canonical_sha256(static_payload),
        "gate_plan_sha256": gate_plan_sha256,
        "sha256": canonical_sha256(full_payload),
    }


def exclusion_preflight_status(
    repo_root: Path,
    *,
    config: Mapping[str, object],
    effective_by_module: Mapping[str, object],
) -> dict[str, object]:
    configured_global = string_list(config.get("scan_exclusions"))
    configured_by_module = mapping(config.get("scan_exclusions_by_module"))
    custom_configured = bool(configured_global) or any(
        bool(string_list(values)) for values in configured_by_module.values()
    )
    if not custom_configured:
        return {"required": False, "status": "not-required"}

    expected_effective = json_safe(effective_by_module)
    security_reduced = bool(configured_global) or bool(
        string_list(configured_by_module.get("security"))
    )
    current_contract = scan_exclusion_contract(repo_root, dict(config))
    runs_dir = repo_root.expanduser().resolve() / ".quality-runner" / "runs"
    for run_dir in run_directories_by_mtime(runs_dir):
        result = read_json(run_dir / "scan-exclusion-preflight-result.json")
        if result is None or result.get("status") not in {"validated", "applied"}:
            continue
        if canonical_sha256(result.get("effective_scan_exclusions_by_module")) != canonical_sha256(
            expected_effective
        ):
            continue
        result_config = mapping(result.get("config"))
        if result_config.get("scan_exclusion_fingerprint") != current_contract.get("fingerprint"):
            continue
        if security_reduced and not report_acknowledges_security(repo_root, run_dir, result):
            continue
        return {
            "required": True,
            "status": "validated",
            "run_id": result.get("run_id"),
            "security_reduced": security_reduced,
        }
    return {
        "required": True,
        "status": "required-unvalidated",
        "security_reduced": security_reduced,
    }


def canonical_sha256(value: object) -> str:
    content = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def included_file_inventory(root: Path, exclusions: object) -> dict[str, object]:
    patterns = string_list(exclusions)
    entries: list[dict[str, object]] = []
    for current_root, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current_root)
        relative_current = relative_path(root, current_path)
        dir_names[:] = [
            name
            for name in sorted(dir_names)
            if not (current_path / name).is_symlink()
            and not is_excluded(join_path(relative_current, name), patterns)
        ]
        for file_name in sorted(file_names):
            path = current_path / file_name
            relative = join_path(relative_current, file_name)
            if path.is_symlink() or not path.is_file() or is_excluded(relative, patterns):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            entries.append({"path": relative, "size": size})
    return {
        "file_count": len(entries),
        "total_bytes": sum(numeric_int(item.get("size")) for item in entries),
        "sha256": canonical_sha256(entries),
    }


def is_excluded(relative: str, patterns: list[str]) -> bool:
    if not relative:
        return False
    parts = PurePosixPath(relative).parts
    return any(part in ALWAYS_EXCLUDED_PATH_PARTS for part in parts) or matches_scan_exclusion(
        relative, patterns
    )


def join_path(parent: str, child: str) -> str:
    return f"{parent}/{child}" if parent else child


def relative_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    return relative.as_posix() if relative.parts else ""


def file_sha256(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def run_directories_by_mtime(runs_dir: Path) -> list[Path]:
    if runs_dir.is_symlink() or not runs_dir.is_dir():
        return []
    values: list[tuple[float, Path]] = []
    for path in runs_dir.iterdir():
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            values.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return [path for _mtime, path in sorted(values, reverse=True)]


def report_acknowledges_security(
    root: Path,
    run_dir: Path,
    result: Mapping[str, object],
) -> bool:
    artifact_paths = mapping(result.get("artifact_paths"))
    report_value = artifact_paths.get("scan_exclusion_preflight_report_json")
    report_path = safe_child_path(root, run_dir, report_value)
    report = read_json(report_path) if report_path is not None else None
    return report is not None and report.get("security_coverage_acknowledged") is True


def safe_child_path(root: Path, run_dir: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return run_dir / "scan-exclusion-preflight-report.json"
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = run_dir / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def read_json(path: Path | None) -> dict[str, object] | None:
    if path is None or path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_run_baseline_artifact(
    root: Path,
    run_id_prefix: str,
    baseline: Mapping[str, object],
) -> str | None:
    run_id = f"{run_id_prefix}-verify"
    try:
        run_dir = prepare_artifact_dir(root, run_id)
        return str(write_json(run_dir / "timeout-baseline.json", dict(baseline)))
    except (OSError, ValueError):
        return None


def mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def list_value(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def positive_int(value: object) -> int:
    return value if isinstance(value, int) and value > 0 else 0


def numeric_float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def numeric_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return str(value)
