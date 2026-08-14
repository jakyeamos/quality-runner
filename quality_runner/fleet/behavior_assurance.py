from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from quality_runner.fleet.behavior_contract import (
    ASSESSMENT_SCHEMA,
    CONTRACT_PATH,
    LEGACY_CONTRACT_SCHEMA,
    RECEIPT_DIRECTORY,
    RECEIPT_SCHEMA,
    RESULT_STATUSES,
    VERIFICATION_LEVELS,
)
from quality_runner.fleet.behavior_projection import coverage as _coverage
from quality_runner.fleet.behavior_projection import empty_coverage as _empty_coverage
from quality_runner.fleet.behavior_projection import requirement_key as _requirement_key
from quality_runner.fleet.behavior_support import (
    future_timestamp as _future_timestamp,
)
from quality_runner.fleet.behavior_support import gap as _gap
from quality_runner.fleet.behavior_support import git_lines as _git_lines
from quality_runner.fleet.behavior_support import is_ancestor as _is_ancestor
from quality_runner.fleet.behavior_support import iso_timestamp as _iso_timestamp
from quality_runner.fleet.behavior_support import object_value as _object
from quality_runner.fleet.behavior_support import object_values as _objects
from quality_runner.fleet.behavior_support import porcelain_path as _porcelain_path
from quality_runner.fleet.behavior_support import read_object as _read_object
from quality_runner.fleet.behavior_support import (
    receipt_evidence_errors as _receipt_evidence_errors,
)
from quality_runner.fleet.behavior_support import string_value as _string
from quality_runner.fleet.behavior_support import string_values as _strings
from quality_runner.fleet.behavior_support import target as _target
from quality_runner.fleet.behavior_validation import contract_errors as _contract_errors
from quality_runner.fleet.behavior_validation import requirements as _requirements
from quality_runner.fleet.contracts import digest

MAX_RECEIPTS = 500


