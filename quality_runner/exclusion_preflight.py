from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from quality_runner.config import CONFIG_FILE_NAME, load_repo_config
from quality_runner.exclusion_preflight_inventory import inventory_candidates
from quality_runner.exclusion_preflight_report import (
    packet_sha256,
    report_sha256,
    validate_exclusion_packet,
    validate_exclusion_report,
)
from quality_runner.exclusion_preflight_support import (
    CANDIDATE_SCAN_SECONDS_THRESHOLD,
    CANDIDATE_TEXT_FILE_THRESHOLD,
    EXCLUSION_PACKET_SCHEMA,
    EXCLUSION_REPORT_SCHEMA,
    EXCLUSION_RESULT_SCHEMA,
    MAX_CANDIDATES,
    dict_value,
    file_sha256,
    json_safe,
    path_has_symlink_component,
    positive_int,
    protected_path_reasons,
    relative_path_error,
    repository_fingerprint,
    string_list,
    unique_strings,
)
from quality_runner.scan_exclusions import (
    SCAN_EXCLUSION_MODULES,
    SCAN_EXCLUSION_SCOPE_ALL,
    SCAN_EXCLUSION_SCOPE_MODULE,
    ScanExclusionOverlay,
    effective_scan_exclusions_by_module,
    gitignore_scan_exclusions,
    normalize_scan_exclusion_module,
    scan_exclusion_overlay_parts,
)


def generated_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def build_exclusion_packet(repo_root: Path, run_id: str) -> dict[str, object]:
    root = repo_root.expanduser().resolve()
    config = load_repo_config(root)
    configured = string_list(config.get("scan_exclusions"))
    effective_by_module = effective_scan_exclusions_by_module(root, config)
    effective = effective_by_module["structural"]
    gitignore_patterns = gitignore_scan_exclusions(root)
    configured_by_module = {
        module: string_list(patterns)
        for module, patterns in dict_value(config.get("scan_exclusions_by_module")).items()
        if isinstance(module, str)
    }
    candidates, traversal = inventory_candidates(
        root,
        effective_exclusions=effective,
        gitignore_patterns=gitignore_patterns,
        config=config,
    )
    gate_timeouts = json_safe(config.get("gate_timeouts"))
    return {
        "schema": EXCLUSION_PACKET_SCHEMA,
        "run_id": run_id,
        "repo_root": str(root),
        "created_at": datetime.now(UTC).isoformat(),
        "repo_fingerprint": repository_fingerprint(root),
        "config": {
            "path": CONFIG_FILE_NAME if (root / CONFIG_FILE_NAME).is_file() else None,
            "sha256": file_sha256(root / CONFIG_FILE_NAME),
            "configured_scan_exclusions": configured,
            "configured_scan_exclusions_by_module": configured_by_module,
            "effective_scan_exclusions": effective,
            "effective_scan_exclusions_by_module": effective_by_module,
            "structural_scan": json_safe(config.get("structural_scan")),
            "gate_timeouts": gate_timeouts,
            "timeout_signals": {
                "structural_max_text_files": positive_int(
                    dict_value(config.get("structural_scan")).get("max_text_files")
                ),
                "configured_gate_timeouts": gate_timeouts,
            },
        },
        "preflight_policy": {
            "mode": "suggest-review-only",
            "candidate_limit": MAX_CANDIDATES,
            "candidate_text_file_threshold": CANDIDATE_TEXT_FILE_THRESHOLD,
            "candidate_scan_seconds_threshold": CANDIDATE_SCAN_SECONDS_THRESHOLD,
            "exclusion_scope": SCAN_EXCLUSION_SCOPE_ALL,
            "available_module_scopes": [SCAN_EXCLUSION_SCOPE_ALL, *SCAN_EXCLUSION_MODULES],
            "security_coverage": (
                "All-module exclusions affect security scanning. A structural or code_quality "
                "exclude can preserve security coverage; a security or all-module exclude "
                "requires explicit security_coverage_acknowledged=true."
            ),
            "protected_path_policy": "Protected source, security, and config roots cannot be excluded.",
        },
        "traversal": traversal,
        "candidates": candidates,
    }


def normalize_run_only_exclusion_paths(repo_root: Path, paths: list[str] | None) -> list[str]:
    root = repo_root.expanduser().resolve()
    normalized: list[str] = []
    for raw_value in paths or []:
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("--scan-exclusion values must be non-empty repo-relative paths")
        value = raw_value.strip()
        error = relative_path_error(value)
        if error is not None:
            raise ValueError(f"invalid run-only scan exclusion {raw_value!r}: {error}")
        protected_reasons = protected_path_reasons(value)
        if protected_reasons:
            raise ValueError(
                f"run-only scan exclusion cannot target protected path {value}: "
                + "; ".join(protected_reasons)
            )
        if path_has_symlink_component(root, value):
            raise ValueError(f"run-only scan exclusion cannot traverse a symlink: {value}")
        candidate_path = root / Path(*PurePosixPath(value).parts)
        try:
            resolved_candidate = candidate_path.resolve()
        except (OSError, RuntimeError) as error:
            raise ValueError(f"run-only scan exclusion cannot resolve path: {value}") from error
        if resolved_candidate == root or root not in resolved_candidate.parents:
            raise ValueError(f"run-only scan exclusion must stay inside the repository: {value}")
        if not candidate_path.is_dir() or candidate_path.is_symlink():
            raise ValueError(f"run-only scan exclusion is not a real directory: {value}")
        if value not in normalized:
            normalized.append(value)
    return normalized


