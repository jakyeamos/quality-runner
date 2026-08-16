from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from quality_runner.code_quality_findings import CATEGORY_ORDER, finding_sort_key, make_finding

ANTI_SLOP_DETECTOR = "anti-slop"
ANTI_SLOP_PACKAGE = "eslint-plugin-anti-slop"
ANTI_SLOP_VERSION = "0.5.0"
ANTI_SLOP_SOURCE_SHA = "a0f8dfa1ff5f0f2b6143536445d62297cdf55b2c"
ANTI_SLOP_PRESET = "evidence"
ANTI_SLOP_FORMATS = ("json", "sarif")
ANTI_SLOP_DETECTOR_SCHEMA = "quality-runner-external-detector/v1"

JS_TS_SUFFIXES = {".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"}
SKIPPED_DIRECTORIES = {
    ".git",
    ".next",
    ".quality-runner",
    ".turbo",
    "build",
    "coverage",
    "dist",
    "node_modules",
}


def merge_anti_slop_scan(
    scan_payload: dict[str, Any], detector_result: dict[str, Any]
) -> dict[str, Any]:
    """Merge external findings while preserving blocked evidence and native overlaps."""
    existing_findings = [
        item for item in scan_payload.get("findings", []) if isinstance(item, dict)
    ]
    existing_evidence = [
        item for item in scan_payload.get("detector_evidence", []) if isinstance(item, dict)
    ]
    receipt = detector_result.get("receipt")
    if not isinstance(receipt, dict):
        raise ValueError("anti-slop detector result is missing its receipt")
    if receipt.get("detector") != ANTI_SLOP_DETECTOR:
        raise ValueError("unexpected external detector receipt")
    if receipt.get("status") != "passed":
        scan_payload["detector_evidence"] = [*existing_evidence, receipt]
        return _refresh_scan_summary(scan_payload)

    relations: list[dict[str, Any]] = []
    merged = list(existing_findings)
    existing_fingerprints = {
        str(item.get("fingerprint")) for item in existing_findings if item.get("fingerprint")
    }
    native_findings = [
        item for item in existing_findings if item.get("detector") != ANTI_SLOP_DETECTOR
    ]
    for candidate in detector_result.get("findings", []):
        if not isinstance(candidate, dict):
            raise ValueError("anti-slop detector finding is malformed")
        fingerprint = str(candidate.get("fingerprint", ""))
        if fingerprint in existing_fingerprints:
            relations.append(
                {
                    "relation": "duplicate",
                    "anti_slop_fingerprint": fingerprint,
                    "existing_finding_id": _finding_identity(candidate, existing_findings),
                }
            )
            continue
        overlap = _native_overlap(candidate, native_findings)
        if overlap is not None:
            relations.append(
                {
                    "relation": "overlap",
                    "anti_slop_fingerprint": fingerprint,
                    "existing_finding_id": _finding_identity(overlap, [overlap]),
                    "deduplicated": True,
                }
            )
            continue
        merged.append(candidate)
        existing_fingerprints.add(fingerprint)

    receipt = {
        **receipt,
        "finding_count": sum(1 for item in merged if item.get("detector") == ANTI_SLOP_DETECTOR),
        "overlap_count": sum(item.get("relation") == "overlap" for item in relations),
        "relations": relations,
    }
    scan_payload["detector_evidence"] = [*existing_evidence, receipt]
    scan_payload["detector_relations"] = relations
    scan_payload["findings"] = sorted(merged, key=finding_sort_key)
    for index, finding in enumerate(scan_payload["findings"], start=1):
        finding["id"] = f"CQ-{index:04d}"
    return _refresh_scan_summary(scan_payload)


def anti_slop_cache_key(
    *,
    target_sha: str,
    qr_version: str,
    ruleset_hash: str,
    configuration_hash: str,
    anti_slop_version: str = ANTI_SLOP_VERSION,
    anti_slop_source_sha: str = ANTI_SLOP_SOURCE_SHA,
) -> str:
    """Return the complete cache identity for one external detector scan."""
    return _hash_value(
        {
            "target_sha": target_sha,
            "qr_version": qr_version,
            "anti_slop_version": anti_slop_version,
            "anti_slop_source_sha": anti_slop_source_sha,
            "ruleset_hash": ruleset_hash,
            "configuration_hash": configuration_hash,
        }
    )


def _blocked_result(
    base: dict[str, Any], reason: str, *, command_result: dict[str, Any]
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "receipt": {
            **base,
            "status": "blocked",
            "command_result": command_result,
            "reason": reason,
        },
        "findings": [],
    }