def assess_behavior_assurance(
    root: Path,
    repository: dict[str, Any],
    as_of: str,
) -> dict[str, Any]:
    """Validate the behavior contract and project release and edge assurance separately."""

    contract_path = root / CONTRACT_PATH
    common: dict[str, Any] = {
        "schema": ASSESSMENT_SCHEMA,
        "contract_path": CONTRACT_PATH.as_posix(),
        "receipt_directory": RECEIPT_DIRECTORY.as_posix(),
        "observed_at": as_of,
    }
    if not contract_path.is_file() or contract_path.is_symlink():
        return _assessment(
            common,
            applicability="unknown",
            contract_status="missing",
            edge_profile_status="missing",
            result_status="unknown",
            freshness="unknown",
            score=0,
            release_ready=False,
            gaps=[_gap("contract_missing", "Add a repository-owned behavior assurance contract.")],
        )

    contract, error = _read_object(contract_path)
    if error:
        return _assessment(
            common,
            applicability="unknown",
            contract_status="invalid",
            edge_profile_status="invalid",
            result_status="blocked",
            freshness="unknown",
            score=1,
            release_ready=False,
            gaps=[_gap("contract_invalid", error)],
        )

    contract_schema = str(contract.get("schema", "unknown"))
    common["contract_schema"] = contract_schema
    common["contract_digest"] = digest(contract)
    errors = _contract_errors(contract)
    applicability = str(contract.get("applicability", "applicable"))
    if errors:
        return _assessment(
            common,
            applicability=applicability
            if applicability in {"applicable", "not_applicable"}
            else "unknown",
            contract_status="invalid",
            edge_profile_status="invalid",
            result_status="blocked",
            freshness="unknown",
            score=1,
            release_ready=False,
            gaps=[_gap("contract_invalid", item) for item in errors[:24]],
        )
    if applicability == "not_applicable":
        return _assessment(
            common,
            applicability="not_applicable",
            contract_status="current",
            edge_profile_status="not_applicable",
            result_status="not_applicable",
            freshness="current",
            score=None,
            release_ready=True,
            gaps=[],
            detail=str(contract["reason"]).strip(),
        )

    requirements = _requirements(contract)
    empty_outcomes = {
        _requirement_key(item): {
            "status": "unknown",
            "kind": "receipt_missing",
            "message": "No trusted receipt covers this scenario.",
        }
        for item in requirements
    }
    target = _target(repository, root)
    common["target_branch"] = target["branch"]
    common["target_commit"] = target["commit"]
    if not target["branch"] or not target["commit"]:
        coverage = _coverage(requirements, empty_outcomes, contract_schema)
        return _assessment(
            common,
            applicability="applicable",
            contract_status="current",
            edge_profile_status=coverage["profile_status"],
            result_status="blocked",
            freshness="unknown",
            score=2,
            release_ready=False,
            coverage=coverage,
            gaps=[
                _gap(
                    "target_unknown",
                    "The target branch and commit must be known before receipts can be trusted.",
                )
            ],
        )

    receipts, receipt_errors = _load_receipts(root, common["contract_digest"], contract)
    dirty_lines = _git_lines(root, "status", "--porcelain=v1", "--untracked-files=all")
    dirty_paths = [_porcelain_path(line) for line in dirty_lines if _porcelain_path(line)]
    outcomes: dict[tuple[str, str], dict[str, Any]] = {}
    for requirement in requirements:
        outcomes[_requirement_key(requirement)] = _evaluate_requirement(
            root=root,
            requirement=requirement,
            receipts=receipts,
            target_branch=str(target["branch"]),
            target_commit=str(target["commit"]),
            dirty_paths=dirty_paths,
            as_of=as_of,
        )

    release_requirements = [item for item in requirements if item["tier"] == 0 and item["required"]]
    verified: list[dict[str, Any]] = []
    gaps = [_gap("receipt_invalid", item) for item in receipt_errors[:12]]
    accepted_defects = 0
    for requirement in release_requirements:
        outcome = outcomes[_requirement_key(requirement)]
        if outcome["status"] == "passed":
            verified.append(outcome)
            accepted_defects += int(outcome.get("accepted_defect", False))
        else:
            gaps.append(
                _gap(
                    str(outcome["kind"]),
                    str(outcome["message"]),
                    behavior_id=str(requirement["behavior_id"]),
                    scenario_id=str(requirement["scenario_id"]),
                )
            )

    required_count = len(release_requirements)
    passed_count = len(verified)
    failed = any(gap["kind"] == "result_failed" for gap in gaps)
    blocked = any(
        gap["kind"] in {"result_blocked", "defect_open", "receipt_invalid"} for gap in gaps
    )
    stale = any(gap["kind"] in {"receipt_stale", "verification_level_low"} for gap in gaps)
    release_ready = required_count > 0 and passed_count == required_count and not receipt_errors
    result_status = (
        "passed" if release_ready else "failed" if failed else "blocked" if blocked else "unknown"
    )
    freshness = "current" if release_ready else "stale" if stale else "unknown"
    coverage = _coverage(requirements, outcomes, contract_schema)
    return _assessment(
        common,
        applicability="applicable",
        contract_status="current",
        edge_profile_status=coverage["profile_status"],
        result_status=result_status,
        freshness=freshness,
        score=4 if release_ready else 2 if required_count else 1,
        release_ready=release_ready,
        gaps=gaps,
        required_scenario_count=required_count,
        passed_scenario_count=passed_count,
        accepted_defect_count=accepted_defects,
        receipt_count=len(receipts),
        verified=verified,
        coverage=coverage,
        detail=(
            f"{passed_count}/{required_count} required Tier-0 scenarios have current trusted "
            f"receipts; {coverage['verified']}/{coverage['total']} total scenarios are verified."
        ),
    )