def normalize_run_only_exclusion_overlay(
    repo_root: Path,
    paths: list[str] | None,
    module_values: list[str] | None,
) -> ScanExclusionOverlay | None:
    normalized_global = normalize_run_only_exclusion_paths(repo_root, paths)
    normalized_modules: dict[str, list[str]] = {}
    for raw_value in module_values or []:
        if not isinstance(raw_value, str) or "=" not in raw_value:
            raise ValueError("--scan-exclusion-module values must use MODULE=DIR syntax")
        raw_module, raw_path = raw_value.split("=", 1)
        module = normalize_scan_exclusion_module(raw_module)
        normalized_path = normalize_run_only_exclusion_paths(repo_root, [raw_path])
        if not normalized_path:
            raise ValueError(f"--scan-exclusion-module value has no directory: {raw_value!r}")
        module_paths = normalized_modules.setdefault(module, [])
        if normalized_path[0] not in module_paths:
            module_paths.append(normalized_path[0])
    if not normalized_global and not normalized_modules:
        return None
    if not normalized_modules:
        return normalized_global
    overlay: dict[str, list[str]] = {SCAN_EXCLUSION_SCOPE_ALL: normalized_global}
    overlay.update(normalized_modules)
    return overlay


def exclusion_patterns_for_paths(paths: list[str] | None) -> list[str]:
    return unique_strings([f"{path}/**" for path in paths or []])


def build_run_only_overlay(
    repo_root: Path,
    paths: ScanExclusionOverlay | None,
    *,
    config: dict[str, object],
) -> dict[str, object] | None:
    normalized_global, module_values = scan_exclusion_overlay_parts(paths)
    normalized = normalize_run_only_exclusion_paths(repo_root, normalized_global)
    normalized_modules = {
        module: normalize_run_only_exclusion_paths(repo_root, values)
        for module, values in module_values.items()
    }
    normalized_modules = {module: values for module, values in normalized_modules.items() if values}
    if not normalized and not normalized_modules:
        return None
    root = repo_root.expanduser().resolve()
    overlay_patterns = exclusion_patterns_for_paths(normalized)
    overlay_patterns_by_module = {
        module: exclusion_patterns_for_paths(values)
        for module, values in normalized_modules.items()
    }
    config_path = root / CONFIG_FILE_NAME
    base_config = load_repo_config(root) if config_path.is_file() else dict(config)
    configured = string_list(base_config.get("scan_exclusions"))
    base_config["scan_exclusions"] = configured
    configured_by_module = {
        module: string_list(values)
        for module, values in dict_value(base_config.get("scan_exclusions_by_module")).items()
        if isinstance(module, str)
    }
    base_config["scan_exclusions_by_module"] = configured_by_module
    if overlay_patterns:
        base_config["scan_exclusions"] = unique_strings([*configured, *overlay_patterns])
    for module, patterns in overlay_patterns_by_module.items():
        configured_by_module[module] = unique_strings(
            [*configured_by_module.get(module, []), *patterns]
        )
    effective_by_module = effective_scan_exclusions_by_module(root, base_config)
    scope = SCAN_EXCLUSION_SCOPE_MODULE if normalized_modules else SCAN_EXCLUSION_SCOPE_ALL
    security_reduced = bool(overlay_patterns or overlay_patterns_by_module.get("security"))
    return {
        "source": "cli-run-only-overlay",
        "scope": scope,
        "security_coverage": (
            "Security scanning is reduced for the globally or security-scoped excluded paths."
            if security_reduced
            else "Structural and code_quality exclusions preserve security scanning coverage."
        ),
        "requested_paths": normalized,
        "requested_paths_by_module": normalized_modules,
        "effective_exclusion_patterns": overlay_patterns,
        "effective_exclusion_patterns_by_module": overlay_patterns_by_module,
        "effective_scan_exclusions": effective_by_module["structural"],
        "effective_scan_exclusions_by_module": effective_by_module,
        "config_sha256": file_sha256(root / CONFIG_FILE_NAME),
        "config_mutated": False,
        "configured_scan_exclusions": configured,
        "configured_scan_exclusions_by_module": configured_by_module,
    }


from quality_runner.exclusion_preflight_command import (  # noqa: E402
    render_exclusion_packet_markdown,
    run_exclusion_preflight_command,
)

__all__ = [
    "EXCLUSION_PACKET_SCHEMA",
    "EXCLUSION_REPORT_SCHEMA",
    "EXCLUSION_RESULT_SCHEMA",
    "build_exclusion_packet",
    "build_run_only_overlay",
    "exclusion_patterns_for_paths",
    "generated_run_id",
    "normalize_run_only_exclusion_paths",
    "normalize_run_only_exclusion_overlay",
    "packet_sha256",
    "render_exclusion_packet_markdown",
    "report_sha256",
    "run_exclusion_preflight_command",
    "validate_exclusion_packet",
    "validate_exclusion_report",
]
