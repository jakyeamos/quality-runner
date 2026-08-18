from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from quality_runner.config import load_repo_config
from quality_runner.discovery import inspect_repo
from quality_runner.fleet.agent_usability import assess_agent_usability
from quality_runner.fleet.behavior_assurance import assess_behavior_assurance
from quality_runner.fleet.behavior_finding import behavior_finding_arguments
from quality_runner.fleet.change_matrix import assess_change_surface_coverage
from quality_runner.fleet.change_surface_hotspots import assess_change_surface_hotspots
from quality_runner.fleet.contracts import (
    DEPLOYMENT_MARKERS,
    DIMENSION_LABELS,
    DIMENSION_TERMS,
    DIMENSIONS,
    FLEET_FINDING_SCHEMA,
    FLEET_PLAN_SCHEMA,
    digest,
    standard_dimensions,
)
from quality_runner.fleet.documentation_visibility import assess_developer_legibility
from quality_runner.fleet.error_codes import stable_error_code_finding_arguments
from quality_runner.fleet.legibility_contract import maintained_control
from quality_runner.fleet.legibility_evidence import (
    collect_documents,
    collect_freshness_evidence,
    collect_link_evidence,
    contains_any,
    term_evidence,
)
from quality_runner.fleet.legibility_finding import (
    finding as _finding,
)
from quality_runner.fleet.legibility_finding import (
    validation_commands as _validation_commands,
)
from quality_runner.fleet.legibility_support import plan_confidence, scan_projection
from quality_runner.fleet.long_running_tasks import assess_long_running_tasks
from quality_runner.fleet.maturity_dimensions import assess_maturity_dimensions
from quality_runner.fleet.projection import build_local_projection
from quality_runner.fleet.skill_contracts import assess_skill_contract_quality
from quality_runner.fleet.standard_audit import (
    long_running_task_finding_arguments,
    matrix_maintenance_finding_arguments,
)
from quality_runner.fleet.strict_debt import (
    assess_strict_policy_visibility,
    assess_strict_type_debt,
)


