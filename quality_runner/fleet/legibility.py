from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.discovery import inspect_repo
from quality_runner.fleet.change_matrix import assess_change_surface_coverage
from quality_runner.fleet.contracts import (
    DIMENSION_LABELS,
    DIMENSIONS,
    FLEET_FINDING_SCHEMA,
    FLEET_PLAN_SCHEMA,
    digest,
)
from quality_runner.fleet.legibility_evidence import (
    collect_documents,
    collect_freshness_evidence,
    collect_link_evidence,
    contains_any,
    term_evidence,
)
from quality_runner.fleet.projection import build_local_projection
from quality_runner.fleet.skill_contracts import assess_skill_contract_quality

DIMENSION_TERMS: dict[str, tuple[str, ...]] = {
    "architecture_boundaries": ("architecture", "boundary", "ownership", "module", "system design"),
    "change_surface_coverage": ("change surface", "change matrix", "dependency map"),
    "coding_conventions": ("convention", "style", "strict", "format", "coding standard"),
    "security_constraints": ("security", "credential", "secret", "authentication", "do not commit"),
    "failure_modes": ("failure", "troubleshoot", "recovery", "incident", "common issue"),
    "implementation_examples": (
        "example",
        "good implementation",
        "reference implementation",
        "pattern",
    ),
    "definition_of_done": (
        "definition of done",
        "acceptance criteria",
        "quality gate",
        "done when",
        "verify",
    ),
    "approval_gated_paths": (
        "approval",
        "forbidden",
        "do not change",
        "destructive",
        "human review",
    ),
    "deployment_rollback": ("deploy", "deployment", "rollback", "release", "revert"),
    "context_routing": ("read when", "load when", "routing", "minimum context", "context index"),
    "skill_contract_quality": ("skill", "trigger", "observable output"),
}

DEPLOYMENT_MARKERS = (
    ".github/workflows",
    "vercel.json",
    "fly.toml",
    "dockerfile",
    "docker-compose",
    "render.yaml",
    "railway.json",
    "terraform",
    "pulumi",
)


def audit_repository(
    *,
    repository: dict[str, Any],
    as_of: str,
    run_id: str,
) -> dict[str, Any]:
    root = Path(str(repository["primary_path"])).expanduser().resolve()
    scan: dict[str, Any]
    scan_error: str | None = None
    try:
        scan = inspect_repo(root, run_id, cache_mode="disabled")
    except (OSError, ValueError) as error:
        scan = {"repo_root": str(root), "warnings": []}
        scan_error = str(error)
    documents = collect_documents(root)
    link_evidence = collect_link_evidence(root, documents)
    findings = [
        _dimension_finding(
            repository=repository,
            scan=scan,
            documents=documents,
            link_evidence=link_evidence,
            dimension=dimension,
            as_of=as_of,
        )
        for dimension in DIMENSIONS
    ]
    if scan_error:
        findings.append(
            {
                "schema": FLEET_FINDING_SCHEMA,
                "finding_id": digest([repository["repo_id"], "scan", scan_error])[:16],
                "repo_id": repository["repo_id"],
                "audit_id": run_id,
                "as_of": as_of,
                "dimension": "quality_commands",
                "status": "blocked",
                "score": 0,
                "applicable": True,
                "severity": "high",
                "priority": "P0",
                "confidence": "high",
                "message": "QR could not inspect the repository without a valid static scan.",
                "evidence": [{"path": ".", "detail": scan_error}],
                "validation_commands": ["qr audit REPO --profile environment-legibility"],
            }
        )
    plan = build_remediation_plan(
        repository=repository,
        findings=findings,
        scan=scan,
        as_of=as_of,
    )
    return {
        "schema": FLEET_FINDING_SCHEMA,
        "repo_id": repository["repo_id"],
        "audit_id": run_id,
        "as_of": as_of,
        "repository": repository,
        "scan": _scan_projection(scan),
        "documents": {
            "paths": sorted(documents),
            "link_evidence": link_evidence,
            "freshness": collect_freshness_evidence(documents, as_of),
        },
        "findings": findings,
        "plan": plan,
        "static_provenance_hash": digest(
            {"repo": repository, "scan": scan, "documents": documents, "findings": findings}
        ),
    }


