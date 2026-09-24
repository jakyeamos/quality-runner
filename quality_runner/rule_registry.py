from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from quality_runner.config import load_repo_config
from quality_runner.skill_config import load_active_skills

RULE_REGISTRY_SCHEMA = "quality-runner-rule-registry/v1"
VERIFICATION_KINDS = ("positive", "negative", "boundary")


# Exact built-in rule identifiers emitted by the code-quality detector. Keep this
# list declarative so consumers do not need to scrape implementation source.
BUILTIN_CODE_QUALITY_RULES = frozenset(
    {
        "api-route-missing-boundary-validation",
        "arbitrary-z-index",
        "await-in-loop",
        "bare-trpc-error",
        "console-output",
        "dead-code-unwired-candidate",
        "decorative-grid-background",
        "deep-nesting",
        "deep-prop-drilling",
        "env-non-null-assertion",
        "eval-user-code",
        "exact-duplicate-test-body",
        "excessive-border-radius",
        "explicit-any",
        "export-without-references",
        "fat-router",
        "gradient-text",
        "hand-rolled-csv-parser",
        "hand-rolled-debounce",
        "hand-rolled-url-parser",
        "hand-rolled-uuid",
        "handler-without-registration",
        "hero-image-lazy-loading",
        "icon-button-missing-label",
        "image-missing-alt",
        "image-missing-dimensions",
        "inconsistent-error-envelope",
        "large-js-bundle-artifact",
        "large-source-file",
        "list-endpoint-missing-pagination",
        "maintenance-compatibility-surface",
        "maintenance-config-surface",
        "maintenance-new-dependency",
        "maintenance-public-surface",
        "missing-empty-state",
        "missing-error-state",
        "missing-loading-state",
        "missing-reduced-motion",
        "near-duplicate-function",
        "nested-card-markup",
        "nested-ternary",
        "nonsemantic-click-target",
        "off-scale-spacing",
        "page-data-access",
        "pass-through-wrapper",
        "placeholder-copy",
        "positive-tabindex",
        "python-blocking-call-in-async",
        "python-query-in-loop",
        "python-sync-work-call-in-async",
        "raw-free-text-z-string",
        "removed-behavior-lock",
        "removed-focus-outline",
        "risky-hidden-reveal",
        "semantic-similarity-cluster",
        "semantic-similarity-pair",
        "side-stripe-border",
        "silent-catch",
        "silent-except-pass",
        "single-implementation-abstraction",
        "single-product-factory",
        "single-use-trivial-dependency",
        "sql-string-interpolation",
        "stub-implementation",
        "todo-comment",
        "todo-scaffold",
        "ts-ignore",
        "undocumented-env-flag",
        "uninstrumented-trpc-procedure",
        "unsafe-html-injection",
        "user-controlled-file-path",
        "user-controlled-shell-command",
        "weak-test-assertion",
        "wildcard-cors-origin",
    }
)


# These families cannot be reduced to a finite package-owned ID list because the
# repository configuration, skill pack, review packet, or evidence supplies part
# of the identifier at runtime.
DYNAMIC_RULE_FAMILIES: tuple[dict[str, str], ...] = (
    {
        "pattern": "architecture-import-boundary:<configured-rule-id>",
        "provider": "repository_config",
        "source": "quality_runner/code_quality_architecture.py",
    },
    {
        "pattern": "architecture-pattern-boundary:<configured-rule-id>:<pattern-index>",
        "provider": "repository_config",
        "source": "quality_runner/code_quality_architecture.py",
    },
    {
        "pattern": "maintenance-<observation-id>",
        "provider": "runtime_evidence",
        "source": "quality_runner/code_quality_maintenance_surface.py",
    },
    {
        "pattern": "<skill-id>/<deterministic-rule-id>",
        "provider": "skill_pack",
        "source": "quality_runner/code_quality_skills.py",
    },
    {
        "pattern": "<skill-id>/<agent-review-rule-id>",
        "provider": "skill_pack_review",
        "source": "quality_runner/skill_review.py",
    },
)


# Only rules with all three fixture classes belong here. The registry deliberately
# exposes the remaining work rather than treating ordinary scanner coverage as
# promotion evidence.
BUILTIN_RULE_TEST_EVIDENCE: dict[str, tuple[str, ...]] = {
    "large-source-file": (
        "positive:tests/test_prevention_policy.py::test_large_source_file_positive_promotion_fixture",
        "negative:tests/test_prevention_policy.py::test_large_source_file_negative_promotion_fixture",
        "boundary:tests/test_prevention_policy.py::test_large_source_file_ambiguous_test_scope_fixture_is_not_enforced",
    ),
    "nested-ternary": (
        "positive:tests/test_prevention_policy.py::test_nested_ternary_positive_promotion_fixture",
        "negative:tests/test_prevention_policy.py::test_nested_ternary_negative_promotion_fixture",
        "boundary:tests/test_code_quality.py::test_nested_ternary_rule_ignores_typescript_non_ternary_question_marks",
    ),
}


