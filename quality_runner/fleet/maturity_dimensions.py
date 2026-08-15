from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import DEPLOYMENT_MARKERS, DIMENSION_TERMS
from quality_runner.fleet.maturity_dimension_support import (
    assessment as _assessment,
)
from quality_runner.fleet.maturity_dimension_support import (
    capability_evidence as _capability_evidence,
)
from quality_runner.fleet.maturity_dimension_support import (
    capability_item as _capability_item,
)
from quality_runner.fleet.maturity_dimension_support import (
    command_evidence as _command_evidence,
)
from quality_runner.fleet.maturity_dimension_support import (
    commands_by_id as _commands,
)
from quality_runner.fleet.maturity_dimension_support import (
    existing_paths as _existing_paths,
)
from quality_runner.fleet.maturity_dimension_support import (
    matched_terms as _matched_terms,
)
from quality_runner.fleet.maturity_dimension_support import (
    not_applicable as _not_applicable,
)
from quality_runner.fleet.maturity_dimension_support import (
    path_evidence as _path_evidence,
)
from quality_runner.fleet.maturity_dimension_support import (
    score_status as _status,
)
from quality_runner.fleet.maturity_dimension_support import (
    surface_evidence as _surface_evidence,
)
from quality_runner.fleet.maturity_dimension_support import (
    surfaces as _surfaces,
)
from quality_runner.fleet.maturity_dimension_support import (
    term_evidence as _term_evidence,
)
from quality_runner.fleet.maturity_dimension_support import (
    unknown_applicability as _unknown_applicability,
)
from quality_runner.fleet.maturity_dimension_support import (
    verification_result as _verification_result,
)
from quality_runner.security.capabilities import detect_security_capabilities
from quality_runner.web_readiness import create_web_readiness_report, has_web_surface

SPECIAL_MATURITY_DIMENSIONS = frozenset(
    {
        "accessibility",
        "artifact_supply_chain",
        "code_health",
        "compatibility_migration",
        "critical_user_journeys",
        "data_integrity_migration",
        "dependency_vulnerability",
        "license_contribution",
        "maintenance_health",
        "observability_runtime_health",
        "ownership_continuity",
        "performance",
        "reliability_resilience",
        "secret_privacy",
        "web_readiness",
    }
)


def assess_maturity_dimensions(
    *,
    root: Path,
    repository: dict[str, Any],
    scan: dict[str, Any],
    documents: dict[str, str],
    config: dict[str, Any],
    as_of: str,
) -> dict[str, dict[str, Any]]:
    """Produce surface-aware evidence for the v2 holistic maturity capabilities."""
    combined = "\n".join(documents.values()).lower()
    commands = _commands(scan)
    surfaces = _surfaces(scan)
    assessments = {
        **_correctness_assessments(commands, surfaces, combined),
        **_security_assessments(scan, commands, combined),
        **_maintainability_assessments(commands, surfaces, combined),
        **_operability_assessments(root, commands, surfaces, combined),
        **_governance_assessments(root, repository, scan, documents, combined),
        **_web_assessments(root, config, as_of),
    }
    missing = SPECIAL_MATURITY_DIMENSIONS - assessments.keys()
    if missing:
        raise ValueError(f"maturity dimension assessments are missing: {sorted(missing)}")
    return assessments


