from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from quality_runner.core.audit_contracts import (
    AuditArtifactPaths,
    AuditPayload,
    ScanExclusionOverlay,
)

type GateExecutionPlan = list[dict[str, object]]
type GateVerificationPayload = dict[str, object]
type WorktreeMode = Literal["in-place", "disposable"]


@dataclass(frozen=True)
class GateExecutionPolicy:
    timeout_seconds: int
    execute_discovered_gates: bool
    read_only_gates: bool
    allow_mutating_gates: bool
    worktree_mode: WorktreeMode | str
    allow_dirty_worktree_verify: bool


@dataclass(frozen=True)
class VerificationRequest:
    repo_root: Path
    run_id: str
    profile: str | None
    ci_status_json: Path | None
    checkout_most_advanced_branch: bool
    policy: GateExecutionPolicy
    skill_review_report: AuditPayload | None
    intent: AuditPayload | None
    scan_exclusion_overlay: ScanExclusionOverlay | None = None
    include_ignored_paths: tuple[str, ...] = ()
    include_paths: tuple[str, ...] = ()
    agent_review_mode: str | None = None
    readiness_evidence_file: Path | None = None


@dataclass(frozen=True)
class VerificationResult:
    run_id: str
    status: str
    artifact_paths: AuditArtifactPaths
    warnings: tuple[AuditPayload, ...]