def _assessment(common: dict[str, Any], **values: Any) -> dict[str, Any]:
    gaps = values.pop("gaps", [])
    release_ready = bool(values.get("release_ready"))
    state = _state({**common, **values})
    return {
        **common,
        **values,
        "state": state,
        "required_scenario_count": values.get("required_scenario_count", 0),
        "passed_scenario_count": values.get("passed_scenario_count", 0),
        "accepted_defect_count": values.get("accepted_defect_count", 0),
        "receipt_count": values.get("receipt_count", 0),
        "verified": values.get("verified", []),
        "coverage": values.get("coverage", _empty_coverage()),
        "gaps": gaps,
        "next_step": (
            "No release-assurance action is required; review edge coverage separately."
            if release_ready
            else "Resolve the listed Tier-0 contract or receipt gaps, then rerun the fleet audit."
        ),
    }


def _state(values: dict[str, Any]) -> str:
    """Return the single onboarding state while preserving dimensional fields."""

    contract_status = str(values.get("contract_status", "unknown"))
    contract_schema = values.get("contract_schema")
    applicability = str(values.get("applicability", "unknown"))
    result_status = str(values.get("result_status", "unknown"))
    freshness = str(values.get("freshness", "unknown"))
    raw_coverage = values.get("coverage")
    coverage = raw_coverage if isinstance(raw_coverage, dict) else {}
    profile_status = str(
        values.get("edge_profile_status") or coverage.get("profile_status") or "unknown"
    )
    required_count = int(values.get("required_scenario_count", 0))
    passed_count = int(values.get("passed_scenario_count", 0))
    verified_count = int(coverage.get("verified", 0))

    if contract_status == "missing":
        return "missing_contract"
    if contract_status == "invalid" or result_status == "blocked":
        return "blocked"
    if applicability == "not_applicable":
        return "not_applicable"
    if contract_schema == LEGACY_CONTRACT_SCHEMA or profile_status == "legacy":
        return "legacy_v1"
    if result_status == "failed":
        return "failed"
    if freshness == "stale":
        return "stale"
    if (passed_count > 0 or verified_count > 0) and (
        required_count == 0 or passed_count < required_count
    ):
        return "partially_verified"
    if profile_status in {"missing", "unprofiled", "partially_profiled"}:
        return "unprofiled"
    if bool(values.get("release_ready")):
        return "current"
    return "unknown"


