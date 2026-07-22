from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

type AuditPayload = dict[str, object]
type AuditArtifactPaths = dict[str, str]
type ScanExclusionOverlay = list[str] | dict[str, list[str]]
type AnalysisMode = Literal["balanced", "full"]
type CacheMode = Literal["repo", "external", "disabled"]


class AuditWarning(TypedDict):
    code: str
    message: str
    path: str


@dataclass(frozen=True)
class AuditRequest:
    repo_root: Path
    run_id: str
    profile: str | None
    ci_status_json: Path | None
    include_ignored_paths: tuple[str, ...]
    branch_warnings: tuple[AuditWarning, ...]
    skill_review_report: AuditPayload | None
    intent: AuditPayload | None
    scan_exclusion_overlay: ScanExclusionOverlay | None = None
    agent_review_mode: str | None = None
    readiness_evidence_file: Path | None = None
    analysis_cache_root: Path | None = None
    focus_paths: tuple[str, ...] = ()
    analysis_mode: AnalysisMode = "full"
    cache_mode: CacheMode | None = None
    cache_root: Path | None = None
    performance_budget_seconds: float | None = None
    include_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScannedTextFile:
    path: str
    text: str
    lines: list[str]


@dataclass(frozen=True)
class TextScanScope:
    repo_root: Path
    files: tuple[ScannedTextFile, ...]
    skipped_files: tuple[AuditPayload, ...]
    max_text_files: int
    scan_exclusions: tuple[str, ...]
    security_surface_paths: tuple[str, ...] = ()
    source_analysis_cache: object | None = None
    focus_paths: tuple[str, ...] = ()
    file_paths: tuple[str, ...] = ()
    inventory: AuditPayload | None = None
    include_paths: tuple[str, ...] = ()
    scan_inclusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditAnalysis:
    request: AuditRequest
    config: AuditPayload
    scan: AuditPayload
    standards_packet: AuditPayload
    capability_map: AuditPayload
    security_scan: AuditPayload
    code_quality_scan: AuditPayload
    package_manager_preflight: AuditPayload
    text_scan_scope: TextScanScope
    performance: AuditPayload | None = None


@dataclass(frozen=True)
class AuditPlan:
    analysis: AuditAnalysis
    audit_report: AuditPayload
    remediation_plan: AuditPayload
    handoff: AuditPayload
    status: Literal["clean", "planned"]


@dataclass(frozen=True)
class PlannedAudit(AuditPlan):
    resolution_ledger: AuditPayload
    remediation_context: AuditPayload | None = None
