from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import CODE_QUALITY_SCAN_SCHEMA, RESOLUTION_LEDGER_SCHEMA

DEFAULT_LARGE_FILE_LINES = 500
DEFAULT_FAT_ROUTER_LINES = 500
ACCEPTED_STATUSES = {"accepted-intentional", "accepted-false-positive", "blocked-with-prerequisite"}
CODE_EXTENSIONS = {".cjs", ".css", ".html", ".js", ".jsx", ".mjs", ".py", ".sh", ".ts", ".tsx"}
TEXT_EXTENSIONS = {*CODE_EXTENSIONS, ".json", ".md", ".toml", ".yaml", ".yml"}
IGNORED_DIRS = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".parcel-cache",
    ".pytest_cache",
    ".quality-runner",
    ".ruff_cache",
    ".svelte-kit",
    ".turbo",
    ".vercel",
    ".venv",
    ".vite",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "generated",
    "gen",
    "node_modules",
    "out",
    "playwright-report",
    "target",
    "test-results",
    "vendor",
}
CATEGORY_ORDER = [
    "harden",
    "simplify",
    "clarify",
    "deduplicate",
    "speed",
    "improve-tests",
    "ui_structural",
]
CONFIDENCE_WEIGHT = {"high": 3, "medium": 2, "low": 1}
SEVERITY_WEIGHT = {"warning": 3, "observation": 1}