def _correctness_assessments(
    commands: dict[str, list[dict[str, Any]]],
    surfaces: list[dict[str, str]],
    text: str,
) -> dict[str, dict[str, Any]]:
    test_evidence = _command_evidence(commands, ("tests", "runtime_smoke"))
    has_tests = bool(commands.get("tests"))
    has_smoke = bool(commands.get("runtime_smoke"))
    reliability_terms = _matched_terms(text, DIMENSION_TERMS["reliability_resilience"])
    reliability_score = min(4, int(has_tests) * 2 + int(has_smoke) + int(bool(reliability_terms)))
    reliability = _assessment(
        reliability_score,
        _status(reliability_score),
        "Reliability evidence combines automated tests, runtime smoke checks, and resilience contracts.",
        [*test_evidence, *_term_evidence(reliability_terms)],
    )

    migration_surface = next((item for item in surfaces if item.get("id") == "db_migrations"), None)
    if migration_surface is None:
        data_integrity = _not_applicable(
            "No database migration surface was detected.",
            [{"path": ".", "detail": "No supported migration directory was found."}],
        )
    else:
        migration_terms = _matched_terms(text, DIMENSION_TERMS["data_integrity_migration"])
        score = 1 + int(bool(migration_terms)) + int(has_tests) + int("rollback" in text)
        data_integrity = _assessment(
            min(score, 4),
            _status(min(score, 4)),
            "Data-integrity maturity reflects migration, rollback, and test evidence.",
            [
                _surface_evidence(migration_surface),
                *_term_evidence(migration_terms),
                *test_evidence,
            ],
        )
    return {
        "reliability_resilience": reliability,
        "data_integrity_migration": data_integrity,
    }


def _security_assessments(
    scan: dict[str, Any],
    commands: dict[str, list[dict[str, Any]]],
    text: str,
) -> dict[str, dict[str, Any]]:
    available, missing = detect_security_capabilities(
        scan=scan,
        standards_packet={"config": {}},
        config={},
    )
    dependency = _security_capability_assessment(
        "security_dependency_audit", available, missing, "dependency and vulnerability"
    )

    has_source = bool(scan.get("languages"))
    if not has_source:
        secret_privacy = _not_applicable(
            "No supported source-code surface was detected.",
            [{"path": ".", "detail": "The repository has no detected source language."}],
        )
    else:
        secret = _capability_item("security_secrets_scan", available)
        privacy_terms = _matched_terms(text, DIMENSION_TERMS["secret_privacy"])
        result = _verification_result(secret)
        score = (
            4
            if result == "passed" and privacy_terms
            else 3
            if secret is not None and privacy_terms
            else 2
            if secret is not None
            else 1
            if privacy_terms
            else 0
        )
        secret_privacy = _assessment(
            score,
            "blocked" if result == "failed" else _status(score),
            "Secret scanning and privacy handling are assessed together without exposing source values.",
            [*_capability_evidence(secret), *_term_evidence(privacy_terms)],
        )

    has_build = bool(commands.get("build"))
    supply_terms = _matched_terms(text, DIMENSION_TERMS["artifact_supply_chain"])
    if not has_build and not supply_terms:
        supply_chain = _not_applicable(
            "No artifact build or distribution surface was detected.",
            [{"path": ".", "detail": "No build command or provenance contract was found."}],
        )
    else:
        ci_present = bool(scan.get("ci_files"))
        score = int(has_build) + int(ci_present) + min(2, len(supply_terms))
        supply_chain = _assessment(
            min(score, 4),
            _status(min(score, 4)),
            "Artifact maturity combines build automation, CI, and provenance or signing evidence.",
            [
                *_command_evidence(commands, ("build",)),
                *_path_evidence(scan.get("ci_files"), "CI surface"),
                *_term_evidence(supply_terms),
            ],
        )
    return {
        "dependency_vulnerability": dependency,
        "secret_privacy": secret_privacy,
        "artifact_supply_chain": supply_chain,
    }


def _maintainability_assessments(
    commands: dict[str, list[dict[str, Any]]],
    surfaces: list[dict[str, str]],
    text: str,
) -> dict[str, dict[str, Any]]:
    health_ids = ("formatter", "lint", "typecheck", "dead_code")
    covered = sum(bool(commands.get(identifier)) for identifier in health_ids)
    code_health = _assessment(
        covered,
        _status(covered),
        "Code health is language-neutral and reflects formatting, linting, typing, and dead-code gates.",
        _command_evidence(commands, health_ids),
    )

    contract_surfaces = [
        item for item in surfaces if item.get("kind") in {"database", "service_contract"}
    ]
    terms = _matched_terms(text, DIMENSION_TERMS["compatibility_migration"])
    if not contract_surfaces and not terms:
        compatibility = _not_applicable(
            "No versioned contract or migration surface was detected.",
            [{"path": ".", "detail": "No API, protocol, or migration contract was found."}],
        )
    else:
        has_tests = bool(commands.get("tests"))
        score = min(4, int(bool(contract_surfaces)) + min(2, len(terms)) + int(has_tests))
        compatibility = _assessment(
            score,
            _status(score),
            "Compatibility maturity reflects versioned surfaces, migration guidance, and tests.",
            [
                *[_surface_evidence(item) for item in contract_surfaces[:8]],
                *_term_evidence(terms),
                *_command_evidence(commands, ("tests",)),
            ],
        )
    return {"code_health": code_health, "compatibility_migration": compatibility}


