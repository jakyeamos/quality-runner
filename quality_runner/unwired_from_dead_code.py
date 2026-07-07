from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from quality_runner.code_quality_findings import (
    CATEGORY_ORDER,
    _counts,
    _finding,
    _finding_sort_key,
)
from quality_runner.code_quality_paths import _verification_for_path

WIP_TERMS = ("draft", "stub", "placeholder", "wip", "scaffold")
VULTURE_RE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):\s+unused\s+"
    r"(?P<kind>variable|function|class|method|property|import)\s+['\"](?P<name>[^'\"]+)['\"]"
)
KNIP_EXPORT_RE = re.compile(
    r"(?P<file>[^:\s]+\.(?:ts|tsx|js|jsx|mjs|cjs|py))(?::(?P<line>\d+))?"
    r".*?(?:unused\s+export|exported\s+but\s+not\s+used|unused\s+file)?"
    r".*?(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)"
)


def merge_dead_code_unwired_findings(
    code_quality_scan: dict[str, Any],
    gate_verification: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    candidates = dead_code_unwired_findings(
        gate_verification=gate_verification,
        existing_findings=_scan_findings(code_quality_scan),
        config=config,
    )
    if not candidates:
        return code_quality_scan

    merged = {**code_quality_scan}
    findings = [*list(_scan_findings(code_quality_scan)), *candidates]
    fingerprints: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for finding in sorted(findings, key=_finding_sort_key):
        fingerprint = str(finding.get("fingerprint") or "")
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        copied = dict(finding)
        deduped.append(copied)
    for index, finding in enumerate(deduped, start=1):
        finding["id"] = f"CQ-{index:04d}"

    existing_summary = merged.get("summary")
    summary: dict[str, Any] = dict(existing_summary) if isinstance(existing_summary, dict) else {}
    summary["total_findings"] = len(deduped)
    summary["findings_by_category"] = _counts(deduped, "category", CATEGORY_ORDER)
    summary["findings_by_severity"] = _counts(deduped, "severity", ["warning", "observation"])
    merged["summary"] = summary
    merged["findings"] = deduped
    return merged


def dead_code_unwired_findings(
    *,
    gate_verification: dict[str, Any],
    existing_findings: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    gate = _dead_code_gate(gate_verification)
    if gate is None:
        return []
    output = "\n".join(
        item
        for item in (
            _string_or_none(gate.get("stdout")),
            _string_or_none(gate.get("stderr")),
            _string_or_none(gate.get("stdout_tail")),
            _string_or_none(gate.get("stderr_tail")),
        )
        if item
    )
    if not output.strip():
        return []

    accepted_prefixes = _accepted_fingerprint_prefixes(config)
    correlated_paths = _correlated_partial_paths(existing_findings)
    findings: list[dict[str, Any]] = []
    for candidate in _dead_code_candidates(output):
        if not _looks_like_unwired_work(candidate, correlated_paths):
            continue
        finding = _finding(
            category="integrate",
            severity="warning",
            confidence="high" if candidate["file"] in correlated_paths else "medium",
            file=candidate["file"],
            line=candidate["line"],
            rule_id="dead-code-unwired-candidate",
            evidence=(
                f"{candidate['tool']} reported unused {candidate['kind']} "
                f"{candidate['name']!r}: {candidate['raw']}"
            ),
            expected_improvement=(
                f"Decide whether {candidate['name']} should be wired into a product "
                "entrypoint, finished, descoped, or accepted as intentional WIP."
            ),
            risk="Dead-code output on scaffold-like work can indicate incomplete wiring rather than obsolete code.",
            verification=_verification_for_path(candidate["file"]),
            remediation_bucket="Integration and wiring decisions",
        )
        fingerprint = str(finding["fingerprint"])
        if any(fingerprint.startswith(prefix) for prefix in accepted_prefixes):
            continue
        findings.append(finding)
    return findings


def _dead_code_gate(gate_verification: dict[str, Any]) -> dict[str, Any] | None:
    gates = gate_verification.get("gates")
    if not isinstance(gates, list):
        return None
    for gate in gates:
        if isinstance(gate, dict) and gate.get("id") == "dead_code":
            return gate
    return None


def _dead_code_candidates(output: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        vulture = VULTURE_RE.match(line)
        if vulture is not None:
            candidates.append(
                {
                    "tool": "vulture",
                    "file": _normalize_path(vulture.group("file")),
                    "line": int(vulture.group("line")),
                    "kind": vulture.group("kind"),
                    "name": vulture.group("name"),
                    "raw": line,
                }
            )
            continue
        if "unused" not in line.lower():
            continue
        knip = KNIP_EXPORT_RE.search(line)
        if knip is None:
            continue
        line_number = knip.group("line")
        candidates.append(
            {
                "tool": "knip",
                "file": _normalize_path(knip.group("file")),
                "line": int(line_number) if line_number is not None else 1,
                "kind": "export",
                "name": knip.group("name"),
                "raw": line,
            }
        )
    return candidates


def _looks_like_unwired_work(candidate: dict[str, Any], correlated_paths: set[str]) -> bool:
    haystack = f"{candidate['file']} {candidate['name']}".lower()
    return candidate["file"] in correlated_paths or any(term in haystack for term in WIP_TERMS)


def _correlated_partial_paths(existing_findings: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for finding in existing_findings:
        if finding.get("category") != "integrate":
            continue
        if finding.get("rule_id") not in {"stub-implementation", "todo-scaffold"}:
            continue
        path = finding.get("file")
        if isinstance(path, str) and path:
            paths.add(path)
    return paths


def _accepted_fingerprint_prefixes(config: dict[str, Any]) -> list[str]:
    dispositions = config.get("accepted_dispositions")
    if not isinstance(dispositions, list):
        return []
    prefixes: list[str] = []
    for item in dispositions:
        if not isinstance(item, dict):
            continue
        fingerprint = item.get("fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            prefixes.append(fingerprint)
    return prefixes


def _scan_findings(code_quality_scan: dict[str, Any]) -> list[dict[str, Any]]:
    findings = code_quality_scan.get("findings")
    if not isinstance(findings, list):
        return []
    return [finding for finding in findings if isinstance(finding, dict)]


def _normalize_path(path: str) -> str:
    return Path(path.strip()).as_posix().lstrip("./")


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