def create_code_quality_scan(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    policy = _structural_policy(config)
    disabled_groups = set(policy["disabled_rule_groups"])
    generated_paths = _generated_paths(scan)
    skipped_files: list[dict[str, str]] = []
    findings: list[dict[str, Any]] = []
    extracted_functions: list[dict[str, Any]] = []
    accountability: list[dict[str, Any]] = []

    for path in _discover_text_files(root, skipped_files, generated_paths):
        relative_path = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = _split_lines(text)
        accountability.append(
            {
                "path": relative_path,
                "line_count": len(lines),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "scan_status": "scanned",
                "check_coverage": _check_coverage(relative_path),
            }
        )
        findings.extend(
            _scan_file(
                relative_path=relative_path,
                text=text,
                lines=lines,
                disabled_groups=disabled_groups,
                large_file_lines=policy["large_file_lines"],
                fat_router_lines=policy["fat_router_lines"],
            )
        )
        extracted_functions.extend(_extract_functions(relative_path, lines))

    if "deduplicate" not in disabled_groups:
        duplicate_clusters = _duplicate_clusters(extracted_functions)
        for cluster in duplicate_clusters:
            first = cluster["candidates"][0]
            findings.append(
                _finding(
                    category="deduplicate",
                    severity="warning",
                    confidence="medium",
                    file=first["file"],
                    line=first["line"],
                    rule_id="near-duplicate-function",
                    evidence=f"{cluster['id']} spans {len(cluster['candidates'])} functions.",
                    expected_improvement=(
                        "Extract a shared helper only when the call sites share domain semantics."
                    ),
                    risk="Near-duplicate logic can drift across fixes.",
                    verification=_verification_for_path(first["file"]),
                    remediation_bucket="duplicate consolidation and helper extraction",
                )
            )
    else:
        duplicate_clusters = []

    sorted_findings = sorted(findings, key=_finding_sort_key)
    for index, finding in enumerate(sorted_findings, start=1):
        finding["id"] = f"CQ-{index:04d}"

    return {
        "schema": CODE_QUALITY_SCAN_SCHEMA,
        "run_id": _string_or_none(scan.get("run_id")),
        "repo_root": str(root),
        "summary": {
            "total_files": len(accountability),
            "total_lines": sum(item["line_count"] for item in accountability),
            "total_findings": len(sorted_findings),
            "findings_by_category": _counts(sorted_findings, "category", CATEGORY_ORDER),
            "findings_by_severity": _counts(
                sorted_findings, "severity", ["warning", "observation"]
            ),
            "duplicate_clusters": len(duplicate_clusters),
        },
        "accountability": accountability,
        "findings": sorted_findings,
        "duplicate_clusters": duplicate_clusters,
        "skipped_files": sorted(skipped_files, key=lambda item: item["path"]),
    }


def build_resolution_ledger(
    *,
    repo_root: Path,
    run_id: str,
    code_quality_scan: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    current_findings = _current_findings(code_quality_scan)
    current_fingerprints = set(current_findings)
    previous_entries = _latest_previous_resolution_entries(repo_root, run_id)
    accepted_by_config = _accepted_dispositions(config)
    accepted_by_previous = {
        entry["fingerprint"]: entry
        for entry in previous_entries
        if entry.get("status") in ACCEPTED_STATUSES and isinstance(entry.get("fingerprint"), str)
    }
    entries: list[dict[str, Any]] = []

    for fingerprint, finding in sorted(current_findings.items()):
        configured = accepted_by_config.get(fingerprint)
        previous = accepted_by_previous.get(fingerprint)
        status = "unresolved"
        reason = ""
        owner = None
        expires = None
        if configured is not None:
            status = configured["status"]
            reason = configured["reason"]
            owner = configured["owner"]
            expires = configured.get("expires")
        elif previous is not None:
            status = str(previous["status"])
            reason = str(previous.get("reason") or previous.get("disposition") or "")
            owner = _string_or_none(previous.get("owner"))
            expires = _string_or_none(previous.get("expires"))

        entries.append(
            _ledger_entry(
                finding=finding,
                status=status,
                reason=reason,
                owner=owner,
                expires=expires,
            )
        )

    for previous in previous_entries:
        fingerprint = previous.get("fingerprint")
        if not isinstance(fingerprint, str) or fingerprint in current_fingerprints:
            continue
        if previous.get("status") == "fixed":
            continue
        entries.append(
            {
                **previous,
                "status": "fixed",
                "reason": "Finding absent from current scan.",
            }
        )

    entries.sort(key=lambda item: (str(item["status"]), str(item["rule_id"]), str(item["file"])))
    return {
        "schema": RESOLUTION_LEDGER_SCHEMA,
        "run_id": run_id,
        "summary": {
            "total_entries": len(entries),
            "by_status": _counts(
                entries, "status", ["unresolved", "fixed", *sorted(ACCEPTED_STATUSES)]
            ),
        },
        "entries": entries,
    }


def render_resolution_ledger_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Quality Runner Resolution Ledger",
        "",
        f"- Schema: {ledger.get('schema')}",
        f"- Run ID: {ledger.get('run_id')}",
        "",
        "## Status Counts",
        "",
    ]
    summary = ledger.get("summary")
    by_status = summary.get("by_status") if isinstance(summary, dict) else None
    if isinstance(by_status, dict):
        for status, count in sorted(by_status.items()):
            lines.append(f"- {status}: {count}")
    lines.extend(["", "## Entries", ""])

    entries = ledger.get("entries")
    if isinstance(entries, list) and entries:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            lines.append(
                f"- {entry.get('status')}: {entry.get('rule_id')} "
                f"({entry.get('file')}:{entry.get('line')})"
            )
    else:
        lines.append("No resolution entries.")
    return "\n".join(lines).rstrip() + "\n"


def _structural_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = config.get("structural_scan")
    if not isinstance(policy, dict):
        policy = {}
    disabled = policy.get("disabled_rule_groups")
    large_file_lines = policy.get("large_file_lines")
    fat_router_lines = policy.get("fat_router_lines")
    return {
        "disabled_rule_groups": [item for item in disabled if isinstance(item, str)]
        if isinstance(disabled, list)
        else [],
        "large_file_lines": large_file_lines
        if isinstance(large_file_lines, int) and large_file_lines > 0
        else DEFAULT_LARGE_FILE_LINES,
        "fat_router_lines": fat_router_lines
        if isinstance(fat_router_lines, int) and fat_router_lines > 0
        else DEFAULT_FAT_ROUTER_LINES,
    }


def _discover_text_files(
    root: Path,
    skipped_files: list[dict[str, str]],
    generated_paths: set[str],
) -> list[Path]:
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        relative_current = current_path.relative_to(root).as_posix()
        ignored = sorted(
            name
            for name in dir_names
            if name in IGNORED_DIRS
            or _under_generated_path(_join_relative(relative_current, name), generated_paths)
        )
        for name in ignored:
            skipped_files.append(
                {
                    "path": (current_path / name).relative_to(root).as_posix(),
                    "reason": "generated directory"
                    if _under_generated_path(
                        _join_relative(relative_current, name), generated_paths
                    )
                    else "ignored directory",
                }
            )
        dir_names[:] = sorted(
            name
            for name in dir_names
            if name not in IGNORED_DIRS
            and not _under_generated_path(_join_relative(relative_current, name), generated_paths)
        )
        for file_name in sorted(file_names):
            path = current_path / file_name
            relative_path = path.relative_to(root).as_posix()
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            if _is_generated_file(relative_path):
                skipped_files.append({"path": relative_path, "reason": "generated file"})
                continue
            if path.suffix in TEXT_EXTENSIONS or path.name in {"Dockerfile", "Makefile"}:
                files.append(path)
    return files


def _scan_file(
    *,
    relative_path: str,
    text: str,
    lines: list[str],
    disabled_groups: set[str],
    large_file_lines: int,
    fat_router_lines: int,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    is_javascript_source = _is_javascript_source_file(relative_path)
    block_depth = 0
    loop_depth = 0
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if "simplify" not in disabled_groups and is_javascript_source:
            if _is_deep_nesting(stripped, block_depth):
                findings.append(
                    _finding(
                        category="simplify",
                        severity="warning",
                        confidence="medium",
                        file=relative_path,
                        line=index,
                        rule_id="deep-nesting",
                        evidence=line,
                        expected_improvement=(
                            "Flatten guard clauses, extract decision helpers, or split rendering branches."
                        ),
                        risk="Deeply nested flow is hard to review and easy to change incorrectly.",
                        verification=_verification_for_path(relative_path),
                        remediation_bucket="simplification and shrink pass",
                    )
                )
            if _nested_ternary(line):
                findings.append(
                    _finding(
                        category="simplify",
                        severity="warning",
                        confidence="high",
                        file=relative_path,
                        line=index,
                        rule_id="nested-ternary",
                        evidence=line,
                        expected_improvement="Replace nested ternaries with named branches or helpers.",
                        risk="Nested ternaries hide branch behavior.",
                        verification=_verification_for_path(relative_path),
                        remediation_bucket="simplification and shrink pass",
                    )
                )

        if "harden" not in disabled_groups:
            findings.extend(_harden_findings(relative_path, line, index))

        if "clarify" not in disabled_groups:
            findings.extend(_clarify_findings(relative_path, line, index))

        if (
            "speed" not in disabled_groups
            and is_javascript_source
            and loop_depth > 0
            and "await" in stripped
        ):
            findings.append(
                _finding(
                    category="speed",
                    severity="warning",
                    confidence="medium",
                    file=relative_path,
                    line=index,
                    rule_id="await-in-loop",
                    evidence=line,
                    expected_improvement="Batch independent work or document required sequencing.",
                    risk="Sequential async work can become a latency bottleneck.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="performance and batching improvements",
                )
            )

        if "improve-tests" not in disabled_groups:
            findings.extend(_test_quality_findings(relative_path, line, index))

        if "ui_structural" not in disabled_groups:
            findings.extend(_ui_structural_findings(relative_path, line, index))

        if is_javascript_source:
            if stripped.startswith(("for ", "for(", "for await", "while ", "while(")):
                loop_depth += 1
            block_depth = max(0, block_depth + line.count("{") - line.count("}"))
            if stripped.startswith("}") and loop_depth > 0:
                loop_depth -= 1

    if "simplify" not in disabled_groups and _is_source_file(relative_path):
        if len(lines) > large_file_lines and not _is_test_file(relative_path):
            findings.append(
                _finding(
                    category="simplify",
                    severity="warning",
                    confidence="high",
                    file=relative_path,
                    line=1,
                    rule_id="large-source-file",
                    evidence=f"{len(lines)} lines",
                    expected_improvement="Split mixed responsibilities into focused modules.",
                    risk="Large files increase review cost and refactor risk.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="simplification and shrink pass",
                )
            )
        if _is_router_path(relative_path) and len(lines) > fat_router_lines:
            findings.append(
                _finding(
                    category="simplify",
                    severity="warning",
                    confidence="high",
                    file=relative_path,
                    line=1,
                    rule_id="fat-router",
                    evidence=f"{len(lines)} router lines",
                    expected_improvement=(
                        "Keep routers focused on validation, authorization, delegation, and response shaping."
                    ),
                    risk="Fat routers mix API boundary and domain logic.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="simplification and shrink pass",
                )
            )

    if (
        "ui_structural" not in disabled_groups
        and _is_ui_file(relative_path)
        and _has_motion_without_reduced_motion(text)
    ):
        findings.append(
            _finding(
                category="ui_structural",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=1,
                rule_id="missing-reduced-motion",
                evidence="motion properties without prefers-reduced-motion fallback",
                expected_improvement="Add a reduced-motion alternative for animation or transition.",
                risk="Motion-sensitive users may get inaccessible UI.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="UI structural quality",
            )
        )

    return findings


def _harden_findings(relative_path: str, line: str, line_number: int) -> list[dict[str, Any]]:
    if not _is_javascript_source_file(relative_path):
        return []

    rules = [
        (
            "explicit-any",
            r"(?::\s*any\b|\bas\s+any\b|<any>)",
            "Replace `any` with a narrow local type, generic constraint, or existing contract.",
            "Type holes allow runtime shape drift through strict boundaries.",
        ),
        (
            "ts-ignore",
            r"@ts-ignore",
            "Remove the ignore or replace it with a documented `@ts-expect-error`.",
            "Ignored diagnostics can conceal real type drift.",
        ),
        (
            "silent-catch",
            r"catch\s*(?:\([^)]*\))?\s*{\s*}|\.catch\(\s*(?:\(\s*\)\s*)?=>\s*{}\s*\)",
            "Log with context or prove the failure is intentionally ignored.",
            "Silent failures make production debugging harder.",
        ),
        (
            "env-non-null-assertion",
            r"\bprocess\.env\.[A-Z0-9_]+!",
            "Route required env access through validation or fail closed.",
            "Deploy misconfiguration can become runtime crashes.",
        ),
    ]
    findings = [
        _finding(
            category="harden",
            severity="warning",
            confidence="high",
            file=relative_path,
            line=line_number,
            rule_id=rule_id,
            evidence=line,
            expected_improvement=expected,
            risk=risk,
            verification=_verification_for_path(relative_path),
            remediation_bucket="API hardening and type safety",
        )
        for rule_id, pattern, expected, risk in rules
        if re.search(pattern, line)
    ]
    if _is_runtime_file(relative_path) and re.search(
        r"\bconsole\.(?:log|debug|warn|error)\s*\(", line
    ):
        findings.append(
            _finding(
                category="harden",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="console-output",
                evidence=line,
                expected_improvement="Use structured logging or remove runtime console output.",
                risk="Noisy output hides real failures and can leak context.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="API hardening and logging",
            )
        )
    if _is_api_file(relative_path):
        if re.search(r"\bnew\s+TRPCError\s*\(", line):
            findings.append(
                _finding(
                    category="harden",
                    severity="warning",
                    confidence="high",
                    file=relative_path,
                    line=line_number,
                    rule_id="bare-trpc-error",
                    evidence=line,
                    expected_improvement="Use the project typed error taxonomy when available.",
                    risk="Bare tRPC errors weaken downstream error handling.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="API hardening, errors, instrumentation, logging",
                )
            )
        if re.search(
            r"\b(?:publicProcedure|protectedProcedure|adminProcedure)\b", line
        ) and not re.search(r"\binstrumented(?:Public|Protected|Admin)Procedure\b", line):
            findings.append(
                _finding(
                    category="harden",
                    severity="warning",
                    confidence="medium",
                    file=relative_path,
                    line=line_number,
                    rule_id="uninstrumented-trpc-procedure",
                    evidence=line,
                    expected_improvement="Use an instrumented procedure or document an explicit opt-out.",
                    risk="Uninstrumented procedures bypass latency and error visibility.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="API hardening, errors, instrumentation, logging",
                )
            )
        if re.search(
            r"\b(?:bio|name|displayName|username|comment|body|reason|title|label|description|note|notes)\s*:\s*z\.string\(\)",
            line,
        ) or re.search(
            r"\b(?:bio|name|displayName|username|comment|body|reason|title|label|description|note|notes)\s*=\s*z\.string\(\)",
            line,
        ):
            findings.append(
                _finding(
                    category="harden",
                    severity="warning",
                    confidence="medium",
                    file=relative_path,
                    line=line_number,
                    rule_id="raw-free-text-z-string",
                    evidence=line,
                    expected_improvement="Use an appropriate shared text sanitizer or bounded schema.",
                    risk="Raw free-text schemas bypass input hygiene.",
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="API hardening and input hygiene",
                )
            )
    return findings


def _clarify_findings(relative_path: str, line: str, line_number: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if _has_todo_comment(line):
        findings.append(
            _finding(
                category="clarify",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="todo-comment",
                evidence=line,
                expected_improvement="Resolve the comment or move it into a tracked plan with owner.",
                risk="Inline unresolved work ages into undocumented ambiguity.",
                verification='rg -n "TODO|FIXME|HACK|TBD" affected files',
                remediation_bucket="clarity and hygiene cleanup",
            )
        )
    if _is_page_file(relative_path) and re.search(
        r"\b(?:trpc\.|useQuery\s*\(|useMutation\s*\(|refetchInterval)\b", line
    ):
        findings.append(
            _finding(
                category="clarify",
                severity="warning",
                confidence="high",
                file=relative_path,
                line=line_number,
                rule_id="page-data-access",
                evidence=line,
                expected_improvement="Move data access and derived state into a co-located page hook.",
                risk="Page components with orchestration become hard to test.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="web/mobile clarity and page thinning",
            )
        )
    return findings


def _test_quality_findings(relative_path: str, line: str, line_number: int) -> list[dict[str, Any]]:
    if not _is_test_file(relative_path) or not _is_javascript_source_file(relative_path):
        return []
    findings: list[dict[str, Any]] = []
    if re.search(
        r"\bexpect\(\s*(true|false)\s*\)\.(?:toBe|toEqual|toStrictEqual)\(\s*\1\s*\)", line
    ) or re.search(r"\.toHaveBeenCalled\(\s*\)", line):
        findings.append(
            _finding(
                category="improve-tests",
                severity="warning",
                confidence="high",
                file=relative_path,
                line=line_number,
                rule_id="weak-test-assertion",
                evidence=line,
                expected_improvement="Assert behavior, payload shape, or state transition.",
                risk="Weak tests can pass while behavior regresses.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="tests, E2E, scripts, CI cleanup",
            )
        )
    if "console.log(" in line:
        findings.append(
            _finding(
                category="improve-tests",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="console-output",
                evidence=line,
                expected_improvement="Remove noisy test output or assert it deliberately.",
                risk="Noisy test logs hide real failures.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="tests, E2E, scripts, CI cleanup",
            )
        )
    return findings


def _ui_structural_findings(
    relative_path: str, line: str, line_number: int
) -> list[dict[str, Any]]:
    if not _is_ui_file(relative_path):
        return []
    specs = [
        (
            "gradient-text",
            "background-clip" in line and "text" in line and "gradient(" in line,
            "Use a solid text color; reserve gradients for meaningful surfaces.",
            "Gradient text is a common low-signal visual trope.",
        ),
        (
            "decorative-grid-background",
            "linear-gradient" in line
            and "1px" in line
            and ("90deg" in line or line.count("linear-gradient") > 1),
            "Remove decorative grid backgrounds unless the surface is a real canvas/map/measurement tool.",
            "Decorative grids read as generic AI decoration.",
        ),
        (
            "side-stripe-border",
            bool(re.search(r"border-(?:left|right)\s*:\s*(?:[2-9]|\d{2,})px", line)),
            "Use full borders, background tints, icons, or no accent instead.",
            "Side-stripe accents are a repetitive card/callout trope.",
        ),
        (
            "excessive-border-radius",
            bool(re.search(r"border-radius\s*:\s*(?:3[2-9]|[4-9]\d|\d{3,})px", line)),
            "Keep cards and panels within the project's radius scale.",
            "Over-rounded containers make interfaces feel generic.",
        ),
        (
            "arbitrary-z-index",
            bool(re.search(r"z-index\s*:\s*(?:999|9999|\d{4,})", line)),
            "Use a semantic z-index scale.",
            "Arbitrary stacking values make overlays fragile.",
        ),
        (
            "nested-card-markup",
            line.count('className="card') + line.count("className='card") >= 2,
            "Avoid nesting cards inside cards; flatten the layout or use sections.",
            "Nested cards create heavy, unclear visual hierarchy.",
        ),
        (
            "risky-hidden-reveal",
            bool(
                re.search(r"\b(?:opacity\s*:\s*0|visibility\s*:\s*hidden|display\s*:\s*none)", line)
            ),
            "Ensure reveal animations enhance visible content rather than gating it.",
            "Hidden default content can ship blank in paused/headless renderers.",
        ),
    ]
    return [
        _finding(
            category="ui_structural",
            severity="observation",
            confidence="medium",
            file=relative_path,
            line=line_number,
            rule_id=rule_id,
            evidence=line,
            expected_improvement=expected,
            risk=risk,
            verification=_verification_for_path(relative_path),
            remediation_bucket="UI structural quality",
        )
        for rule_id, matched, expected, risk in specs
        if matched
    ]


def _finding(
    *,
    category: str,
    severity: str,
    confidence: str,
    file: str,
    line: int,
    rule_id: str,
    evidence: str,
    expected_improvement: str,
    risk: str,
    verification: str,
    remediation_bucket: str,
) -> dict[str, Any]:
    fingerprint = _fingerprint(rule_id, file, evidence)
    return {
        "id": "",
        "fingerprint": fingerprint,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "score": SEVERITY_WEIGHT[severity] * CONFIDENCE_WEIGHT[confidence],
        "file": file,
        "line": line,
        "rule_id": rule_id,
        "evidence": evidence.strip(),
        "expected_improvement": expected_improvement,
        "risk": risk,
        "verification": verification,
        "remediation_bucket": remediation_bucket,
    }


def _fingerprint(rule_id: str, file: str, evidence: str) -> str:
    normalized = " ".join(evidence.strip().split())
    return hashlib.sha256(f"{rule_id}:{file}:{normalized}".encode()).hexdigest()[:16]


def _finding_sort_key(finding: dict[str, Any]) -> tuple[int, int, str, int, str]:
    return (
        -int(finding["score"]),
        CATEGORY_ORDER.index(str(finding["category"])),
        str(finding["file"]),
        int(finding["line"]),
        str(finding["rule_id"]),
    )


def _counts(items: list[dict[str, Any]], field: str, keys: list[str]) -> dict[str, int]:
    counts = {key: 0 for key in keys}
    for item in items:
        value = item.get(field)
        if isinstance(value, str):
            counts[value] = counts.get(value, 0) + 1
    return counts


def _extract_functions(relative_path: str, lines: list[str]) -> list[dict[str, Any]]:
    if not _is_javascript_source_file(relative_path):
        return []
    functions: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = re.search(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)", line)
        if match is None:
            continue
        end = _block_end(lines, index)
        body = "\n".join(lines[index : end + 1])
        normalized = _normalize_function(body, match.group(2))
        if len(normalized) < 30:
            continue
        functions.append(
            {
                "file": relative_path,
                "line": index + 1,
                "name": match.group(1),
                "line_count": end - index + 1,
                "normalized_body": normalized,
            }
        )
    return functions


def _duplicate_clusters(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for function in functions:
        normalized = str(function["normalized_body"])
        groups.setdefault(normalized, []).append(function)
    clusters = []
    for group in groups.values():
        if len(group) < 2:
            continue
        candidates = sorted(group, key=lambda item: (str(item["file"]), int(item["line"])))
        clusters.append(
            {
                "id": f"DUP-{len(clusters) + 1:03d}",
                "similarity": 100,
                "reason": "normalized-function-body-match",
                "candidates": [
                    {
                        "file": str(item["file"]),
                        "line": int(item["line"]),
                        "name": str(item["name"]),
                        "line_count": int(item["line_count"]),
                    }
                    for item in candidates
                ],
            }
        )
    return clusters


def _generated_paths(scan: dict[str, Any]) -> set[str]:
    generated_code = scan.get("generated_code")
    if not isinstance(generated_code, list):
        return set()
    paths: set[str] = set()
    for item in generated_code:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str) and path:
            paths.add(path.strip("/"))
    return paths


def _under_generated_path(relative_path: str, generated_paths: set[str]) -> bool:
    normalized = relative_path.strip("/")
    return any(normalized == path or normalized.startswith(f"{path}/") for path in generated_paths)


def _join_relative(parent: str, child: str) -> str:
    return child if parent == "." else f"{parent}/{child}"


def _is_generated_file(relative_path: str) -> bool:
    name = Path(relative_path).name
    generated_suffixes = (
        ".d.ts",
        ".gen.js",
        ".gen.ts",
        ".gen.tsx",
        ".generated.js",
        ".generated.ts",
        ".generated.tsx",
        ".pb.go",
        "_pb2.py",
        "_pb2_grpc.py",
    )
    return name.endswith(generated_suffixes)


def _block_end(lines: list[str], start: int) -> int:
    depth = 0
    opened = False
    for index in range(start, len(lines)):
        line = lines[index]
        depth += line.count("{")
        opened = opened or depth > 0
        depth -= line.count("}")
        if opened and depth <= 0:
            return index
    return start


def _normalize_function(body: str, params: str) -> str:
    local_names = {
        match.group(1) for match in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)", body)
    }
    local_names.update(
        name_match.group(1)
        for part in params.split(",")
        if (name_match := re.match(r"\s*([A-Za-z_$][\w$]*)", part))
    )
    normalized = re.sub(r"\bfunction\s+[A-Za-z_$][\w$]*", "function FN", body)
    normalized = re.sub(r"\([^)]*\)", "(ARGS)", normalized, count=1)
    for name in sorted(local_names, key=len, reverse=True):
        normalized = re.sub(rf"\b{re.escape(name)}\b", "LOCAL", normalized)
    return re.sub(r"\s+", "", normalized)


def _current_findings(code_quality_scan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = code_quality_scan.get("findings")
    if not isinstance(findings, list):
        return {}
    return {
        finding["fingerprint"]: finding
        for finding in findings
        if isinstance(finding, dict) and isinstance(finding.get("fingerprint"), str)
    }


def _ledger_entry(
    *,
    finding: dict[str, Any],
    status: str,
    reason: str,
    owner: str | None,
    expires: str | None,
) -> dict[str, Any]:
    return {
        "fingerprint": finding["fingerprint"],
        "status": status,
        "category": finding["category"],
        "severity": finding["severity"],
        "rule_id": finding["rule_id"],
        "file": finding["file"],
        "line": finding["line"],
        "score": finding["score"],
        "confidence": finding["confidence"],
        "verification": finding["verification"],
        "reason": reason,
        "owner": owner,
        "expires": expires,
    }


def _latest_previous_resolution_entries(repo_root: Path, run_id: str) -> list[dict[str, Any]]:
    runs_dir = repo_root.expanduser().resolve() / ".quality-runner" / "runs"
    if not runs_dir.is_dir():
        return []
    candidates = [
        path / "resolution-ledger.json"
        for path in sorted(runs_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
        if path.is_dir() and path.name != run_id and not path.is_symlink()
    ]
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            import json

            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = payload.get("entries")
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]
    return []


def _accepted_dispositions(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    dispositions = config.get("accepted_dispositions")
    if not isinstance(dispositions, list):
        return {}
    accepted: dict[str, dict[str, str]] = {}
    for item in dispositions:
        if not isinstance(item, dict):
            continue
        fingerprint = item.get("fingerprint")
        status = item.get("status")
        reason = item.get("reason")
        owner = item.get("owner")
        expires = item.get("expires")
        if (
            isinstance(fingerprint, str)
            and fingerprint
            and isinstance(status, str)
            and status in ACCEPTED_STATUSES
            and isinstance(reason, str)
            and reason
            and isinstance(owner, str)
            and owner
        ):
            accepted[fingerprint] = {
                "fingerprint": fingerprint,
                "status": status,
                "reason": reason,
                "owner": owner,
                **({"expires": expires} if isinstance(expires, str) and expires else {}),
            }
    return accepted


def _check_coverage(relative_path: str) -> list[str]:
    coverage = ["static-code-quality"]
    if _is_test_file(relative_path):
        coverage.append("test-quality")
    if _is_ui_file(relative_path):
        coverage.append("ui-structural")
    return coverage


def _verification_for_path(relative_path: str) -> str:
    if relative_path.startswith("quality_runner/") or relative_path.startswith("tests/"):
        return "python3.14 -m pytest -q"
    if relative_path.startswith("packages/api/"):
        return "pnpm --filter @soundscape/api typecheck && pnpm --filter @soundscape/api test"
    if relative_path.startswith("packages/web/") or relative_path.startswith("src/"):
        return "pnpm --filter @soundscape/web typecheck && pnpm --filter @soundscape/web test"
    if relative_path.startswith("apps/mobile/"):
        return "pnpm --filter @soundscape/mobile typecheck && pnpm --filter @soundscape/mobile test"
    return "Run the relevant formatter, typecheck, and tests for the touched package."


def _is_deep_nesting(stripped: str, block_depth: int) -> bool:
    return block_depth >= 3 and stripped.startswith(
        ("if ", "if(", "for ", "for(", "while ", "while(", "switch", "try", "catch")
    )


def _nested_ternary(line: str) -> bool:
    return line.count("?") >= 2 and ":" in line


def _is_source_file(relative_path: str) -> bool:
    return Path(relative_path).suffix in {".cjs", ".js", ".jsx", ".mjs", ".py", ".ts", ".tsx"}


def _is_javascript_source_file(relative_path: str) -> bool:
    return Path(relative_path).suffix in {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}


def _is_api_file(relative_path: str) -> bool:
    return relative_path.startswith("packages/api/src/")


def _is_runtime_file(relative_path: str) -> bool:
    return _is_source_file(relative_path) and not _is_test_file(relative_path)


def _is_router_path(relative_path: str) -> bool:
    return "routers/" in relative_path and not _is_test_file(relative_path)


def _is_page_file(relative_path: str) -> bool:
    return relative_path.endswith("/page.tsx") and "/app/" in f"/{relative_path}"


def _is_test_file(relative_path: str) -> bool:
    return re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", relative_path) is not None or bool(
        re.search(r"(?:^|/)test_[^/]+\.py$", relative_path)
        or re.search(r"(?:^|/)[^/]+_test\.py$", relative_path)
    )


def _has_todo_comment(line: str) -> bool:
    if not re.search(r"\b(?:TODO|FIXME|HACK|TBD)\b", line):
        return False
    stripped = line.lstrip()
    if stripped.startswith(("#", "//", "/*", "*")):
        return True
    return bool(
        re.search(r"\s(?:#|//)\s*(?:TODO|FIXME|HACK|TBD)\b", line)
    ) and not stripped.startswith(("'", '"'))


def _is_ui_file(relative_path: str) -> bool:
    suffix = Path(relative_path).suffix
    return suffix in {".css", ".html", ".jsx", ".tsx"} or "/web/" in relative_path


def _has_motion_without_reduced_motion(text: str) -> bool:
    has_motion = re.search(r"\b(?:animation|transition)\s*:", text) is not None
    return has_motion and "prefers-reduced-motion" not in text


def _split_lines(text: str) -> list[str]:
    if not text:
        return []
    lines = text.splitlines()
    return lines


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