def _operability_assessments(
    root: Path,
    commands: dict[str, list[dict[str, Any]]],
    surfaces: list[dict[str, str]],
    text: str,
) -> dict[str, dict[str, Any]]:
    runtime_surfaces = [
        item for item in surfaces if item.get("kind") in {"runtime", "infrastructure"}
    ]
    has_deployment = any((root / marker).exists() for marker in DEPLOYMENT_MARKERS)
    if not runtime_surfaces and not has_deployment:
        observability = _not_applicable(
            "No deployed runtime or infrastructure surface was detected.",
            [{"path": ".", "detail": "Observability is conditional on an operated runtime."}],
        )
    else:
        terms = _matched_terms(text, DIMENSION_TERMS["observability_runtime_health"])
        has_smoke = bool(commands.get("runtime_smoke"))
        score = min(
            4, int(bool(runtime_surfaces) or has_deployment) + min(2, len(terms)) + int(has_smoke)
        )
        observability = _assessment(
            score,
            _status(score),
            "Runtime health reflects observability contracts and executable smoke checks.",
            [
                *[_surface_evidence(item) for item in runtime_surfaces[:8]],
                *_term_evidence(terms),
                *_command_evidence(commands, ("runtime_smoke",)),
            ],
        )
    return {"observability_runtime_health": observability}


def _governance_assessments(
    root: Path,
    repository: dict[str, Any],
    scan: dict[str, Any],
    documents: dict[str, str],
    text: str,
) -> dict[str, dict[str, Any]]:
    ownership_paths = _existing_paths(root, ("CODEOWNERS", ".github/CODEOWNERS", "MAINTAINERS"))
    ownership_terms = _matched_terms(text, DIMENSION_TERMS["ownership_continuity"])
    ownership_score = min(4, len(ownership_paths) * 2 + min(2, len(ownership_terms)))
    ownership = _assessment(
        ownership_score,
        _status(ownership_score),
        "Ownership continuity requires discoverable maintainers or repository ownership contracts.",
        [*_path_evidence(ownership_paths, "ownership contract"), *_term_evidence(ownership_terms)],
    )

    maintenance_terms = _matched_terms(text, DIMENSION_TERMS["maintenance_health"])
    reviewed_docs = [path for path, value in documents.items() if "last reviewed" in value.lower()]
    ci_present = bool(scan.get("ci_files"))
    maintenance_score = min(
        4, int(ci_present) + min(2, len(maintenance_terms)) + int(bool(reviewed_docs))
    )
    maintenance = _assessment(
        maintenance_score,
        _status(maintenance_score),
        "Maintenance continuity combines CI, review freshness, and maintenance or release evidence.",
        [
            *_path_evidence(scan.get("ci_files"), "CI surface"),
            *_path_evidence(reviewed_docs, "reviewed documentation"),
            *_term_evidence(maintenance_terms),
        ],
    )

    license_paths = _existing_paths(
        root,
        (
            "LICENSE",
            "LICENSE.md",
            "LICENSE.txt",
            "COPYING",
            "CONTRIBUTING.md",
            ".github/CONTRIBUTING.md",
        ),
    )
    license_terms = _matched_terms(text, DIMENSION_TERMS["license_contribution"])
    origin = repository.get("identity_provenance")
    has_origin = isinstance(origin, dict) and bool(origin.get("normalized_origin"))
    if not license_paths and not license_terms and not has_origin:
        license_contract = _not_applicable(
            "No external distribution origin or contribution surface was detected.",
            [{"path": ".", "detail": "License and contribution controls are conditional."}],
        )
    elif not license_paths and not license_terms:
        license_contract = _unknown_applicability(
            "Repository visibility is unknown, so license and contribution applicability cannot be inferred.",
            [{"path": ".", "detail": "Declare or document the distribution boundary."}],
        )
    else:
        score = min(4, len(license_paths) + min(2, len(license_terms)))
        license_contract = _assessment(
            score,
            _status(score),
            "License and contribution maturity reflects repository-owned policy surfaces.",
            [*_path_evidence(license_paths, "policy surface"), *_term_evidence(license_terms)],
        )
    return {
        "ownership_continuity": ownership,
        "maintenance_health": maintenance,
        "license_contribution": license_contract,
    }


