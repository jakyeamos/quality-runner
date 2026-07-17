from __future__ import annotations

import difflib
import json
import re
import tomllib
from pathlib import Path
from typing import cast

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.config import CONFIG_FILE_NAME, load_repo_config
from quality_runner.exclusion_preflight_report import packet_sha256, report_sha256
from quality_runner.exclusion_preflight_support import (
    EXCLUSION_RESULT_SCHEMA,
    file_sha256,
    markdown_cell,
    object_list,
    object_value,
    string_list,
    unique_strings,
)
from quality_runner.manifest import build_run_manifest
from quality_runner.scan_exclusions import (
    SCAN_EXCLUSION_SCOPE_ALL,
    effective_scan_exclusions_by_module,
    gitignore_scan_exclusions,
    resolve_scan_exclusions,
)


def run_exclusion_preflight_command(
    repo_root: Path,
    *,
    action: str,
    run_id: str | None = None,
    packet_path: Path | None = None,
    report_path: Path | None = None,
    apply: bool = False,
) -> dict[str, object]:
    from quality_runner.exclusion_preflight import (
        build_exclusion_packet,
        generated_run_id,
        validate_exclusion_report,
    )

    if action not in {"suggest", "validate", "apply"}:
        raise ValueError(f"unsupported exclusion preflight action: {action}")
    if action in {"validate", "apply"} and (packet_path is None or report_path is None):
        raise ValueError(f"exclusions {action} requires --packet and --report")
    if action == "apply" and not apply:
        raise ValueError("exclusions apply is a mutation and requires explicit --apply")

    root = repo_root.expanduser().resolve()
    resolved_run_id = generated_run_id() if run_id is None else run_id
    run_dir = prepare_artifact_dir(root, resolved_run_id)
    packet: dict[str, object]
    report: dict[str, object] | None = None
    validation: dict[str, object] | None = None
    if action == "suggest":
        packet = build_exclusion_packet(root, resolved_run_id)
    else:
        packet_value = load_json(packet_path)
        packet = cast(dict[str, object], packet_value) if isinstance(packet_value, dict) else {}
        report_value = load_json(report_path)
        report = cast(dict[str, object], report_value) if isinstance(report_value, dict) else None
        validation = validate_exclusion_report(packet_value, report_value, repo_root=root)

    artifact_paths: dict[str, str] = {
        "scan_exclusion_preflight_packet_json": str(
            write_json(run_dir / "scan-exclusion-preflight-packet.json", packet)
        ),
        "scan_exclusion_preflight_packet_md": str(
            write_text(
                run_dir / "scan-exclusion-preflight-packet.md",
                render_exclusion_packet_markdown(packet),
            )
        ),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
    }
    if report is not None:
        artifact_paths["scan_exclusion_preflight_report_json"] = str(
            write_json(run_dir / "scan-exclusion-preflight-report.json", report)
        )

    config_result: dict[str, object] = {
        "path": str(root / CONFIG_FILE_NAME),
        "before_sha256": file_sha256(root / CONFIG_FILE_NAME),
        "after_sha256": file_sha256(root / CONFIG_FILE_NAME),
        "changed": False,
        "diff": "",
    }
    approved_patterns: list[str] = []
    approved_patterns_by_module: dict[str, list[str]] = {}
    rejected_decisions: list[dict[str, object]] = []
    if action == "suggest":
        status = "suggested"
        candidates = packet.get("candidates")
        decision_summary: dict[str, object] = {
            "exclude": 0,
            "include": 0,
            "defer": 0,
            "pending_review": len(candidates) if isinstance(candidates, list) else 0,
        }
    else:
        assert validation is not None
        passed = validation.get("passed") is True
        approved_patterns = string_list(validation.get("approved_patterns"))
        approved_patterns_by_module = {
            module: string_list(patterns)
            for module, patterns in object_value(
                validation.get("approved_patterns_by_module")
            ).items()
            if isinstance(module, str)
        }
        rejected_decisions = object_list(validation.get("rejected_decisions"))
        decision_summary = object_value(validation.get("decision_counts"))
        if not passed:
            status = "rejected"
            approved_patterns = []
            approved_patterns_by_module = {}
        elif action == "apply":
            config_result = apply_config_exclusions(
                root,
                approved_patterns,
                approved_patterns_by_module,
            )
            status = "applied"
        else:
            status = "validated"

    effective_by_module = effective_scan_exclusions_by_module(root, load_repo_config(root))
    effective_exclusions = effective_by_module[SCAN_EXCLUSION_SCOPE_ALL]
    report_scope_value = report.get("scope") if isinstance(report, dict) else None
    report_scope = (
        report_scope_value
        if report_scope_value in {SCAN_EXCLUSION_SCOPE_ALL, "module-scoped"}
        else SCAN_EXCLUSION_SCOPE_ALL
    )
    security_reduced = any(
        scope in {SCAN_EXCLUSION_SCOPE_ALL, "security"}
        for scope, patterns in approved_patterns_by_module.items()
        if patterns
    )
    result: dict[str, object] = {
        "schema": EXCLUSION_RESULT_SCHEMA,
        "status": status,
        "implementation_allowed": False,
        "config_mutation_requested": action == "apply",
        "config_mutation_applied": config_result.get("changed") is True,
        "stage": action,
        "run_id": resolved_run_id,
        "repo_root": str(root),
        "packet_sha256": packet_sha256(packet),
        "report_sha256": report_sha256(report) if report is not None else None,
        "decision_summary": decision_summary,
        "approved_exclusions": approved_patterns,
        "approved_exclusions_by_module": approved_patterns_by_module,
        "rejected_decisions": rejected_decisions,
        "config": config_result,
        "effective_scan_exclusions": effective_exclusions,
        "effective_scan_exclusions_by_module": effective_by_module,
        "artifact_paths": artifact_paths,
    }
    if validation is not None:
        result["validation"] = validation
    result_path = run_dir / "scan-exclusion-preflight-result.json"
    artifact_paths["scan_exclusion_preflight_result_json"] = str(result_path)
    write_json(result_path, result)
    metadata: dict[str, object] = {
        "stage": action,
        "packet_json": artifact_paths["scan_exclusion_preflight_packet_json"],
        "report_json": artifact_paths.get("scan_exclusion_preflight_report_json"),
        "result_json": artifact_paths["scan_exclusion_preflight_result_json"],
        "packet_sha256": result["packet_sha256"],
        "report_sha256": result["report_sha256"],
        "approved_exclusions": approved_patterns,
        "approved_exclusions_by_module": approved_patterns_by_module,
        "rejected_decisions": rejected_decisions,
        "effective_scan_exclusions": effective_exclusions,
        "effective_scan_exclusions_by_module": effective_by_module,
        "config": config_result,
        "scope": report_scope,
        "security_coverage": (
            "explicit-scope-reduces-security-coverage"
            if security_reduced
            else "security-coverage-preserved"
        ),
    }
    manifest = build_run_manifest(
        repo_root=root,
        run_id=resolved_run_id,
        mode="exclusion-preflight",
        artifact_paths=artifact_paths,
        scan_exclusion_preflight=metadata,
    )
    artifact_paths["run_manifest_json"] = str(write_json(run_dir / "run-manifest.json", manifest))
    return result


