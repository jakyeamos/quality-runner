from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import cast

from quality_runner.exclusion_preflight_support import (
    EXCLUSION_PACKET_SCHEMA,
    EXCLUSION_REPORT_SCHEMA,
    EXCLUSION_RESULT_SCHEMA,
    candidate_id,
    path_has_symlink_component,
    protected_path_reasons,
    relative_path_error,
    repository_fingerprint,
)
from quality_runner.scan_exclusions import (
    SCAN_EXCLUSION_MODULES,
    SCAN_EXCLUSION_SCOPE_ALL,
    SCAN_EXCLUSION_SCOPE_MODULE,
)


def validate_exclusion_packet(
    packet: object,
    *,
    repo_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be an object"]
    allowed_packet_keys = {
        "schema",
        "run_id",
        "repo_root",
        "created_at",
        "repo_fingerprint",
        "config",
        "preflight_policy",
        "traversal",
        "candidates",
    }
    errors.extend(
        f"packet contains unsupported field: {key}"
        for key in sorted(set(packet) - allowed_packet_keys)
    )
    if packet.get("schema") != EXCLUSION_PACKET_SCHEMA:
        errors.append(f"packet schema must be {EXCLUSION_PACKET_SCHEMA}")
    root_value = packet.get("repo_root")
    if not isinstance(root_value, str) or not root_value:
        errors.append("packet repo_root must be a non-empty string")
    elif repo_root is not None and Path(root_value).expanduser().resolve() != repo_root.resolve():
        errors.append("packet repo_root does not match the target repository")
    candidates = packet.get("candidates")
    if not isinstance(candidates, list):
        errors.append("packet candidates must be an array")
        return errors
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, candidate_value in enumerate(candidates):
        if not isinstance(candidate_value, dict):
            errors.append(f"packet candidate {index} must be an object")
            continue
        candidate = cast(dict[str, object], candidate_value)
        allowed_candidate_keys = {
            "candidate_id",
            "path",
            "proposed_scope",
            "evidence",
            "protected",
            "protected_reasons",
            "suggested_decision",
            "confidence",
        }
        errors.extend(
            f"packet candidate {index} contains unsupported field: {key}"
            for key in sorted(set(candidate) - allowed_candidate_keys)
        )
        candidate_value_id = candidate.get("candidate_id")
        path_value = candidate.get("path")
        if not isinstance(candidate_value_id, str) or not re.fullmatch(
            r"EXC-[0-9a-f]{12}", candidate_value_id
        ):
            errors.append(f"packet candidate {index} has an invalid candidate_id")
        elif candidate_value_id in seen_ids:
            errors.append(f"packet candidate {candidate_value_id} is duplicated")
        else:
            seen_ids.add(candidate_value_id)
        if not isinstance(path_value, str):
            errors.append(f"packet candidate {index} path must be a string")
            continue
        path_error = relative_path_error(path_value)
        if path_error is not None:
            errors.append(f"packet candidate {index} {path_error}")
            continue
        if path_value in seen_paths:
            errors.append(f"packet candidate path {path_value} is duplicated")
        seen_paths.add(path_value)
        if candidate_value_id != candidate_id(path_value):
            errors.append(f"packet candidate id does not match path {path_value}")
        if repo_root is not None:
            if path_has_symlink_component(repo_root.resolve(), path_value):
                errors.append(f"packet candidate path traverses a symlink: {path_value}")
            candidate_path = repo_root.resolve() / Path(*PurePosixPath(path_value).parts)
            if not candidate_path.is_dir() or candidate_path.is_symlink():
                errors.append(f"packet candidate path is not a real directory: {path_value}")
        proposed_scope = candidate.get("proposed_scope")
        if not isinstance(proposed_scope, dict):
            errors.append(f"packet candidate {path_value} proposed_scope must be an object")
        else:
            scope = cast(dict[str, object], proposed_scope)
            if scope.get("path") != path_value or scope.get("pattern") != f"{path_value}/**":
                errors.append(f"packet candidate {path_value} has an unsafe proposed scope")
            if scope.get("module_scope") not in {SCAN_EXCLUSION_SCOPE_ALL, *SCAN_EXCLUSION_MODULES}:
                errors.append(f"packet candidate {path_value} has an invalid module scope")
            available_scopes = scope.get("available_module_scopes")
            if available_scopes is not None and (
                not isinstance(available_scopes, list)
                or any(
                    item not in {SCAN_EXCLUSION_SCOPE_ALL, *SCAN_EXCLUSION_MODULES}
                    for item in available_scopes
                )
            ):
                errors.append(f"packet candidate {path_value} has invalid available module scopes")
        protected = protected_path_reasons(path_value)
        if not isinstance(candidate.get("protected"), bool):
            errors.append(f"packet candidate {path_value} protected must be boolean")
        if candidate.get("protected") is not True and protected:
            errors.append(f"packet candidate {path_value} must be marked protected")
        protected_reasons = candidate.get("protected_reasons")
        if not isinstance(protected_reasons, list) or any(
            not isinstance(reason, str) for reason in protected_reasons
        ):
            errors.append(f"packet candidate {path_value} protected_reasons must be string array")
        if candidate.get("suggested_decision") not in {"exclude", "include", "defer"}:
            errors.append(f"packet candidate {path_value} has an invalid suggested_decision")
        if candidate.get("confidence") not in {"high", "medium", "low"}:
            errors.append(f"packet candidate {path_value} has an invalid confidence")
    return errors


def validate_exclusion_report(
    packet: object,
    report: object,
    *,
    repo_root: Path,
) -> dict[str, object]:
    root = repo_root.expanduser().resolve()
    errors = validate_exclusion_packet(packet, repo_root=root)
    if not isinstance(packet, dict):
        errors.append("packet must be an object")
        return validation_result(errors, [], [], {}, [])
    packet_dict = cast(dict[str, object], packet)
    if not isinstance(report, dict):
        errors.append("report must be an object")
        return validation_result(errors, [], [], {}, [])
    report_dict = cast(dict[str, object], report)
    allowed_report_keys = {
        "schema",
        "packet_sha256",
        "repo_root",
        "repo_fingerprint",
        "reviewer",
        "scope",
        "security_coverage_acknowledged",
        "decisions",
    }
    errors.extend(
        f"report contains unsupported field: {key}"
        for key in sorted(set(report_dict) - allowed_report_keys)
    )
    if report_dict.get("schema") != EXCLUSION_REPORT_SCHEMA:
        errors.append(f"report schema must be {EXCLUSION_REPORT_SCHEMA}")
    if report_dict.get("packet_sha256") != packet_sha256(packet_dict):
        errors.append("report packet_sha256 does not match the packet")
    if report_dict.get("repo_root") != packet_dict.get("repo_root"):
        errors.append("report repo_root does not match the packet")
    if report_dict.get("repo_root") != str(root):
        errors.append("report repo_root does not match the target repository")
    packet_fingerprint = packet_dict.get("repo_fingerprint")
    if report_dict.get("repo_fingerprint") != packet_fingerprint:
        errors.append("report repo_fingerprint does not match the packet")
    if isinstance(packet_fingerprint, dict):
        if repository_fingerprint(root) != packet_fingerprint:
            errors.append("packet repo/config fingerprint is stale for the target repository")
    else:
        errors.append("packet repo_fingerprint must be an object")
    reviewer = report_dict.get("reviewer")
    if not isinstance(reviewer, dict):
        errors.append("report reviewer must be an object")
    else:
        reviewer_dict = cast(dict[str, object], reviewer)
        if not isinstance(reviewer_dict.get("id"), str) or not str(reviewer_dict["id"]).strip():
            errors.append("report reviewer.id must be a non-empty string")
        if not isinstance(reviewer_dict.get("kind"), str) or not str(reviewer_dict["kind"]).strip():
            errors.append("report reviewer.kind must be a non-empty string")
    report_scope = report_dict.get("scope")
    if report_scope not in {SCAN_EXCLUSION_SCOPE_ALL, SCAN_EXCLUSION_SCOPE_MODULE}:
        errors.append("report scope must be all-modules or module-scoped")

    candidate_map: dict[str, dict[str, object]] = {}
    candidates = packet_dict.get("candidates")
    if isinstance(candidates, list):
        for candidate_value in candidates:
            if isinstance(candidate_value, dict) and isinstance(
                candidate_value.get("candidate_id"), str
            ):
                candidate_map[str(candidate_value["candidate_id"])] = cast(
                    dict[str, object], candidate_value
                )
    decisions_value = report_dict.get("decisions")
    decisions = (
        [cast(dict[str, object], item) for item in decisions_value if isinstance(item, dict)]
        if isinstance(decisions_value, list)
        else []
    )
    if not isinstance(decisions_value, list):
        errors.append("report decisions must be an array")
    counts = {"exclude": 0, "include": 0, "defer": 0}
    approved_paths: list[str] = []
    approved_patterns: list[str] = []
    approved_patterns_by_module: dict[str, list[str]] = {}
    rejected_decisions: list[dict[str, object]] = []
    seen_decisions: set[str] = set()
    used_module_scope = False
    for index, decision in enumerate(decisions):
        errors.extend(
            f"report decision {index} contains unsupported field: {key}"
            for key in sorted(
                set(decision)
                - {
                    "candidate_id",
                    "decision",
                    "rationale",
                    "evidence",
                    "confidence",
                    "module_scope",
                }
            )
        )
        candidate_value_id = decision.get("candidate_id")
        if not isinstance(candidate_value_id, str) or candidate_value_id not in candidate_map:
            errors.append(f"report decision {index} references an unknown candidate_id")
            rejected_decisions.append(
                {"candidate_id": candidate_value_id, "reason": "unknown candidate"}
            )
            continue
        if candidate_value_id in seen_decisions:
            errors.append(f"report decision {candidate_value_id} is duplicated")
            continue
        seen_decisions.add(candidate_value_id)
        candidate = candidate_map[candidate_value_id]
        decision_value = decision.get("decision")
        if decision_value not in {"exclude", "include", "defer"}:
            errors.append(f"report decision {candidate_value_id} has an invalid decision")
            rejected_decisions.append(
                {"candidate_id": candidate_value_id, "reason": "invalid decision"}
            )
            continue
        decision_name = cast(str, decision_value)
        counts[decision_name] += 1
        if not isinstance(decision.get("rationale"), str) or not str(decision["rationale"]).strip():
            errors.append(f"report decision {candidate_value_id} rationale must be non-empty")
        evidence = decision.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(not isinstance(item, str) or not item.strip() for item in evidence)
        ):
            errors.append(f"report decision {candidate_value_id} evidence must contain strings")
        confidence = decision.get("confidence")
        if confidence not in {"high", "medium", "low"}:
            errors.append(f"report decision {candidate_value_id} has an invalid confidence")
        module_scope_value = decision.get("module_scope", SCAN_EXCLUSION_SCOPE_ALL)
        if module_scope_value not in {SCAN_EXCLUSION_SCOPE_ALL, *SCAN_EXCLUSION_MODULES}:
            errors.append(f"report decision {candidate_value_id} has an invalid module scope")
            module_scope = SCAN_EXCLUSION_SCOPE_ALL
        else:
            module_scope = str(module_scope_value)
        if module_scope != SCAN_EXCLUSION_SCOPE_ALL and decision_name == "exclude":
            used_module_scope = True
        path_value = candidate.get("path")
        if not isinstance(path_value, str):
            errors.append(f"report decision {candidate_value_id} candidate path is invalid")
            continue
        if decision_name != "exclude":
            continue
        protected_reasons = protected_path_reasons(path_value)
        if protected_reasons:
            reason = "; ".join(protected_reasons)
            errors.append(f"report cannot exclude protected path {path_value}: {reason}")
            rejected_decisions.append(
                {"candidate_id": candidate_value_id, "path": path_value, "reason": reason}
            )
        elif confidence == "low":
            errors.append(f"report cannot exclude low-confidence candidate {path_value}")
            rejected_decisions.append(
                {"candidate_id": candidate_value_id, "path": path_value, "reason": "low confidence"}
            )
        else:
            approved_paths.append(path_value)
            pattern = f"{path_value}/**"
            approved_patterns_by_module.setdefault(module_scope, []).append(pattern)
            if module_scope == SCAN_EXCLUSION_SCOPE_ALL:
                approved_patterns.append(pattern)

    missing = sorted(set(candidate_map) - seen_decisions)
    if missing:
        errors.append(f"report must decide every packet candidate; missing: {', '.join(missing)}")
    if used_module_scope and report_scope != SCAN_EXCLUSION_SCOPE_MODULE:
        errors.append("report scope must be module-scoped when a decision uses module scope")
    if not used_module_scope and report_scope != SCAN_EXCLUSION_SCOPE_ALL:
        errors.append("report scope must be all-modules when all excludes are global")
    security_reduced = any(
        scope in {SCAN_EXCLUSION_SCOPE_ALL, "security"} for scope in approved_patterns_by_module
    )
    if security_reduced and report_dict.get("security_coverage_acknowledged") is not True:
        errors.append("report must explicitly acknowledge security coverage impact")
    return validation_result(
        errors,
        approved_paths,
        approved_patterns,
        approved_patterns_by_module,
        rejected_decisions,
        counts,
    )


def packet_sha256(packet: dict[str, object]) -> str:
    content = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def report_sha256(report: dict[str, object]) -> str:
    content = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validation_result(
    errors: list[str],
    approved_paths: list[str],
    approved_patterns: list[str],
    approved_patterns_by_module: dict[str, list[str]],
    rejected_decisions: list[dict[str, object]],
    counts: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "schema": EXCLUSION_RESULT_SCHEMA,
        "status": "validated" if not errors else "rejected",
        "passed": not errors,
        "errors": errors,
        "approved_paths": approved_paths,
        "approved_patterns": approved_patterns,
        "approved_patterns_by_module": approved_patterns_by_module,
        "rejected_decisions": rejected_decisions,
        "decision_counts": counts or {"exclude": 0, "include": 0, "defer": 0},
    }
