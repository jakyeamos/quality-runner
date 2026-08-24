from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

GATE_VERIFICATION_SCHEMA = "quality-runner-gate-verification-v0.2"
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024


def quality_violations(
    *,
    root: Path,
    details: dict[str, Any],
    policy: dict[str, Any],
    branch: str | None,
    head_sha: str | None,
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    canonical = details.get("canonical_verify_command")
    if not _nonempty_string(canonical):
        violations.append({"rule": "missing-canonical-verify", "path": "details"})
    ci = _object(details.get("ci"))
    if ci.get("status") != "passed":
        violations.append({"rule": "ci-not-passed", "path": "details.ci.status"})
    if ci.get("verify_command") != canonical:
        violations.append({"rule": "ci-command-drift", "path": "details.ci.verify_command"})
    if ci.get("locked_dependencies") is not True:
        violations.append({"rule": "ci-not-locked", "path": "details.ci.locked_dependencies"})
    violations.extend(_exact_ref_violations(ci, branch=branch, head_sha=head_sha))

    result = _object(details.get("result"))
    warnings = result.get("warnings")
    errors = result.get("errors")
    if warnings != 0 or errors != 0:
        violations.append(
            {
                "rule": "nonzero-quality-findings",
                "path": "details.result",
                "warnings": warnings,
                "errors": errors,
            }
        )

    gates = _records_by_id(details.get("gates"))
    for gate_id in _string_list(policy.get("required_gates")):
        gate = gates.get(gate_id)
        if gate is None:
            violations.append({"rule": "missing-quality-gate", "path": gate_id})
            continue
        applicability = gate.get("applicability")
        status = gate.get("status")
        if applicability == "not_applicable":
            if not _nonempty_string(gate.get("reason")):
                violations.append({"rule": "missing-gate-na-reason", "path": gate_id})
        elif applicability != "applicable" or status != "passed":
            violations.append(
                {"rule": "quality-gate-not-passed", "path": gate_id, "status": status}
            )

    controls = _records_by_id(details.get("negative_controls"))
    expected_status = {
        "clean-fixture": "passed",
        "seeded-violation": "blocked",
        "missing-tool": "blocked",
        "skipped-required-adapter": "blocked",
    }
    for control_id in _string_list(policy.get("required_negative_controls")):
        control = controls.get(control_id)
        if control is None:
            violations.append({"rule": "missing-negative-control", "path": control_id})
            continue
        expected = expected_status.get(control_id)
        if expected is None or control.get("status") != expected:
            violations.append(
                {
                    "rule": "negative-control-not-enforced",
                    "path": control_id,
                    "expected": expected,
                    "observed": control.get("status"),
                }
            )
    if details.get("baselines") != []:
        violations.append({"rule": "quality-baseline-present", "path": "details.baselines"})
    violations.extend(
        _gate_receipt_violations(
            root=root,
            descriptor=_object(details.get("quality_runner_receipt")),
            canonical=canonical if isinstance(canonical, str) else None,
            branch=branch,
            head_sha=head_sha,
        )
    )
    return violations


def _gate_receipt_violations(
    *,
    root: Path,
    descriptor: dict[str, Any],
    canonical: str | None,
    branch: str | None,
    head_sha: str | None,
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    relative = descriptor.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return [{"rule": "invalid-receipt-path", "path": "quality_runner_receipt.path"}]
    candidate = root / relative
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return [{"rule": "receipt-outside-repository", "path": relative}]
    if _has_symlink_component(root, candidate):
        return [{"rule": "receipt-symlink", "path": relative}]
    if not resolved.is_file():
        return [{"rule": "receipt-missing", "path": relative}]
    try:
        if resolved.stat().st_size > MAX_EVIDENCE_BYTES:
            return [{"rule": "receipt-too-large", "path": relative}]
    except OSError:
        return [{"rule": "receipt-unreadable", "path": relative}]
    digest = _sha256_path(resolved)
    if descriptor.get("sha256") != digest:
        violations.append(
            {
                "rule": "receipt-digest-mismatch",
                "path": relative,
                "expected": descriptor.get("sha256"),
                "observed": digest,
            }
        )
    receipt, read_violations = _read_object(resolved, label="quality receipt")
    violations.extend(read_violations)
    if descriptor.get("schema") != GATE_VERIFICATION_SCHEMA:
        violations.append({"rule": "receipt-descriptor-schema", "path": relative})
    if receipt.get("schema") != GATE_VERIFICATION_SCHEMA:
        violations.append({"rule": "receipt-schema", "path": relative})
    if receipt.get("status") != "passed":
        violations.append({"rule": "receipt-not-passed", "path": relative})
    if receipt.get("execute_discovered_gates") is not True:
        violations.append({"rule": "receipt-did-not-execute", "path": relative})
    context = _object(receipt.get("verification_context"))
    if context.get("execution_authorized") is not True:
        violations.append({"rule": "receipt-execution-not-authorized", "path": relative})
    violations.extend(
        _exact_ref_violations(_object(receipt.get("provenance")), branch=branch, head_sha=head_sha)
    )
    gates = (
        [
            cast(dict[str, Any], gate)
            for gate in cast(list[object], receipt.get("gates"))
            if isinstance(gate, dict)
        ]
        if isinstance(receipt.get("gates"), list)
        else []
    )
    required = [gate for gate in gates if gate.get("enforcement") != "advisory"]
    if not required:
        violations.append({"rule": "receipt-has-no-required-gates", "path": relative})
    for gate in required:
        if gate.get("status") != "passed":
            violations.append(
                {"rule": "receipt-required-gate-not-passed", "path": str(gate.get("id"))}
            )
    if canonical is not None and not any(gate.get("command") == canonical for gate in required):
        violations.append({"rule": "receipt-canonical-command-missing", "path": relative})
    return violations


def _exact_ref_violations(
    target: dict[str, Any], *, branch: str | None, head_sha: str | None
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if target.get("branch") != branch:
        violations.append(
            {
                "rule": "branch-mismatch",
                "path": "target.branch",
                "expected": branch,
                "observed": target.get("branch"),
            }
        )
    if target.get("head_sha") != head_sha:
        violations.append(
            {
                "rule": "head-mismatch",
                "path": "target.head_sha",
                "expected": head_sha,
                "observed": target.get("head_sha"),
            }
        )
    return violations


def _read_object(path: Path, *, label: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, [
            {"rule": f"{label.replace(' ', '-')}-invalid", "path": str(path), "error": str(error)}
        ]
    if not isinstance(value, dict):
        return {}, [{"rule": f"{label.replace(' ', '-')}-not-object", "path": str(path)}]
    return cast(dict[str, Any], value), []


def _sha256_path(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _has_symlink_component(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for segment in relative.parts:
        current = current / segment
        if current.is_symlink():
            return True
    return False


def _records_by_id(value: object) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(value, list):
        return result
    for raw in cast(list[object], value):
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            result[str(raw["id"])] = cast(dict[str, Any], raw)
    return result


def _object(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str) and item]


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
