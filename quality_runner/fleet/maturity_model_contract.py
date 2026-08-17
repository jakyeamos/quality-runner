from __future__ import annotations

from typing import Any

REPOSITORY_MATURITY_SCHEMA = "quality-runner-repository-maturity/v2"

PILLAR_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "correctness_reliability",
        "label": "Correctness and reliability",
        "weight": 0.22,
        "applicability": "required",
        "capabilities": {
            "automated_quality_gates": {
                "applicability": "required",
                "patterns": ("quality_commands", "dynamic_verification"),
            },
            "behavior_outcomes": {
                "applicability": "required",
                "patterns": ("behavior_assurance", "behavior_"),
            },
            "reliability_and_resilience": {
                "applicability": "required",
                "patterns": ("reliability_resilience",),
            },
            "data_integrity_and_migration": {
                "applicability": "conditional",
                "patterns": ("data_integrity_migration",),
            },
        },
    },
    {
        "id": "security_privacy_supply_chain",
        "label": "Security, privacy, and supply chain",
        "weight": 0.22,
        "applicability": "required",
        "capabilities": {
            "security_constraints": {
                "applicability": "required",
                "patterns": ("security_constraints", "approval_gated_paths"),
            },
            "dependency_and_vulnerability_risk": {
                "applicability": "conditional",
                "patterns": ("dependency_vulnerability",),
            },
            "secret_and_privacy_controls": {
                "applicability": "conditional",
                "patterns": ("secret_privacy",),
            },
            "artifact_provenance": {
                "applicability": "conditional",
                "patterns": ("artifact_supply_chain",),
            },
        },
    },
    {
        "id": "maintainability_evolvability",
        "label": "Maintainability and evolvability",
        "weight": 0.16,
        "applicability": "required",
        "capabilities": {
            "architecture_boundaries": {
                "applicability": "required",
                "patterns": ("architecture_boundaries",),
            },
            "change_impact_contract": {
                "applicability": "required",
                "patterns": ("change_surface_coverage",),
            },
            "coding_and_type_health": {
                "applicability": "required",
                "patterns": (
                    "code_health",
                    "coding_conventions",
                    "strict_policy_visibility",
                    "strict_type_debt",
                ),
            },
            "compatibility_and_migration": {
                "applicability": "conditional",
                "patterns": ("compatibility_migration",),
            },
        },
    },
    {
        "id": "operability_release_safety",
        "label": "Operability and release safety",
        "weight": 0.14,
        "applicability": "required",
        "capabilities": {
            "failure_and_recovery_contract": {
                "applicability": "required",
                "patterns": ("failure_modes", "deployment_rollback"),
            },
            "diagnosability": {
                "applicability": "conditional",
                "patterns": ("diagnosability.",),
            },
            "operational_observability": {
                "applicability": "conditional",
                "patterns": (
                    "observability_runtime_health",
                    "long_running_task_observability",
                    "long_running_task_optimization",
                ),
            },
        },
    },
    {
        "id": "user_facing_quality",
        "label": "User-facing quality",
        "weight": 0.10,
        "applicability": "conditional",
        "capabilities": {
            "accessible_experience": {
                "applicability": "conditional",
                "patterns": ("accessibility",),
            },
            "performance_evidence": {
                "applicability": "conditional",
                "patterns": ("performance",),
            },
            "critical_user_journeys": {
                "applicability": "conditional",
                "patterns": ("critical_user_journeys",),
            },
            "holistic_web_readiness": {
                "applicability": "conditional",
                "patterns": ("web_readiness",),
            },
        },
    },
    {
        "id": "human_agent_usability",
        "label": "Human and agent usability",
        "weight": 0.10,
        "applicability": "agent_conditional",
        "capabilities": {
            "documentation_contract": {
                "applicability": "agent_conditional",
                "patterns": (
                    "implementation_examples",
                    "agent_usability.documentation_contract",
                ),
            },
            "tool_skill_coverage": {
                "applicability": "agent_conditional",
                "patterns": (
                    "skill_contract_quality",
                    "agent_usability.tool_skill_coverage",
                ),
            },
            "behavior_evidence": {
                "applicability": "agent_conditional",
                "patterns": ("agent_usability.behavior_evidence",),
            },
            "routing_and_portability": {
                "applicability": "agent_conditional",
                "patterns": (
                    "context_routing",
                    "agent_usability.freshness_portability",
                ),
            },
        },
    },
    {
        "id": "governance_sustainability",
        "label": "Governance and sustainability",
        "weight": 0.06,
        "applicability": "conditional",
        "capabilities": {
            "ownership_continuity": {
                "applicability": "required",
                "patterns": ("ownership_continuity",),
            },
            "maintenance_continuity": {
                "applicability": "required",
                "patterns": ("maintenance_health",),
            },
            "license_and_contribution": {
                "applicability": "conditional",
                "patterns": ("license_contribution",),
            },
            "completion_and_matrix_discipline": {
                "applicability": "required",
                "patterns": ("definition_of_done", "matrix_maintenance"),
            },
        },
    },
)