def _web_assessments(root: Path, config: dict[str, Any], as_of: str) -> dict[str, dict[str, Any]]:
    web_config = config.get("web_readiness")
    configured = dict(web_config) if isinstance(web_config, dict) else {}
    if configured.get("applicability") == "not_applicable" or not has_web_surface(root):
        reason = str(configured.get("reason") or "No supported web source surface was detected.")
        return {
            dimension: _not_applicable(reason, [{"path": ".", "detail": reason}])
            for dimension in (
                "accessibility",
                "performance",
                "critical_user_journeys",
                "web_readiness",
            )
        }
    if configured.get("applicability") not in {"public_web", "internal_web"}:
        configured["applicability"] = "internal_web"
    report = create_web_readiness_report(
        root,
        config={"web_readiness": configured},
        generated_at=as_of,
    )
    checks = [item for item in report.get("checks", []) if isinstance(item, dict)]
    groups = {
        "accessibility": {
            "document_language",
            "image_alternatives",
            "route_titles",
            "primary_heading",
        },
        "performance": {"javascript_bundle_budget"},
        "critical_user_journeys": {"deployment_route_coverage", "console_errors", "asset_errors"},
        "web_readiness": {str(item.get("id")) for item in checks},
    }
    return {
        dimension: _web_check_assessment(checks, identifiers, dimension)
        for dimension, identifiers in groups.items()
    }


def _web_check_assessment(
    checks: list[dict[str, Any]], identifiers: set[str], dimension: str
) -> dict[str, Any]:
    selected = [item for item in checks if item.get("id") in identifiers]
    if not selected:
        return _assessment(
            None,
            "unknown",
            f"No {dimension.replace('_', ' ')} checks were produced by web readiness.",
            [],
        )
    statuses = [str(item.get("status", "unknown")) for item in selected]
    passed = statuses.count("passed")
    if passed == len(selected):
        score, status = 4, "maintained"
    elif any(item in {"failed", "blocked"} for item in statuses):
        score, status = round(4 * passed / len(selected)), "attention"
    else:
        score, status = (3 if passed else 1), "unknown"
    evidence = [
        {
            "path": f"web-readiness:{item.get('id', 'check')}",
            "detail": str(item.get("detail", "Web-readiness evidence."))[:240],
        }
        for item in selected[:16]
    ]
    return _assessment(
        score,
        status,
        f"{dimension.replace('_', ' ').title()} is projected from quality-runner-web-readiness/v1 checks.",
        evidence,
    )


def _security_capability_assessment(
    capability_id: str,
    available: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    label: str,
) -> dict[str, Any]:
    item = _capability_item(capability_id, available)
    if item is None and _capability_item(capability_id, missing) is None:
        return _not_applicable(
            f"No {label} surface was detected.",
            [{"path": ".", "detail": f"{label.title()} checks are conditional."}],
        )
    result = _verification_result(item)
    score = 4 if result == "passed" else 0 if result == "failed" else 2 if item else 0
    return _assessment(
        score,
        "blocked" if result == "failed" else _status(score),
        f"{label.title()} evidence reuses the Quality Runner security capability detector.",
        _capability_evidence(item or _capability_item(capability_id, missing)),
    )