def render_exclusion_packet_markdown(packet: dict[str, object]) -> str:
    policy = object_value(packet.get("preflight_policy"))
    available_scopes = policy.get("available_module_scopes")
    scope_text = (
        ", ".join(str(item) for item in available_scopes)
        if isinstance(available_scopes, list)
        else "all-modules"
    )
    lines = [
        "# Quality Runner Scan-Exclusion Preflight",
        "",
        f"- Schema: `{packet.get('schema')}`",
        f"- Repository: `{packet.get('repo_root')}`",
        f"- Run: `{packet.get('run_id')}`",
        "- Mode: deterministic candidate inventory; review-only",
        f"- Available scopes: `{scope_text}`",
        "",
        "Review every candidate and write a report with one decision per candidate.",
        "Use `exclude`, `include`, or `defer`; all-modules and security excludes must acknowledge their security coverage impact. Structural and code_quality excludes can preserve security coverage.",
        "",
        "| Candidate | Proposed scope | Suggested decision | Confidence | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for candidate in object_list(packet.get("candidates")):
        path = str(candidate.get("path", ""))
        scope = object_value(candidate.get("proposed_scope"))
        evidence = object_value(candidate.get("evidence"))
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(f"{candidate.get('candidate_id')} `{path}`"),
                    markdown_cell(
                        f"{scope.get('module_scope', 'all-modules')}: {scope.get('pattern', '')}"
                    ),
                    markdown_cell(str(candidate.get("suggested_decision", "defer"))),
                    markdown_cell(str(candidate.get("confidence", "low"))),
                    markdown_cell(
                        f"{evidence.get('file_count', 0)} files; "
                        f"{evidence.get('estimated_text_files', 0)} text; "
                        f"~{evidence.get('estimated_scan_seconds', 0)}s"
                    ),
                ]
            )
        )
    if not object_list(packet.get("candidates")):
        lines.append("| — | — | none | — | No review candidates were found. |")
    return "\n".join(lines) + "\n"


