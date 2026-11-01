from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from quality_runner.artifacts import safe_child_file
from quality_runner.model_audit.contracts import (
    PREFIX,
    array_value,
    digest,
    exact_keys,
    load_json,
    object_value,
    text,
    write_once,
)
from quality_runner.review_response_files import read_regular_text_file


def validate_receipt(
    directory: Path, manifest: dict[str, Any], result: dict[str, Any], raw: object
) -> dict[str, Any]:
    receipt = object_value(raw, "verification")
    exact_keys(
        receipt,
        {
            "schema",
            "run_id",
            "manifest_digest",
            "response_digest",
            "verifier_id",
            "independent",
            "findings",
        },
        "verification",
    )
    if (
        receipt["schema"] != PREFIX + "verification/v1"
        or receipt["run_id"] != manifest["run_id"]
        or receipt["manifest_digest"] != manifest["digest"]
        or receipt["response_digest"] != result["response_digest"]
    ):
        raise ValueError("verification must bind the exact run, manifest and response")
    verifier = text(receipt["verifier_id"], "verifier_id")
    if receipt["independent"] is not True or verifier == manifest["reviewer"]["reviewer_id"]:
        raise ValueError("verification requires an independent verifier attestation")
    available = {finding["fingerprint"] for finding in result["findings"]}
    criteria = {criterion["id"] for criterion in manifest["profile"]["criteria"]}
    findings = array_value(receipt["findings"], "verification findings", minimum=1)
    seen: set[str] = set()
    for raw_finding in findings:
        finding = object_value(raw_finding, "verification finding")
        exact_keys(
            finding,
            {"fingerprint", "canonical_key", "criterion_id", "verdict", "method", "evidence"},
            "verification finding",
        )
        fingerprint = text(finding["fingerprint"], "fingerprint")
        if fingerprint not in available or fingerprint in seen:
            raise ValueError("verification references unknown or duplicate finding")
        seen.add(fingerprint)
        text(finding["canonical_key"], "canonical_key")
        text(finding["method"], "method")
        if finding["criterion_id"] not in criteria:
            raise ValueError("verification criterion is not in this audit profile")
        if finding["verdict"] not in {"verified", "disputed", "unverified"}:
            raise ValueError("unsupported verification verdict; resolution belongs to remediation")
        evidence = array_value(finding["evidence"], "evidence", minimum=1, maximum=16)
        for raw_reference in evidence:
            reference = object_value(raw_reference, "evidence")
            exact_keys(reference, {"path", "sha256"}, "evidence")
            path = safe_child_file(
                directory, text(reference["path"], "evidence path"), require_exists=True
            )
            content = read_regular_text_file(path, maximum_bytes=2_000_000)
            if (
                not content.strip()
                or hashlib.sha256(content.encode()).hexdigest() != reference["sha256"]
            ):
                raise ValueError("verification evidence digest mismatch or empty evidence")
    return receipt


def accept_verification(
    directory: Path, manifest: dict[str, Any], result: dict[str, Any], raw: object
) -> dict[str, Any]:
    receipt = validate_receipt(directory, manifest, result, raw)
    name = f"model-audit-verification-{digest(receipt)}.json"
    path = safe_child_file(directory, name)
    if path.exists():
        if load_json(path) != receipt:
            raise ValueError("verification receipt collision")
    else:
        write_once(directory, name, receipt)
    return {
        "schema": PREFIX + "verify/v1",
        "status": "verification-recorded",
        "receipt": str(path),
        "assurance": "independence and reproduction are attested by the verifier; hashes bind evidence, not behavior",
    }


def verified_findings(
    directory: Path, manifest: dict[str, Any], result: dict[str, Any]
) -> list[dict[str, Any]]:
    receipts: dict[str, list[dict[str, Any]]] = {}
    paths = sorted(directory.glob("model-audit-verification-*.json"))
    if len(paths) > 256:
        raise ValueError("too many verification receipts")
    for path in paths:
        receipt = validate_receipt(directory, manifest, result, load_json(path))
        if path.name != f"model-audit-verification-{digest(receipt)}.json":
            raise ValueError("verification receipt digest mismatch")
        for finding in receipt["findings"]:
            receipts.setdefault(finding["fingerprint"], []).append(finding)
    findings: list[dict[str, Any]] = []
    for finding in result["findings"]:
        entries = receipts.get(finding["fingerprint"], [])
        identities = {(item["canonical_key"], item["criterion_id"]) for item in entries}
        verdicts = {item["verdict"] for item in entries}
        verdict = (
            next(iter(verdicts))
            if len(verdicts) == 1 and len(identities) == 1
            else "disputed"
            if entries
            else "unverified"
        )
        canonical_key, criterion = next(iter(identities)) if len(identities) == 1 else (None, None)
        findings.append(
            {
                "fingerprint": finding["fingerprint"],
                "canonical_key": canonical_key,
                "criterion_id": criterion,
                "verdict": verdict,
                "summary": finding["summary"],
                "severity": finding["severity"],
                "location": finding["location"],
                "verification_receipts": len(entries),
                "identity_conflict": len(identities) > 1,
            }
        )
    return findings