def build_remediation_plan(
    *,
    repository: dict[str, Any],
    findings: list[dict[str, Any]],
    scan: dict[str, Any],
    as_of: str,
) -> dict[str, Any]:
    tasks: dict[str, list[dict[str, Any]]] = {"P0": [], "P1": [], "P2": []}
    for finding in findings:
        if finding.get("status") == "not_applicable" or finding.get("score") == 4:
            continue
        priority = str(finding.get("priority", "P1"))
        if priority not in tasks:
            priority = "P1"
        dimension = str(finding.get("dimension", "environment"))
        tasks[priority].append(
            {
                "task_id": f"{repository['repo_id']}-{dimension}",
                "dimension": dimension,
                "observed_gap": finding.get("message"),
                "evidence": finding.get("evidence", []),
                "exact_surface": [item.get("path") for item in finding.get("evidence", [])],
                "owner": "repository-owner",
                "dependencies": ["preserve existing repository conventions"],
                "validation_commands": finding.get("validation_commands", []),
                "acceptance_criteria": [
                    f"{DIMENSION_LABELS.get(dimension, dimension)} is discoverable, validated, and fresh",
                    "QR replay records the evidence without modifying the source checkout",
                ],
                "rollback_or_removal": "Remove the local projection or revert the documentation-only commit if it conflicts with the repository contract.",
            }
        )
    projection = build_local_projection(repository, findings)
    return {
        "schema": FLEET_PLAN_SCHEMA,
        "plan_id": digest([repository["repo_id"], findings])[:16],
        "repo_id": repository["repo_id"],
        "as_of": as_of,
        "status": "ready" if any(tasks.values()) else "complete",
        "observed_gap_summary": f"{sum(len(items) for items in tasks.values())} remediation task(s) remain below full maturity.",
        "impact": "Agents may spend more context, choose unverified commands, or make unsafe assumptions when the environment contract is incomplete.",
        "confidence": _plan_confidence(findings),
        "affected_surfaces": sorted(
            {
                path
                for finding in findings
                for item in finding.get("evidence", [])
                for path in [item.get("path")]
                if isinstance(path, str)
            }
        ),
        "tasks": tasks,
        "owner": "repository-owner",
        "local_projection": projection,
        "unresolved_questions": [
            "Which repository-specific command should be the canonical pre-PR gate if several commands are discovered?",
        ],
        "provenance_hash": digest({"repo": repository, "scan": scan, "findings": findings}),
    }


def _dimension_finding(
    *,
    repository: dict[str, Any],
    scan: dict[str, Any],
    documents: dict[str, str],
    link_evidence: dict[str, Any],
    dimension: str,
    as_of: str,
) -> dict[str, Any]:
    combined = "\n".join(documents.values()).lower()
    evidence: list[dict[str, str]] = []
    score = 0
    status = "absent"
    confidence = "medium"
    if dimension == "change_surface_coverage":
        assessment = assess_change_surface_coverage(
            Path(str(repository["primary_path"])).expanduser().resolve(),
            documents,
            as_of,
        )
        return _finding(
            repository=repository,
            dimension=dimension,
            score=assessment["score"],
            as_of=as_of,
            status=assessment["status"],
            severity="observation",
            priority="P1",
            confidence="high" if assessment["status"] != "unknown" else "medium",
            message=assessment["message"],
            evidence=assessment["evidence"],
            validation_commands=["qr fleet audit run --repo-path REPO --json"],
        )
    if dimension == "skill_contract_quality":
        assessment = assess_skill_contract_quality(
            Path(str(repository["primary_path"])).expanduser().resolve()
        )
        return _finding(
            repository=repository,
            dimension=dimension,
            score=assessment["score"],
            as_of=as_of,
            status=assessment["status"],
            severity="observation",
            priority="P1",
            confidence="medium",
            message=assessment["message"],
            evidence=assessment["evidence"],
            validation_commands=["qr fleet audit run --repo-path REPO --json"],
        )
    if dimension == "quality_commands":
        commands = scan.get("quality_commands")
        if isinstance(commands, list) and commands:
            score = 2
            status = "discoverable"
            evidence = [
                {
                    "path": str(item.get("source", "discovered")),
                    "detail": str(item.get("command", "")),
                }
                for item in commands
                if isinstance(item, dict)
            ][:12]
        elif contains_any(combined, ("test", "lint", "build")):
            score = 1
            status = "unknown"
            evidence = [
                {
                    "path": "documentation",
                    "detail": "Quality language is present but no executable command was discovered.",
                }
            ]
        else:
            evidence = [
                {
                    "path": ".",
                    "detail": "No executable quality command was discovered in the bounded scan.",
                }
            ]
    elif dimension == "deployment_rollback" and not _has_deployment_surface(
        repository, scan, combined
    ):
        return _finding(
            repository=repository,
            dimension=dimension,
            score=None,
            as_of=as_of,
            status="not_applicable",
            severity="observation",
            priority="P2",
            confidence="medium",
            message="No deployment surface was detected in the bounded repository scan.",
            evidence=[
                {
                    "path": ".",
                    "detail": "No deployment markers or deployment documentation were found.",
                }
            ],
            validation_commands=["Reassess when a deployment surface is introduced."],
        )
    else:
        terms = DIMENSION_TERMS[dimension]
        matches = [term for term in terms if term in combined]
        if matches:
            score = 2
            status = "discoverable"
            evidence = term_evidence(documents, matches)
        else:
            evidence = [
                {"path": ".", "detail": f"No evidence for {DIMENSION_LABELS[dimension]} was found."}
            ]

    freshness = collect_freshness_evidence(documents, as_of)
    if dimension == "context_routing":
        instruction_files = scan.get("agent_instruction_files")
        if isinstance(instruction_files, list) and instruction_files:
            score = max(score, 2)
            status = "discoverable"
            evidence.extend(
                {"path": str(path), "detail": "agent instruction surface"}
                for path in instruction_files
            )
        if (
            ".agents/context/README.md" in documents or ".context/README.md" in documents
        ) and link_evidence.get("invalid_count", 0) == 0:
            score = max(score, 3)
            status = "validated"
    if link_evidence.get("invalid_count", 0) > 0 and dimension in {
        "context_routing",
        "architecture_boundaries",
    }:
        status = "blocked"
        confidence = "high"
        score = min(score, 1)
        evidence.append(
            {
                "path": "documentation links",
                "detail": "One or more relative context/document links are invalid.",
            }
        )
    if freshness.get("stale_paths") and dimension in {
        "context_routing",
        "definition_of_done",
        "quality_commands",
    }:
        status = "stale"
        confidence = "high"
        score = min(score, 2)
        evidence.append(
            {
                "path": freshness["stale_paths"][0],
                "detail": "Last-reviewed marker is older than the freshness window.",
            }
        )
    elif freshness.get("status") == "unknown" and dimension in {
        "context_routing",
        "definition_of_done",
        "quality_commands",
    }:
        status = "unknown"
        score = min(score, 2)
        evidence.append(
            {"path": "documentation", "detail": "No freshness marker was found for this control."}
        )
    if score == 2 and status == "discoverable" and not evidence:
        status = "unknown"
    priority = (
        "P0"
        if dimension in {"quality_commands", "security_constraints", "approval_gated_paths"}
        and score < 2
        else "P1"
    )
    message = (
        f"{DIMENSION_LABELS[dimension]} are below the QR full-potential contract."
        if score < 4
        else f"{DIMENSION_LABELS[dimension]} are fully evidenced."
    )
    return _finding(
        repository=repository,
        dimension=dimension,
        score=score,
        as_of=as_of,
        status=status,
        severity="high" if priority == "P0" else "observation",
        priority=priority,
        confidence=confidence,
        message=message,
        evidence=evidence[:16],
        validation_commands=_validation_commands(dimension, scan),
    )