def rule_registry(repo_root: Path) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    config = load_repo_config(root)
    prevention = _mapping(config.get("prevention")) or {}
    promotion = _promotion_index(prevention)

    exact_rules = [
        _exact_rule(
            detector="code_quality",
            rule_id=rule_id,
            provider="builtin",
            source="quality_runner",
            evidence=BUILTIN_RULE_TEST_EVIDENCE.get(rule_id, ()),
            promotion=promotion.get(("code_quality", rule_id)),
        )
        for rule_id in sorted(BUILTIN_CODE_QUALITY_RULES)
    ]

    skills, skill_warnings = load_active_skills(root, config)
    for skill in sorted(skills, key=lambda item: str(item.get("id") or "")):
        skill_id = str(skill["id"])
        source = _relative_source(root, skill.get("path"))
        for rule in _mappings(skill.get("deterministic_rules")):
            rule_id = f"{skill_id}/{rule['id']}"
            exact_rules.append(
                _exact_rule(
                    detector="code_quality",
                    rule_id=rule_id,
                    provider="skill_pack",
                    source=source,
                    evidence=(),
                    promotion=promotion.get(("code_quality", rule_id)),
                )
            )
        for review in _mappings(skill.get("agent_reviews")):
            rule_id = f"{skill_id}/{review['id']}"
            exact_rules.append(
                _exact_rule(
                    detector="code_quality",
                    rule_id=rule_id,
                    provider="skill_pack_review",
                    source=source,
                    evidence=(),
                    promotion=promotion.get(("code_quality", rule_id)),
                )
            )

    exact_rules.sort(key=lambda item: (str(item["detector"]), str(item["rule_id"])))
    verified = sum(item["verification"]["status"] == "behavior-verified" for item in exact_rules)
    promoted = sum(item["promotion"]["state"] == "behavior-verified" for item in exact_rules)
    return {
        "schema": RULE_REGISTRY_SCHEMA,
        "repository": str(root),
        "exact_rules": exact_rules,
        "dynamic_rule_families": [dict(item) for item in DYNAMIC_RULE_FAMILIES],
        "warnings": [dict(item) for item in skill_warnings],
        "summary": {
            "exact_rule_count": len(exact_rules),
            "builtin_exact_rule_count": len(BUILTIN_CODE_QUALITY_RULES),
            "skill_pack_exact_rule_count": sum(
                item["provider"] in {"skill_pack", "skill_pack_review"} for item in exact_rules
            ),
            "dynamic_family_count": len(DYNAMIC_RULE_FAMILIES),
            "behavior_verified_exact_rule_count": verified,
            "unverified_exact_rule_count": len(exact_rules) - verified,
            "promoted_exact_rule_count": promoted,
        },
    }


def _exact_rule(
    *,
    detector: str,
    rule_id: str,
    provider: str,
    source: str,
    evidence: tuple[str, ...],
    promotion: dict[str, Any] | None,
) -> dict[str, Any]:
    evidence_kinds = {item.split(":", 1)[0] for item in evidence if ":" in item}
    missing = [kind for kind in VERIFICATION_KINDS if kind not in evidence_kinds]
    return {
        "detector": detector,
        "rule_id": rule_id,
        "provider": provider,
        "source": source,
        "verification": {
            "status": "behavior-verified" if not missing else "unverified",
            "evidence_refs": list(evidence),
            "missing_evidence": missing,
        },
        "promotion": {
            "state": str(promotion.get("state")) if promotion else "not-promoted",
            "owner": promotion.get("owner") if promotion else None,
            "evidence_refs": list(promotion.get("evidence_refs", [])) if promotion else [],
        },
    }


def _promotion_index(prevention: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for rule in _mappings(prevention.get("rules")):
        detector = rule.get("detector")
        rule_id = rule.get("rule_id")
        if isinstance(detector, str) and isinstance(rule_id, str):
            result[(detector, rule_id)] = rule
    return result


def _relative_source(root: Path, value: object) -> str:
    if isinstance(value, Path):
        try:
            return value.resolve().relative_to(root).as_posix()
        except ValueError:
            return "external-skill-pack"
    return "skill-pack"


def _mapping(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _mappings(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, Any], item) for item in cast(list[object], value) if isinstance(item, dict)
    ]
