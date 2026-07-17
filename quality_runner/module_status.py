from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

MODULE_STATUS_SCHEMA = "quality-runner-module-status-v0.1"
MODULE_STATUS_VALUES = frozenset(
    {"enabled", "disabled", "not_applicable", "unavailable", "not_run"}
)


def build_module_status(
    *,
    mode: str,
    profile: str,
    repo_scan: dict[str, Any],
    code_quality_scan: dict[str, Any] | None = None,
    capability_map: dict[str, Any] | None = None,
    standards_packet: dict[str, Any] | None = None,
    security_scan: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality_summary = _summary(code_quality_scan)
    ui_file_count = _ui_file_count(code_quality_scan)
    ui_quality_status = _ui_quality_status(quality_summary, ui_file_count)
    modules = [
        _module(
            "repository-discovery",
            "core",
            "enabled" if repo_scan else "not_run",
            "Repository facts and scan boundaries are captured for every workflow run.",
        ),
        _module(
            "evidence-provenance",
            "core",
            "enabled" if isinstance(repo_scan.get("provenance"), dict) else "unavailable",
            "Git and workflow provenance is attached to the repository scan.",
        ),
        _module(
            "structural-quality",
            "core",
            "enabled" if code_quality_scan is not None else "not_run",
            "Deterministic structural findings are included in the code-quality scan.",
            finding_count=_int_value(quality_summary.get("total_findings")),
        ),
        _module(
            "capability-detection",
            "core",
            "enabled" if capability_map is not None else "not_run",
            "Repo-owned quality gates are detected and classified.",
        ),
        _module(
            "remediation-handoff",
            "core",
            "enabled" if mode in {"run", "verify-gates", "refresh"} else "not_run",
            "The workflow emits a consumer-neutral handoff when the selected mode plans work.",
        ),
        _module(
            "read-only-safety",
            "core",
            "enabled",
            "QR remains advisory and does not apply source changes.",
        ),
        _module(
            "similarity",
            "core",
            _similarity_status(quality_summary),
            _similarity_summary(quality_summary),
            finding_count=_int_value(quality_summary.get("semantic_similarity_clusters")),
        ),
        _module(
            "ui-quality",
            "core",
            ui_quality_status,
            _ui_quality_summary(ui_file_count, ui_quality_status),
        ),
        _module(
            "ui-token-contract",
            "optional",
            "not_run" if ui_file_count > 0 else "not_applicable",
            (
                "The fixture-scoped UI token contract sidecar was not requested."
                if ui_file_count > 0
                else "UI token contracts do not apply without a detected UI surface."
            ),
        ),
        _optional_architecture(config),
        _optional_skills(config, code_quality_scan),
        _optional_security(security_scan),
        _optional_release(standards_packet, profile),
        _optional_intent(intent),
        _optional_ci(repo_scan),
        _optional_gate_controller(repo_scan),
        _optional_planning(repo_scan),
    ]
    return {
        "schema": MODULE_STATUS_SCHEMA,
        "mode": mode,
        "profile": profile,
        "modules": modules,
        "summary": _summary_counts(modules),
    }


def build_timeout_module_status(*, mode: str, profile: str, reason: str) -> dict[str, Any]:
    modules = [
        _module(
            module_id,
            "core",
            "enabled" if module_id == "read-only-safety" else "not_run",
            f"{module_id} was not evaluated because the workflow timed out: {reason}",
        )
        for module_id in (
            "repository-discovery",
            "evidence-provenance",
            "structural-quality",
            "capability-detection",
            "remediation-handoff",
            "read-only-safety",
            "similarity",
            "ui-quality",
        )
    ]
    modules.extend(
        _module(
            module_id,
            "optional",
            "not_run",
            f"{module_id} was not evaluated because the workflow timed out: {reason}",
        )
        for module_id in (
            "ui-token-contract",
            "architecture-contracts",
            "quality-skills",
            "security-review",
            "release-readiness",
            "author-intent",
            "ci-evidence",
            "gate-controller",
            "qr-phase-planning",
        )
    )
    return {
        "schema": MODULE_STATUS_SCHEMA,
        "mode": mode,
        "profile": profile,
        "modules": modules,
        "summary": _summary_counts(modules),
    }


def validate_module_status(payload: dict[str, Any]) -> dict[str, Any]:
    modules = payload.get("modules")
    valid = payload.get("schema") == MODULE_STATUS_SCHEMA and isinstance(modules, list)
    errors: list[str] = []
    if not valid:
        errors.append("module status must contain the expected schema and modules list")
    if isinstance(modules, list):
        seen: set[str] = set()
        for item in modules:
            if not isinstance(item, dict):
                errors.append("module entries must be objects")
                continue
            module_id = item.get("id")
            status = item.get("status")
            if not isinstance(module_id, str) or not module_id:
                errors.append("module entries require a non-empty id")
            elif module_id in seen:
                errors.append(f"duplicate module id: {module_id}")
            else:
                seen.add(module_id)
            if item.get("kind") not in {"core", "optional"}:
                errors.append(f"invalid module kind for {module_id}")
            if status not in MODULE_STATUS_VALUES:
                errors.append(f"invalid module status for {module_id}: {status}")
    return {
        "passed": not errors,
        "errors": errors,
        "module_count": len(modules) if isinstance(modules, list) else 0,
    }


def _module(
    module_id: str,
    kind: str,
    status: str,
    summary: str,
    *,
    finding_count: int | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": module_id,
        "kind": kind,
        "status": status,
        "summary": summary,
    }
    if finding_count is not None:
        item["finding_count"] = finding_count
    if reason is not None:
        item["reason"] = reason
    return item


def _optional_architecture(config: dict[str, Any] | None) -> dict[str, Any]:
    section = _section(config, "architecture")
    if section is None:
        return _module(
            "architecture-contracts",
            "optional",
            "not_applicable",
            "No repository-specific architecture contract is configured.",
        )
    if section.get("enabled") is True:
        return _module(
            "architecture-contracts",
            "optional",
            "enabled",
            "Configured import and pattern boundaries are active.",
        )
    return _module(
        "architecture-contracts",
        "optional",
        "disabled",
        "Architecture contracts are configured but not enabled.",
    )


def _optional_skills(
    config: dict[str, Any] | None,
    code_quality_scan: dict[str, Any] | None,
) -> dict[str, Any]:
    section = _section(config, "skills")
    skills = code_quality_scan.get("quality_skills") if code_quality_scan else None
    selection = code_quality_scan.get("skill_selection") if code_quality_scan else None
    selection_status = selection.get("status") if isinstance(selection, dict) else None
    if section is None and selection_status == "disabled":
        return _module(
            "quality-skills",
            "optional",
            "disabled",
            "Quality Skill packs are explicitly disabled for this repository.",
        )
    if section is None and selection_status == "unavailable":
        return _module(
            "quality-skills",
            "optional",
            "unavailable",
            "The configured global Quality Skill corpus could not be loaded.",
        )
    if section is None and selection_status in {None, "not_configured"}:
        return _module(
            "quality-skills",
            "optional",
            "not_applicable",
            "No local or global Quality Skill packs are configured.",
        )
    if section is None and selection_status == "enabled" and not skills:
        return _module(
            "quality-skills",
            "optional",
            "enabled",
            "The global Quality Skill corpus was evaluated; no pack met the repository relevance threshold.",
        )
    if section is None:
        section = {}
    if section.get("enabled") is False:
        return _module(
            "quality-skills",
            "optional",
            "disabled",
            "Quality Skill packs are explicitly disabled for this repository.",
        )
    if isinstance(skills, list) and skills:
        source = selection.get("source") if isinstance(selection, dict) else "local"
        global_count = (
            len(selection.get("selected_global_skill_ids", []))
            if isinstance(selection, dict)
            and isinstance(selection.get("selected_global_skill_ids"), list)
            else 0
        )
        source_summary = f" from {source}" if isinstance(source, str) else ""
        return _module(
            "quality-skills",
            "optional",
            "enabled",
            f"{len(skills)} Quality Skill pack(s) are active{source_summary}; {global_count} selected from the global corpus.",
        )
    return _module(
        "quality-skills",
        "optional",
        "unavailable",
        "Quality Skills are enabled but no valid active pack was loaded.",
    )


def _optional_security(security_scan: dict[str, Any] | None) -> dict[str, Any]:
    if security_scan is None:
        return _module(
            "security-review",
            "optional",
            "not_run",
            "The security review phase was not run for this workflow.",
        )
    settings = security_scan.get("settings")
    if isinstance(settings, dict) and settings.get("enabled") is False:
        return _module(
            "security-review",
            "optional",
            "disabled",
            "Security review is explicitly disabled by repository configuration.",
        )
    return _module(
        "security-review",
        "optional",
        "enabled",
        "Security surfaces and configured review gates were evaluated.",
    )


def _optional_release(
    standards_packet: dict[str, Any] | None,
    profile: str,
) -> dict[str, Any]:
    selected_profile = standards_packet.get("profile") if standards_packet else profile
    if selected_profile == "release":
        return _module(
            "release-readiness",
            "optional",
            "enabled",
            "Release readiness gates are active for the selected profile.",
        )
    return _module(
        "release-readiness",
        "optional",
        "not_applicable",
        "The release profile was not selected.",
    )


def _optional_intent(intent: dict[str, Any] | None) -> dict[str, Any]:
    return _module(
        "author-intent",
        "optional",
        "enabled" if intent is not None else "not_run",
        "Task intent is attached to the run." if intent else "No task intent was supplied.",
    )


def _optional_ci(repo_scan: dict[str, Any]) -> dict[str, Any]:
    checks = repo_scan.get("ci_checks")
    if isinstance(checks, list) and checks:
        return _module(
            "ci-evidence",
            "optional",
            "enabled",
            f"{len(checks)} CI check result(s) were supplied to the run.",
        )
    return _module(
        "ci-evidence",
        "optional",
        "not_run",
        "No external CI status evidence was supplied.",
    )


def _optional_gate_controller(repo_scan: dict[str, Any]) -> dict[str, Any]:
    repo_root = repo_scan.get("repo_root")
    if isinstance(repo_root, str) and (Path(repo_root) / ".quality-runner" / "gate-runs").exists():
        return _module(
            "gate-controller",
            "optional",
            "enabled",
            "QR Gate state is available alongside the run artifacts.",
        )
    return _module(
        "gate-controller",
        "optional",
        "not_run",
        "The optional gate controller was not opened for this run.",
    )


def _optional_planning(repo_scan: dict[str, Any]) -> dict[str, Any]:
    repo_root = repo_scan.get("repo_root")
    if isinstance(repo_root, str) and (Path(repo_root) / ".planning" / "quality-runner").exists():
        return _module(
            "qr-phase-planning",
            "optional",
            "enabled",
            "QR-owned phase planning is present for this repository.",
        )
    return _module(
        "qr-phase-planning",
        "optional",
        "not_run",
        "No QR-owned phase plan is present; GSD remains an external consumer.",
    )


def _summary_counts(modules: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(item["status"]) for item in modules)
    kinds = {
        kind: dict(Counter(str(item["status"]) for item in modules if item["kind"] == kind))
        for kind in ("core", "optional")
    }
    return {
        "module_count": len(modules),
        "by_status": dict(sorted(statuses.items())),
        "by_kind": kinds,
    }


def _summary(code_quality_scan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(code_quality_scan, dict):
        return {}
    summary = code_quality_scan.get("summary")
    return summary if isinstance(summary, dict) else {}


def _ui_file_count(code_quality_scan: dict[str, Any] | None) -> int:
    summary = _summary(code_quality_scan)
    explicit = summary.get("ui_file_count")
    if isinstance(explicit, int):
        return explicit
    accountability = code_quality_scan.get("accountability") if code_quality_scan else None
    if not isinstance(accountability, list):
        return 0
    return sum(
        1
        for item in accountability
        if isinstance(item, dict)
        and isinstance(item.get("check_coverage"), list)
        and "ui-structural" in item["check_coverage"]
    )


def _ui_quality_status(summary: dict[str, Any], ui_file_count: int) -> str:
    status = summary.get("ui_quality_status")
    if isinstance(status, str) and status in MODULE_STATUS_VALUES:
        return status
    return "enabled" if ui_file_count > 0 else "not_applicable"


def _ui_quality_summary(file_count: int, status: str) -> str:
    if file_count == 0:
        return "No user-facing UI files were detected."
    if status == "disabled":
        return (
            f"UI files were detected, but UI structural checks are disabled ({file_count} file(s))."
        )
    return f"UI structural checks cover {file_count} detected UI file(s)."


def _similarity_status(summary: dict[str, Any]) -> str:
    status = summary.get("semantic_similarity_status")
    if isinstance(status, str) and status in MODULE_STATUS_VALUES:
        return status
    if status in {"executed", "enabled"}:
        return "enabled"
    if status in {"failed", "missing"}:
        return "unavailable"
    if status == "skipped":
        return "disabled"
    if summary.get("semantic_similarity_engine") == "quality-runner-native":
        return "enabled"
    return "not_run"


def _similarity_summary(summary: dict[str, Any]) -> str:
    engine = summary.get("semantic_similarity_engine")
    if engine in {"quality-runner-native", "native"}:
        return "QR-native semantic similarity runs without external binaries."
    if engine == "external-binary":
        return "An external similarity backend was explicitly selected for this run."
    return "Native semantic similarity was not executed for this run."


def _section(config: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    value = config.get(key) if isinstance(config, dict) else None
    return value if isinstance(value, dict) else None


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0