def _finding(
    *,
    repository: dict[str, Any],
    dimension: str,
    score: int | None,
    as_of: str,
    status: str,
    severity: str,
    priority: str,
    confidence: str,
    message: str,
    evidence: list[dict[str, str]],
    validation_commands: list[str],
) -> dict[str, Any]:
    return {
        "schema": FLEET_FINDING_SCHEMA,
        "finding_id": digest([repository["repo_id"], dimension, status, evidence])[:16],
        "repo_id": repository["repo_id"],
        "as_of": as_of,
        "dimension": dimension,
        "label": DIMENSION_LABELS[dimension],
        "applicable": status != "not_applicable",
        "score": score,
        "status": status,
        "severity": severity,
        "priority": priority,
        "confidence": confidence,
        "message": message,
        "evidence": evidence,
        "validation_commands": validation_commands,
        "provenance_hash": digest(
            {"repo_id": repository["repo_id"], "dimension": dimension, "evidence": evidence}
        ),
    }


def _scan_projection(scan: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema",
        "package_manager",
        "languages",
        "ecosystems",
        "scripts",
        "quality_commands",
        "agent_instruction_files",
        "ci_files",
        "quality_contract",
        "warnings",
        "git_provenance",
    )
    return {key: scan[key] for key in keys if key in scan}


def _validation_commands(dimension: str, scan: dict[str, Any]) -> list[str]:
    commands = [
        str(item.get("command"))
        for item in scan.get("quality_commands", [])
        if isinstance(item, dict) and isinstance(item.get("command"), str)
    ]
    if dimension == "quality_commands" and commands:
        return commands[:6]
    return ["qr audit REPO --profile environment-legibility --json"]


def _has_deployment_surface(repository: dict[str, Any], scan: dict[str, Any], text: str) -> bool:
    root = Path(str(repository["primary_path"]))
    if any((root / marker).exists() for marker in DEPLOYMENT_MARKERS):
        return True
    ci_files = scan.get("ci_files")
    return bool(isinstance(ci_files, list) and ci_files) and contains_any(
        text, ("deploy", "release")
    )


def _plan_confidence(findings: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in findings}
    if "blocked" in statuses:
        return "high"
    if "unknown" in statuses or "stale" in statuses:
        return "medium"
    return "medium"
