"""Evidence contracts for reviewing and safely reducing a test portfolio."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PORTFOLIO_INPUT_SCHEMA = "quality-runner-test-portfolio-input/v1"
PORTFOLIO_AUDIT_SCHEMA = "quality-runner-test-portfolio-audit/v1"
REMOVAL_INPUT_SCHEMA = "quality-runner-test-removal-proof-input/v1"
REMOVAL_PROOF_SCHEMA = "quality-runner-test-removal-proof/v1"

_RECOMMENDATIONS = {"keep", "merge", "rewrite", "delete_candidate", "unknown"}
_REMOVABLE_DISPOSITIONS = {"merge", "delete_candidate"}


def load_test_portfolio_json(path: Path) -> dict[str, Any]:
    """Load a local JSON object without interpreting paths inside it."""

    resolved = path.expanduser().resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {resolved}")
    return payload


def write_test_portfolio_json(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write deterministic JSON only to the caller's explicit output path."""

    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return resolved


def audit_test_portfolio(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Turn caller-assembled test evidence into bounded review dispositions."""

    tests = _validate_portfolio_manifest(manifest)
    behavior_owners: dict[str, list[str]] = defaultdict(list)
    for test in tests:
        for behavior in test["behaviors"]:
            behavior_owners[behavior].append(test["id"])
    behavior_map = {
        behavior: sorted(owners) for behavior, owners in sorted(behavior_owners.items())
    }

    candidates = [
        _portfolio_candidate(test, behavior_owners=behavior_map, known_ids={t["id"] for t in tests})
        for test in tests
    ]
    disposition_counts = Counter(candidate["disposition"] for candidate in candidates)
    artifact: dict[str, Any] = {
        "schema": PORTFOLIO_AUDIT_SCHEMA,
        "status": "review-required",
        "implementation_allowed": False,
        "source_schema": PORTFOLIO_INPUT_SCHEMA,
        "repository": dict(manifest["repository"]),
        "revision": dict(manifest["revision"]),
        "input_hash": _canonical_hash(manifest),
        "coverage": {
            "test_count": len(tests),
            "behavior_count": len(behavior_map),
            "behavior_mapped_tests": sum(bool(test["behaviors"]) for test in tests),
            "reviewed_tests": sum(bool(test["reviewers"]) for test in tests),
            "dynamic_signal_tests": sum(bool(test["unique_signals"]) for test in tests),
        },
        "behavior_owners": behavior_map,
        "summary": {
            "dispositions": dict(sorted(disposition_counts.items())),
            "removal_candidates": sum(
                candidate["disposition"] in _REMOVABLE_DISPOSITIONS for candidate in candidates
            ),
            "proof_required": True,
        },
        "candidates": candidates,
        "authority": {
            "reviewer_recommendations_are_evidence": True,
            "reviewer_recommendations_authorize_removal": False,
            "removal_requires": REMOVAL_PROOF_SCHEMA,
        },
    }
    artifact["audit_hash"] = _canonical_hash(artifact, exclude=("audit_hash",))
    return artifact


def build_test_removal_proof(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless exact-revision evidence preserves the tested signals."""

    audit, removed_ids = _validate_removal_manifest(manifest)
    revision = manifest["revision"]
    suite = manifest["suite"]
    mutation = manifest.get("mutation")
    defect_replays = manifest.get("defective_revisions", [])
    impact_map = manifest.get("impact_map")
    candidates = {item["test_id"]: item for item in audit["candidates"]}

    checks: list[dict[str, Any]] = []
    _check(
        checks,
        "clean-exact-revisions",
        revision.get("worktree_clean") is True
        and _nonempty(revision.get("base"))
        and _nonempty(revision.get("head"))
        and revision.get("base") != revision.get("head")
        and audit["revision"].get("head") == revision.get("base"),
        "The proof binds a clean baseline audit to distinct base and head revisions.",
    )
    _check(
        checks,
        "candidate-eligibility",
        all(
            candidates[test_id]["disposition"] in _REMOVABLE_DISPOSITIONS
            and not candidates[test_id]["unique_behaviors"]
            and not candidates[test_id]["unique_signals"]
            and candidates[test_id]["critical_contract"] is False
            for test_id in removed_ids
        ),
        "Every removed test was a non-critical merge/delete candidate with no unique signal.",
    )
    _check(
        checks,
        "suite-replay",
        _suite_passes(suite.get("baseline"), revision.get("base"))
        and _suite_passes(suite.get("current"), revision.get("head")),
        "The declared full suite passed at both exact revisions.",
    )

    mutation_present = isinstance(mutation, Mapping)
    if mutation_present:
        _check(
            checks,
            "mutation-preservation",
            _mutation_preserved(mutation, revision),
            "A complete, stable-target mutation comparison added no survivors or uncovered mutants.",
        )
    defects_present = isinstance(defect_replays, list) and bool(defect_replays)
    if defects_present:
        _check(
            checks,
            "defect-replay-preservation",
            _defects_preserved(defect_replays, revision),
            "Every declared defective revision remained detected before and after removal.",
        )
    _check(
        checks,
        "dynamic-removal-evidence",
        mutation_present or defects_present,
        "At least one mutation comparison or defective-revision replay is present.",
    )
    if isinstance(impact_map, Mapping):
        _check(
            checks,
            "impact-map-preservation",
            impact_map.get("status") == "complete"
            and impact_map.get("uncovered_dependencies") == [],
            "The optional per-test impact map reports complete coverage and no newly uncovered dependency.",
        )

    blockers = [check["id"] for check in checks if check["passed"] is False]
    status = "passed" if not blockers else "blocked"
    proof: dict[str, Any] = {
        "schema": REMOVAL_PROOF_SCHEMA,
        "status": status,
        "implementation_allowed": False,
        "source_schema": REMOVAL_INPUT_SCHEMA,
        "repository": dict(manifest["repository"]),
        "revision": dict(revision),
        "portfolio_audit_hash": audit["audit_hash"],
        "removed_test_ids": removed_ids,
        "checks": checks,
        "blockers": blockers,
        "summary": {
            "removed_test_count": len(removed_ids),
            "dynamic_evidence_channels": sum((mutation_present, defects_present)),
            "unique_signal_loss": False if not blockers else "unknown",
        },
        "authority": {
            "proof_is_evidence": True,
            "proof_executes_removal": False,
            "proof_authorizes_source_mutation": False,
        },
        "input_hash": _canonical_hash(manifest),
    }
    proof["proof_hash"] = _canonical_hash(proof, exclude=("proof_hash",))
    return proof


def _validate_portfolio_manifest(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema") != PORTFOLIO_INPUT_SCHEMA:
        raise ValueError(f"manifest schema must be {PORTFOLIO_INPUT_SCHEMA}")
    _require_mapping(manifest.get("repository"), "repository")
    revision = _require_mapping(manifest.get("revision"), "revision")
    if not _nonempty(revision.get("head")):
        raise ValueError("revision.head must be a non-empty exact revision")
    raw_tests = manifest.get("tests")
    if not isinstance(raw_tests, list) or not raw_tests:
        raise ValueError("tests must be a non-empty array")

    tests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_tests):
        item = _require_mapping(raw, f"tests[{index}]")
        test_id = _required_text(item.get("id"), f"tests[{index}].id")
        if test_id in seen:
            raise ValueError(f"duplicate test id: {test_id}")
        seen.add(test_id)
        path = _required_text(item.get("path"), f"tests[{index}].path")
        reviewers = _normalize_reviewers(item.get("reviewers", []), test_id=test_id)
        tests.append(
            {
                "id": test_id,
                "path": path,
                "behaviors": _string_list(item.get("behaviors", []), f"{test_id}.behaviors"),
                "reviewers": reviewers,
                "unique_signals": _string_list(
                    item.get("unique_signals", []), f"{test_id}.unique_signals"
                ),
                "duplicate_of": _string_list(
                    item.get("duplicate_of", []), f"{test_id}.duplicate_of"
                ),
                "evidence_gaps": _string_list(
                    item.get("evidence_gaps", []), f"{test_id}.evidence_gaps"
                ),
                "critical_contract": item.get("critical_contract") is True,
                "runtime_seconds": _optional_nonnegative_number(
                    item.get("runtime_seconds"), f"{test_id}.runtime_seconds"
                ),
                "flaky": item.get("flaky") is True,
            }
        )
    return sorted(tests, key=lambda item: item["id"])


def _portfolio_candidate(
    test: Mapping[str, Any], *, behavior_owners: Mapping[str, list[str]], known_ids: set[str]
) -> dict[str, Any]:
    unique_behaviors = sorted(
        behavior for behavior in test["behaviors"] if behavior_owners.get(behavior) == [test["id"]]
    )
    duplicate_targets = sorted(target for target in test["duplicate_of"] if target in known_ids)
    recommendations = {review["recommendation"] for review in test["reviewers"]}
    deletion_reviewers = {
        review["reviewer"]
        for review in test["reviewers"]
        if review["recommendation"] == "delete_candidate"
    }
    conflict = "delete_candidate" in recommendations and "keep" in recommendations
    evidence_needed = list(test["evidence_gaps"])

    if test["critical_contract"] or unique_behaviors or test["unique_signals"]:
        disposition, confidence = "keep", "high"
        rationale = "The test protects a critical contract or a signal not attributed elsewhere."
    elif conflict:
        disposition, confidence = "insufficient_evidence", "low"
        rationale = "Independent reviewers disagree about whether the test should remain."
        evidence_needed.append("Resolve the reviewer disagreement with behavior-level evidence.")
    elif duplicate_targets:
        disposition, confidence = "merge", "medium"
        rationale = (
            "The manifest identifies another test for the same behavior and no unique signal."
        )
        evidence_needed.append(
            "Prove the target test preserves mutation or defective-revision detection."
        )
    elif len(deletion_reviewers) >= 2 and (
        not test["behaviors"]
        or all(len(behavior_owners.get(behavior, [])) > 1 for behavior in test["behaviors"])
    ):
        disposition, confidence = "delete_candidate", "medium"
        rationale = (
            "At least two independent reviewers nominate removal, while the behavior map "
            "attributes no unique protected signal to this test."
        )
        evidence_needed.append("Generate an exact-revision dynamic removal proof before deletion.")
    elif "rewrite" in recommendations:
        disposition, confidence = "rewrite", "medium"
        rationale = (
            "Review evidence identifies value that should be preserved through a clearer test."
        )
    else:
        disposition, confidence = "insufficient_evidence", "low"
        rationale = "The supplied static and review evidence does not justify a portfolio change."
        evidence_needed.append(
            "Map the test to behavior and add dynamic evidence or a second review."
        )

    return {
        "test_id": test["id"],
        "path": test["path"],
        "disposition": disposition,
        "confidence": confidence,
        "rationale": rationale,
        "behaviors": list(test["behaviors"]),
        "unique_behaviors": unique_behaviors,
        "unique_signals": list(test["unique_signals"]),
        "duplicate_targets": duplicate_targets,
        "critical_contract": test["critical_contract"],
        "runtime_seconds": test["runtime_seconds"],
        "flaky": test["flaky"],
        "reviewers": list(test["reviewers"]),
        "evidence_needed": sorted(set(evidence_needed)),
    }


def _validate_removal_manifest(
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if manifest.get("schema") != REMOVAL_INPUT_SCHEMA:
        raise ValueError(f"manifest schema must be {REMOVAL_INPUT_SCHEMA}")
    _require_mapping(manifest.get("repository"), "repository")
    _require_mapping(manifest.get("revision"), "revision")
    _require_mapping(manifest.get("suite"), "suite")
    audit = dict(_require_mapping(manifest.get("portfolio_audit"), "portfolio_audit"))
    if audit.get("schema") != PORTFOLIO_AUDIT_SCHEMA:
        raise ValueError("portfolio_audit schema is invalid")
    if audit.get("audit_hash") != _canonical_hash(audit, exclude=("audit_hash",)):
        raise ValueError("portfolio_audit hash does not match its contents")
    removed_ids = sorted(
        set(_string_list(manifest.get("removed_test_ids", []), "removed_test_ids"))
    )
    if not removed_ids:
        raise ValueError("removed_test_ids must be a non-empty array")
    known = {
        item.get("test_id")
        for item in audit.get("candidates", [])
        if isinstance(item, Mapping) and isinstance(item.get("test_id"), str)
    }
    missing = sorted(set(removed_ids) - known)
    if missing:
        raise ValueError("removed tests missing from portfolio audit: " + ", ".join(missing))
    return audit, removed_ids


def _suite_passes(value: Any, revision: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("revision") == revision
        and value.get("status") == "passed"
        and isinstance(value.get("test_count"), int)
        and value["test_count"] >= 0
    )


def _mutation_preserved(value: Mapping[str, Any], revision: Mapping[str, Any]) -> bool:
    baseline = value.get("baseline")
    current = value.get("current")
    if not isinstance(baseline, Mapping) or not isinstance(current, Mapping):
        return False
    numeric_keys = ("killed", "survived", "no_coverage")
    return bool(
        value.get("status") == "complete"
        and _nonempty(value.get("target_set_hash"))
        and baseline.get("target_set_hash") == value.get("target_set_hash")
        and current.get("target_set_hash") == value.get("target_set_hash")
        and baseline.get("revision") == revision.get("base")
        and current.get("revision") == revision.get("head")
        and all(isinstance(baseline.get(key), int) for key in numeric_keys)
        and all(isinstance(current.get(key), int) for key in numeric_keys)
        and current["survived"] <= baseline["survived"]
        and current["no_coverage"] <= baseline["no_coverage"]
    )


def _defects_preserved(value: Sequence[Any], revision: Mapping[str, Any]) -> bool:
    return all(
        isinstance(item, Mapping)
        and _nonempty(item.get("id"))
        and item.get("baseline_revision") == revision.get("base")
        and item.get("current_revision") == revision.get("head")
        and item.get("baseline_status") == "detected"
        and item.get("current_status") == "detected"
        for item in value
    )


def _normalize_reviewers(value: Any, *, test_id: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"{test_id}.reviewers must be an array")
    reviewers: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _require_mapping(raw, f"{test_id}.reviewers[{index}]")
        reviewer = _required_text(item.get("reviewer"), f"{test_id}.reviewer")
        if reviewer in seen:
            raise ValueError(f"duplicate reviewer for {test_id}: {reviewer}")
        seen.add(reviewer)
        recommendation = _required_text(item.get("recommendation"), f"{test_id}.recommendation")
        if recommendation not in _RECOMMENDATIONS:
            raise ValueError(f"unsupported recommendation for {test_id}: {recommendation}")
        reviewers.append(
            {
                "reviewer": reviewer,
                "recommendation": recommendation,
                "rationale": _required_text(item.get("rationale"), f"{test_id}.rationale"),
            }
        )
    return sorted(reviewers, key=lambda item: item["reviewer"])


def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, evidence: str) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "evidence": evidence})


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not _nonempty(item) for item in value):
        raise ValueError(f"{label} must be an array of non-empty strings")
    return sorted(set(str(item) for item in value))


def _optional_nonnegative_number(value: Any, label: str) -> int | float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative number")
    return value


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _required_text(value: Any, label: str) -> str:
    if not _nonempty(value):
        raise ValueError(f"{label} must be a non-empty string")
    return str(value)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical_hash(value: Any, *, exclude: Sequence[str] = ()) -> str:
    if isinstance(value, Mapping):
        omitted = set(exclude)
        value = {str(key): item for key, item in value.items() if str(key) not in omitted}
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