def _parse_output(stdout: str, output_format: str, root: Path) -> list[dict[str, Any]]:
    payload = json.loads(stdout)
    if output_format == "json":
        analysis = payload.get("analysis")
        if not isinstance(analysis, dict) or analysis.get("status") != "complete":
            raise ValueError("JSON analysis status is not complete")
        raw_findings = payload.get("newFindings", payload.get("findings"))
        if not isinstance(raw_findings, list):
            raise ValueError("JSON report does not contain a findings list")
        return [_finding_from_json(item, root) for item in raw_findings]
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("SARIF report does not contain runs")
    for run in runs:
        invocations = run.get("invocations") if isinstance(run, dict) else None
        if not isinstance(invocations, list) or not invocations:
            raise ValueError("SARIF report does not contain invocation status")
        if invocations[0].get("executionSuccessful") is not True:
            raise ValueError("SARIF invocation did not complete successfully")
    raw_results: list[dict[str, Any]] = []
    for run in runs:
        results = run.get("results")
        if isinstance(results, list):
            raw_results.extend(item for item in results if isinstance(item, dict))
    return [_finding_from_sarif(item, root) for item in raw_results]


def _finding_from_json(item: dict[str, Any], root: Path) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("JSON finding is not an object")
    rule_id = _rule_id(item.get("ruleId") or item.get("rule_id"))
    file = _relative_file(item.get("file") or item.get("filePath"), root)
    line = _line_number(item.get("line") or item.get("startLine"))
    message = _text(item.get("message"), "Anti-Slop evidence finding")
    return _make_external_finding(
        rule_id=rule_id,
        file=file,
        line=line,
        message=message,
        severity=item.get("severity"),
        fingerprint=item.get("fingerprint"),
        required_fix=item.get("requiredFix") or item.get("required_fix"),
        category=item.get("category"),
    )


def _finding_from_sarif(item: dict[str, Any], root: Path) -> dict[str, Any]:
    rule_id = _rule_id(item.get("ruleId"))
    locations = item.get("locations")
    if not isinstance(locations, list) or not locations:
        raise ValueError("SARIF finding has no location")
    physical = locations[0].get("physicalLocation")
    if not isinstance(physical, dict):
        raise ValueError("SARIF finding has no physical location")
    artifact = physical.get("artifactLocation")
    region = physical.get("region")
    if not isinstance(artifact, dict) or not isinstance(region, dict):
        raise ValueError("SARIF finding has incomplete location")
    file = _relative_file(artifact.get("uri"), root)
    line = _line_number(region.get("startLine"))
    message = _text((item.get("message") or {}).get("text"), "Anti-Slop evidence finding")
    partial = item.get("partialFingerprints")
    fingerprint = None
    if isinstance(partial, dict):
        fingerprint = next((value for value in partial.values() if isinstance(value, str)), None)
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    return _make_external_finding(
        rule_id=rule_id,
        file=file,
        line=line,
        message=message,
        severity=item.get("level"),
        fingerprint=fingerprint,
        required_fix=properties.get("requiredFix"),
        category=properties.get("category"),
    )


def _make_external_finding(
    *,
    rule_id: str,
    file: str,
    line: int,
    message: str,
    severity: Any,
    fingerprint: Any,
    required_fix: Any,
    category: Any,
) -> dict[str, Any]:
    finding = make_finding(
        category="anti-slop",
        severity="warning" if severity in {"error", "warning", 2, "2"} else "observation",
        confidence="high",
        file=file,
        line=line,
        rule_id=rule_id,
        evidence=message,
        expected_improvement=_text(
            required_fix, "Preserve the validated TypeScript evidence at this boundary."
        ),
        risk="External anti-slop evidence requires targeted review before remediation.",
        verification="Re-run the pinned anti-slop detector at the same target SHA.",
        remediation_bucket="anti-slop",
        rule_message=message,
        rule_category=_text(category, "TypeScript evidence"),
    )
    if isinstance(fingerprint, str) and fingerprint:
        finding["fingerprint"] = f"anti-slop:{fingerprint}"
    finding.update(
        {
            "detector": ANTI_SLOP_DETECTOR,
            "producer": ANTI_SLOP_PACKAGE,
            "producer_version": ANTI_SLOP_VERSION,
        }
    )
    return finding


def _refresh_scan_summary(payload: dict[str, Any]) -> dict[str, Any]:
    findings = [item for item in payload.get("findings", []) if isinstance(item, dict)]
    summary = dict(payload.get("summary") or {})
    categories = list(dict.fromkeys([*CATEGORY_ORDER, "anti-slop"]))
    summary["total_findings"] = len(findings)
    summary["findings_by_category"] = _counts(findings, "category", categories)
    summary["findings_by_severity"] = _counts(findings, "severity", ["warning", "observation"])
    payload["summary"] = summary
    payload["findings"] = findings
    return payload


def _native_overlap(
    candidate: dict[str, Any], native_findings: list[dict[str, Any]]
) -> dict[str, Any] | None:
    candidate_file = str(candidate.get("file", ""))
    candidate_line = int(candidate.get("line", 0))
    candidate_rule = str(candidate.get("rule_id", "")).removeprefix("anti-slop/")
    candidate_message = _normalize_text(candidate.get("evidence"))
    for native in native_findings:
        if str(native.get("file", "")) != candidate_file:
            continue
        if abs(int(native.get("line", 0)) - candidate_line) > 1:
            continue
        native_rule = str(native.get("rule_id", "")).removeprefix("anti-slop/")
        if native_rule == candidate_rule:
            return native
        native_message = _normalize_text(native.get("evidence") or native.get("rule_message"))
        if (
            candidate_message
            and native_message
            and (
                candidate_message == native_message
                or candidate_message in native_message
                or native_message in candidate_message
            )
        ):
            return native
    return None


