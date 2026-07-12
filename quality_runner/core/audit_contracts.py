from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

type AuditPayload = dict[str, object]
type AuditArtifactPaths = dict[str, str]


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