def apply_config_exclusions(
    repo_root: Path,
    patterns: list[str],
    patterns_by_module: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    root = repo_root.expanduser().resolve()
    config_path = root / CONFIG_FILE_NAME
    before = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    before_sha = file_sha256(config_path)
    if config_path.exists():
        try:
            parsed = tomllib.loads(before)
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"cannot apply exclusions to invalid TOML config: {error}") from error
        section = parsed.get("quality_runner")
        existing = string_list(section.get("scan_exclusions")) if isinstance(section, dict) else []
        existing_by_module = (
            {
                module: string_list(values)
                for module, values in section.get("scan_exclusions_by_module", {}).items()
                if isinstance(module, str)
            }
            if isinstance(section, dict)
            and isinstance(section.get("scan_exclusions_by_module"), dict)
            else {}
        )
    else:
        existing = []
        existing_by_module = {}
    merged = unique_strings([*existing, *patterns])
    merged_by_module = dict(existing_by_module)
    for module, module_patterns in (patterns_by_module or {}).items():
        if module == SCAN_EXCLUSION_SCOPE_ALL:
            continue
        merged_by_module[module] = unique_strings(
            [*merged_by_module.get(module, []), *module_patterns]
        )
    after = (
        render_config_with_exclusions(
            before,
            merged,
            module_exclusions=merged_by_module if patterns_by_module and merged_by_module else None,
        )
        if (before or merged or merged_by_module)
        else before
    )
    changed = before != after
    if changed:
        config_path.write_text(after, encoding="utf-8")
    after_sha = file_sha256(config_path)
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{CONFIG_FILE_NAME}",
            tofile=f"b/{CONFIG_FILE_NAME}",
            lineterm="",
        )
    )
    return {
        "path": str(config_path),
        "before_sha256": before_sha,
        "after_sha256": after_sha,
        "changed": changed,
        "diff": f"{diff}\n" if diff else "",
        "scan_exclusions": merged,
        "scan_exclusions_by_module": merged_by_module,
    }


def render_config_with_exclusions(
    before: str,
    exclusions: list[str],
    *,
    module_exclusions: dict[str, list[str]] | None = None,
) -> str:
    assignment = f"scan_exclusions = {json.dumps(exclusions, separators=(', ', ': '))}"
    if not before:
        lines = ["[quality_runner]\n", f"{assignment}\n"]
        return _render_module_exclusions(lines, module_exclusions)
    lines = before.splitlines(keepends=True)
    section_start = next(
        (index for index, line in enumerate(lines) if line.strip() == "[quality_runner]"),
        None,
    )
    if section_start is None:
        return before.rstrip("\n") + f"\n\n[quality_runner]\n{assignment}\n"
    section_end = len(lines)
    for index in range(section_start + 1, len(lines)):
        if re.match(r"^\s*\[", lines[index]):
            section_end = index
            break
    key_indices = [
        index
        for index in range(section_start + 1, section_end)
        if re.match(r"^\s*scan_exclusions\s*=", lines[index])
    ]
    if len(key_indices) > 1:
        raise ValueError(f"{CONFIG_FILE_NAME} contains duplicate scan_exclusions keys")
    if key_indices:
        index = key_indices[0]
        if "]" not in lines[index].split("=", 1)[1]:
            raise ValueError(
                f"{CONFIG_FILE_NAME} uses a multiline scan_exclusions value; apply it manually"
            )
        lines[index] = assignment + "\n"
    else:
        lines.insert(section_start + 1, assignment + "\n")
    return _render_module_exclusions(lines, module_exclusions)


def _render_module_exclusions(
    lines: list[str],
    module_exclusions: dict[str, list[str]] | None,
) -> str:
    if not module_exclusions:
        return "".join(lines)
    assignments = [
        f"{module} = {json.dumps(module_exclusions[module], separators=(', ', ': '))}\n"
        for module in sorted(module_exclusions)
        if module_exclusions[module]
    ]
    if not assignments:
        return "".join(lines)
    header_pattern = r"^\s*\[quality_runner\.scan_exclusions_by_module\]\s*$"
    section_start = next(
        (index for index, line in enumerate(lines) if re.match(header_pattern, line.strip())),
        None,
    )
    replacement = ["[quality_runner.scan_exclusions_by_module]\n", *assignments]
    if section_start is not None:
        section_end = len(lines)
        for index in range(section_start + 1, len(lines)):
            if re.match(r"^\s*\[", lines[index]):
                section_end = index
                break
        lines[section_start:section_end] = replacement
        return "".join(lines)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    if lines and lines[-1].strip():
        lines.append("\n")
    lines.extend(replacement)
    return "".join(lines)


def effective_exclusions_for(root: Path) -> list[str]:
    config = load_repo_config(root)
    return unique_strings([*resolve_scan_exclusions(config), *gitignore_scan_exclusions(root)])


def load_json(path: Path | None) -> object:
    if path is None:
        raise ValueError("JSON path is required")
    resolved = path.expanduser().resolve()
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"JSON file does not exist: {resolved}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {resolved}: {error}") from error