def _finding_identity(candidate: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    fingerprint = candidate.get("fingerprint")
    if isinstance(fingerprint, str) and fingerprint:
        for item in candidates:
            if item.get("fingerprint") == fingerprint:
                return str(item.get("id") or fingerprint)
    return str(candidate.get("id") or fingerprint or "unknown")


def _validate_producer(root: Path) -> str | None:
    if not root.is_dir():
        return f"anti-slop producer root is unavailable: {root}"
    if _git_output(root, "rev-parse", "--show-toplevel") != str(root):
        return "anti-slop producer root is not a git checkout"
    if _git_output(root, "rev-parse", "HEAD") != ANTI_SLOP_SOURCE_SHA:
        return "anti-slop producer source SHA does not match the pinned version"
    dirty = _git_output(root, "status", "--porcelain")
    if dirty:
        return "anti-slop producer checkout is dirty"
    package_path = root / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return f"anti-slop producer package metadata is unreadable: {error}"
    if package.get("name") != ANTI_SLOP_PACKAGE or package.get("version") != ANTI_SLOP_VERSION:
        return "anti-slop producer package identity does not match the pinned version"
    if not (root / "bin" / "anti-slop.mjs").is_file():
        return "anti-slop producer CLI is missing"
    return None


def _producer_enabled_rules(
    root: Path, node: str, preset: str, timeout_seconds: int
) -> tuple[list[str] | None, dict[str, Any]]:
    script = (
        "import antiSlop from './src/index.mjs'; "
        "const rules = antiSlop.configs[process.argv[1]]?.rules; "
        "if (!rules) process.exit(2); "
        "process.stdout.write(JSON.stringify(Object.keys(rules).sort()));"
    )
    command = [node, "--input-type=module", "-e", script, preset]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, {"reason": f"ruleset resolution failed: {error}"}
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    resolution = {
        "exit_code": completed.returncode,
        "stdout_sha256": _sha256(stdout.encode("utf-8")),
        "stderr_sha256": _sha256(stderr.encode("utf-8")),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr_bytes": len(stderr.encode("utf-8")),
    }
    if completed.returncode != 0:
        return None, {**resolution, "reason": "producer ruleset resolution returned a failure"}
    try:
        enabled_rules = json.loads(stdout)
    except json.JSONDecodeError as error:
        return None, {**resolution, "reason": f"producer ruleset resolution was malformed: {error}"}
    if (
        not isinstance(enabled_rules, list)
        or not enabled_rules
        or not all(
            isinstance(rule, str) and rule.startswith("anti-slop/") for rule in enabled_rules
        )
    ):
        return None, {**resolution, "reason": "producer ruleset resolution did not return rule ids"}
    return enabled_rules, resolution


def _relative_file(raw: Any, root: Path) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("finding file is missing")
    parsed = urlparse(raw)
    value = unquote(parsed.path) if parsed.scheme == "file" else raw
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("finding file escapes target repository") from error
    return relative.as_posix()


def _line_number(raw: Any) -> int:
    if isinstance(raw, bool):
        raise ValueError("finding line is invalid")
    try:
        line = int(raw)
    except (TypeError, ValueError) as error:
        raise ValueError("finding line is invalid") from error
    if line < 1:
        raise ValueError("finding line is invalid")
    return line


def _rule_id(raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("finding rule id is missing")
    return raw if raw.startswith("anti-slop/") else f"anti-slop/{raw}"


def _text(raw: Any, default: str) -> str:
    return raw.strip() if isinstance(raw, str) and raw.strip() else default


def _normalize_text(raw: Any) -> str:
    return " ".join(str(raw or "").lower().split())


def _counts(items: list[dict[str, Any]], field: str, keys: list[str]) -> dict[str, int]:
    result = {key: 0 for key in keys}
    for item in items:
        value = item.get(field)
        if isinstance(value, str):
            result[value] = result.get(value, 0) + 1
    return result


def _hash_value(value: Any) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _sha256(content.encode("utf-8"))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _cache_path(cache_root: Path | None, cache_key: str) -> Path | None:
    if cache_root is None:
        return None
    return cache_root.expanduser().resolve() / "anti-slop" / f"{cache_key}.json"


def _read_cached_result(path: Path | None, base: dict[str, Any]) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("status") != "passed":
        return None
    receipt = payload.get("receipt")
    findings = payload.get("findings")
    if not isinstance(receipt, dict) or not isinstance(findings, list):
        return None
    for field in (
        "target_sha",
        "qr_version",
        "ruleset_hash",
        "configuration_hash",
        "cache_key",
    ):
        if receipt.get(field) != base.get(field):
            return None
    if receipt.get("producer") != base.get("producer"):
        return None
    return {"receipt": receipt, "findings": findings}


def _git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None