def _load_receipts(
    root: Path, contract_digest: str, contract: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    directory = root / RECEIPT_DIRECTORY
    if not directory.is_dir() or directory.is_symlink():
        return [], []
    approved = set(_strings(contract.get("approved_producers", ["quality-runner"])))
    receipts: list[dict[str, Any]] = []
    errors: list[str] = []
    paths = sorted(directory.glob("*.json"))
    if len(paths) > MAX_RECEIPTS:
        errors.append(f"receipt inventory exceeds the bounded limit of {MAX_RECEIPTS}")
        paths = paths[:MAX_RECEIPTS]
    for path in paths:
        receipt, error = _read_object(path)
        if error:
            errors.append(f"{path.name}: {error}")
            continue
        receipt_errors = _receipt_errors(receipt, path, contract_digest, approved)
        if receipt_errors:
            errors.extend(f"{path.name}: {item}" for item in receipt_errors)
            continue
        receipts.append(receipt)
    return receipts, errors


def _receipt_errors(
    receipt: dict[str, Any], path: Path, contract_digest: str, approved: set[str]
) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema") != RECEIPT_SCHEMA:
        errors.append(f"schema must be {RECEIPT_SCHEMA}")
    receipt_id = _string(receipt.get("receipt_id"))
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_id"}
    expected_id = f"receipt-{digest(unsigned)[:24]}"
    if receipt_id != expected_id or path.stem != expected_id:
        errors.append("receipt id and filename must match the canonical content digest")
    if receipt.get("contract_digest") != contract_digest:
        errors.append("contract_digest does not match the current behavior contract")
    producer = _object(receipt.get("producer"))
    producer_id = _string(producer.get("id"))
    if producer_id not in approved or not _string(producer.get("version")):
        errors.append("producer id is not approved or its version is missing")
    target = _object(receipt.get("target"))
    if not _string(target.get("branch")) or not _string(target.get("commit")):
        errors.append("target.branch and target.commit must be non-empty")
    if not _iso_timestamp(receipt.get("generated_at")):
        errors.append("generated_at must be an ISO-8601 timestamp")
    results = _objects(receipt.get("results"))
    if not results:
        errors.append("results must contain at least one scenario result")
    for index, result in enumerate(results):
        if not _string(result.get("behavior_id")) or not _string(result.get("scenario_id")):
            errors.append(f"results[{index}] must identify behavior_id and scenario_id")
        if result.get("status") not in RESULT_STATUSES:
            errors.append(f"results[{index}].status is unsupported")
        if result.get("verification_level") not in VERIFICATION_LEVELS:
            errors.append(f"results[{index}].verification_level is unsupported")
        if result.get("status") == "passed" and not _objects(result.get("evidence")):
            errors.append(f"results[{index}] passed without evidence")
        errors.extend(_receipt_evidence_errors(result, producer_id, index))
    return errors


def _evaluate_requirement(**values: Any) -> dict[str, Any]:
    root: Path = values["root"]
    requirement: dict[str, Any] = values["requirement"]
    candidates: list[dict[str, Any]] = []
    for receipt in values["receipts"]:
        target = receipt["target"]
        if target["branch"] != values["target_branch"]:
            continue
        for result in _objects(receipt.get("results")):
            if (
                result.get("behavior_id") == requirement["behavior_id"]
                and result.get("scenario_id") == requirement["scenario_id"]
            ):
                candidates.append({"receipt": receipt, "result": result})
    candidates.sort(
        key=lambda item: (
            item["receipt"]["target"]["commit"] == values["target_commit"],
            str(item["receipt"].get("generated_at", "")),
        ),
        reverse=True,
    )
    if not candidates:
        return {
            "status": "unknown",
            "kind": "receipt_missing",
            "message": "No trusted receipt covers this scenario.",
        }
    for candidate in candidates:
        receipt = candidate["receipt"]
        result = candidate["result"]
        receipt_commit = str(receipt["target"]["commit"])
        changed_paths = list(values["dirty_paths"])
        if receipt_commit != values["target_commit"]:
            if not _is_ancestor(root, receipt_commit, values["target_commit"]):
                continue
            changed_paths.extend(
                _git_lines(
                    root,
                    "diff",
                    "--name-only",
                    f"{receipt_commit}..{values['target_commit']}",
                    "--",
                )
            )
        if any(
            fnmatch.fnmatch(path, pattern)
            for path in changed_paths
            for pattern in requirement["change_triggers"]
        ):
            continue
        minimum = VERIFICATION_LEVELS[str(requirement["minimum_verification_level"])]
        actual = VERIFICATION_LEVELS[str(result["verification_level"])]
        if actual < minimum:
            return {
                "status": "unknown",
                "kind": "verification_level_low",
                "message": (
                    f"Receipt verification level {result['verification_level']} is below "
                    f"required {requirement['minimum_verification_level']}."
                ),
            }
        defect = result.get("defect") if isinstance(result.get("defect"), dict) else {}
        defect_state = defect.get("state", "clear")
        accepted = defect_state == "accepted_with_expiry" and _future_timestamp(
            defect.get("expires_at"), values["as_of"]
        )
        if defect_state == "open" or (defect_state == "accepted_with_expiry" and not accepted):
            return {
                "status": "blocked",
                "kind": "defect_open",
                "message": "The scenario has an open or expired accepted defect.",
            }
        if result["status"] != "passed":
            return {
                "status": result["status"],
                "kind": f"result_{result['status']}",
                "message": f"The latest applicable receipt result is {result['status']}.",
            }
        return {
            "behavior_id": requirement["behavior_id"],
            "scenario_id": requirement["scenario_id"],
            "status": "passed",
            "verification_level": result["verification_level"],
            "receipt_id": receipt["receipt_id"],
            "receipt_commit": receipt_commit,
            "carried_forward": receipt_commit != values["target_commit"],
            "accepted_defect": accepted,
        }
    return {
        "status": "unknown",
        "kind": "receipt_stale",
        "message": "Receipts exist, but relevant paths changed or their commits are not ancestors of the target.",
    }