def audit_repository(
    *,
    repository: dict[str, Any],
    as_of: str,
    run_id: str,
    standard: str | None = None,
) -> dict[str, Any]:
    selected_standard_dimensions = standard_dimensions(standard)
    root = Path(str(repository["primary_path"])).expanduser().resolve()
    config = load_repo_config(root)
    scan: dict[str, Any]
    scan_error: str | None = None
    try:
        scan = inspect_repo(root, run_id, config=config, cache_mode="disabled")
    except (OSError, ValueError) as error:
        scan = {"repo_root": str(root), "warnings": []}
        scan_error = str(error)
    documents = collect_documents(root)
    link_evidence = collect_link_evidence(root, documents)
    selected_dimensions = (
        selected_standard_dimensions if selected_standard_dimensions else DIMENSIONS
    )
    long_running_task_assessments = (
        assess_long_running_tasks(root)
        if any(dimension.startswith("long_running_task_") for dimension in selected_dimensions)
        else {}
    )
    maturity_assessments = (
        assess_maturity_dimensions(
            root=root,
            repository=repository,
            scan=scan,
            documents=documents,
            config=config,
            as_of=as_of,
        )
        if standard is None
        else {}
    )
    findings = [
        _dimension_finding(
            repository=repository,
            scan=scan,
            documents=documents,
            link_evidence=link_evidence,
            dimension=dimension,
            as_of=as_of,
            maturity_assessments=maturity_assessments,
            long_running_task_assessments=long_running_task_assessments,
        )
        for dimension in selected_dimensions
    ]
    if standard is None:
        agent_usability = assess_agent_usability(
            root,
            documents,
            link_evidence,
            as_of,
        )
        behavior_assurance = assess_behavior_assurance(root, repository, as_of)
        findings.append(
            _finding(**behavior_finding_arguments(repository, behavior_assurance, as_of))
        )
    else:
        agent_usability = {}
        behavior_assurance = {}
    if scan_error and standard is None:
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
        "standard": standard,
        "repository": repository,
        "scan": scan_projection(scan),
        "documents": {
            "paths": sorted(documents),
            "link_evidence": link_evidence,
            "freshness": collect_freshness_evidence(documents, as_of),
        },
        "agent_usability": agent_usability,
        "behavior_assurance": behavior_assurance,
        "findings": findings,
        "plan": plan,
        "static_provenance_hash": digest(
            {
                "repo": repository,
                "scan": scan,
                "documents": documents,
                "agent_usability": agent_usability,
                "behavior_assurance": behavior_assurance,
                "standard": standard,
                "findings": findings,
            }
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
        "confidence": plan_confidence(findings),
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
    maturity_assessments: dict[str, dict[str, Any]],
    long_running_task_assessments: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    combined = "\n".join(documents.values()).lower()
    evidence: list[dict[str, str]] = []
    score = 0
    status = "absent"
    confidence = "medium"
    root = Path(str(repository["primary_path"])).expanduser().resolve()
    if dimension == "developer_legibility":
        assessment = assess_developer_legibility(root, documents, link_evidence, as_of)
        score = assessment["score"]
        return _finding(
            repository=repository,
            dimension=dimension,
            score=score,
            as_of=as_of,
            status=str(assessment["status"]),
            severity="observation" if score is None or score >= 2 else "high",
            priority="P1",
            confidence="high",
            message=str(assessment["message"]),
            evidence=list(assessment["evidence"]),
            validation_commands=[
                "qr fleet audit run --repo-path REPO --standard developer-legibility --json"
            ],
            audit=assessment,
        )
    if dimension == "change_surface_hotspots":
        assessment = assess_change_surface_hotspots(root, as_of)
        score = assessment["score"]
        return _finding(
            repository=repository,
            dimension=dimension,
            score=score,
            as_of=as_of,
            status=str(assessment["status"]),
            severity="observation",
            priority="P2",
            confidence="medium",
            message=str(assessment["message"]),
            evidence=list(assessment["evidence"]),
            validation_commands=["qr fleet audit run --repo-path REPO --json"],
            audit=assessment,
        )
    if dimension in maturity_assessments:
        assessment = maturity_assessments[dimension]
        return _finding(
            repository=repository,
            dimension=dimension,
            score=assessment["score"],
            as_of=as_of,
            status=str(assessment["status"]),
            severity=str(assessment["severity"]),
            priority=str(assessment["priority"]),
            confidence=str(assessment["confidence"]),
            message=str(assessment["message"]),
            evidence=list(assessment["evidence"]),
            validation_commands=list(assessment["validation_commands"]),
            applicability=str(assessment["applicability"]),
        )
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
    if dimension == "diagnosability.stable_error_codes":
        return _finding(**stable_error_code_finding_arguments(repository=repository, as_of=as_of))
    if dimension == "matrix_maintenance":
        return _finding(
            **matrix_maintenance_finding_arguments(
                repository=repository, documents=documents, as_of=as_of
            )
        )
    if dimension in long_running_task_assessments:
        return _finding(
            **long_running_task_finding_arguments(
                repository=repository,
                dimension=dimension,
                assessments=long_running_task_assessments,
                as_of=as_of,
            )
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
    if dimension == "strict_policy_visibility":
        assessment = assess_strict_policy_visibility(
            Path(str(repository["primary_path"])).expanduser().resolve(), scan
        )
        return _finding(
            repository=repository,
            dimension=dimension,
            score=assessment["score"],
            as_of=as_of,
            status=assessment["status"],
            severity="observation",
            priority="P1",
            confidence="high",
            message=assessment["message"],
            evidence=assessment["evidence"],
            validation_commands=["uv run --locked qr fleet audit run --repo-path REPO --json"],
        )
    if dimension == "strict_type_debt":
        assessment = assess_strict_type_debt(
            Path(str(repository["primary_path"])).expanduser().resolve()
        )
        return _finding(
            repository=repository,
            dimension=dimension,
            score=assessment["score"],
            as_of=as_of,
            status=assessment["status"],
            severity="high" if assessment["status"] == "blocked" else "observation",
            priority="P0" if assessment["status"] == "blocked" else "P1",
            confidence="high",
            message=assessment["message"],
            evidence=assessment["evidence"],
            validation_commands=["uv run --locked python scripts/check_strict_baseline.py"],
        )
    maintained = maintained_control(
        root=Path(str(repository["primary_path"])).expanduser().resolve(),
        dimension=dimension,
        as_of=as_of,
    )
    if maintained is not None:
        return _finding(
            repository=repository,
            dimension=dimension,
            score=4,
            as_of=as_of,
            status="maintained",
            severity="observation",
            priority="P1",
            confidence="high",
            message="The control is documented, validated, fresh, and bound to an enforcement path.",
            evidence=maintained,
            validation_commands=[
                "python3 scripts/check_environment_contract.py",
                "qr fleet audit run --repo-path REPO --dynamic --json",
            ],
        )
    if dimension == "quality_commands":
        commands = scan.get("quality_commands")
        if isinstance(commands, list) and commands:
            typed_commands = cast(list[Any], commands)
            score = 2
            status = "discoverable"
            evidence = [
                {
                    "path": str(cast(dict[str, Any], item).get("source", "discovered")),
                    "detail": str(cast(dict[str, Any], item).get("command", "")),
                }
                for item in typed_commands
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
            typed_instruction_files = cast(list[Any], instruction_files)
            score = max(score, 2)
            status = "discoverable"
            evidence.extend(
                {"path": str(path), "detail": "agent instruction surface"}
                for path in typed_instruction_files
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
    if freshness.get("status") == "stale" and dimension in {
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


def _has_deployment_surface(repository: dict[str, Any], scan: dict[str, Any], text: str) -> bool:
    root = Path(str(repository["primary_path"]))
    if any((root / marker).exists() for marker in DEPLOYMENT_MARKERS):
        return True
    ci_files = scan.get("ci_files")
    return bool(isinstance(ci_files, list) and cast(list[Any], ci_files)) and contains_any(
        text, ("deploy", "release")
    )
