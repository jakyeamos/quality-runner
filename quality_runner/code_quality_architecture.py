from __future__ import annotations

import posixpath
import re
from fnmatch import fnmatchcase
from typing import Any

from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import _is_test_file, _verification_for_path

SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py")

FROM_IMPORT_RE = re.compile(
    r"""(?:^|[^\w$])
        (?:import|export)\s+
        (?:type\s+)?
        (?:
            \*\s+from
            |\{[^}]*\}\s+from
            |[^"'\n;]+?\s+from
        )
        \s*["']([^"']+)["']
    """,
    re.VERBOSE,
)
SIDE_EFFECT_IMPORT_RE = re.compile(r"""^\s*import\s+["']([^"']+)["']""")
REQUIRE_RE = re.compile(r"""\brequire\s*\(\s*["']([^"']+)["']\s*\)""")
DYNAMIC_IMPORT_RE = re.compile(r"""\bimport\s*\(\s*["']([^"']+)["']\s*\)""")


def architecture_findings(
    scanned_files: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    policy = _architecture_policy(config)
    if not policy["enabled"]:
        return []

    findings: list[dict[str, Any]] = []
    for rule in policy["import_boundaries"]:
        findings.extend(_import_boundary_findings(scanned_files, rule))
    for rule in policy["pattern_boundaries"]:
        findings.extend(_pattern_boundary_findings(scanned_files, rule))
    return findings


def _architecture_policy(config: dict[str, Any]) -> dict[str, Any]:
    section = config.get("architecture")
    if not isinstance(section, dict):
        return {"enabled": False, "import_boundaries": [], "pattern_boundaries": []}
    enabled = section.get("enabled") is True
    import_boundaries = section.get("import_boundaries")
    pattern_boundaries = section.get("pattern_boundaries")
    return {
        "enabled": enabled,
        "import_boundaries": import_boundaries if isinstance(import_boundaries, list) else [],
        "pattern_boundaries": pattern_boundaries if isinstance(pattern_boundaries, list) else [],
    }


def _import_boundary_findings(
    scanned_files: list[dict[str, Any]],
    rule: dict[str, Any],
) -> list[dict[str, Any]]:
    rule_id = str(rule.get("id", ""))
    sources = [item for item in rule.get("sources", []) if isinstance(item, str)]
    disallowed = [item for item in rule.get("disallowed_imports", []) if isinstance(item, str)]
    allowed = [item for item in rule.get("allowed_imports", []) if isinstance(item, str)]
    if not rule_id or not sources or not disallowed:
        return []

    severity = rule.get("severity")
    if severity not in {"warning", "observation"}:
        severity = "warning"
    risk = str(
        rule.get("risk")
        or "Cross-layer imports couple modules to implementation details and make refactors unsafe."
    )
    expected = str(
        rule.get("expected")
        or "Move access behind the configured layer boundary or import only approved shared surfaces."
    )
    full_rule_id = f"architecture-import-boundary:{rule_id}"

    findings: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if not _path_matches_any(relative_path, sources):
            continue
        lines = item.get("lines")
        if not isinstance(lines, list):
            continue
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, str):
                continue
            for specifier in _extract_import_specifiers(line):
                if not _import_violates_boundary(
                    source_file=relative_path,
                    specifier=specifier,
                    disallowed_patterns=disallowed,
                    allowed_patterns=allowed,
                ):
                    continue
                findings.append(
                    _finding(
                        category="architecture",
                        severity=severity,
                        confidence="medium",
                        file=relative_path,
                        line=index,
                        rule_id=full_rule_id,
                        evidence=line,
                        expected_improvement=expected,
                        risk=risk,
                        verification=_verification_for_path(relative_path),
                        remediation_bucket="architecture contract",
                    )
                )
    return findings


def _pattern_boundary_findings(
    scanned_files: list[dict[str, Any]],
    rule: dict[str, Any],
) -> list[dict[str, Any]]:
    rule_id = str(rule.get("id", ""))
    paths = [item for item in rule.get("paths", []) if isinstance(item, str)]
    patterns = [item for item in rule.get("disallowed_patterns", []) if isinstance(item, str)]
    if not rule_id or not paths or not patterns:
        return []

    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error:
            continue
    if not compiled:
        return []

    severity = rule.get("severity")
    if severity not in {"warning", "observation"}:
        severity = "warning"
    risk = str(
        rule.get("risk")
        or "Forbidden runtime patterns in declarative modules make contracts harder to reuse and test."
    )
    expected = str(
        rule.get("expected")
        or "Keep declarative modules side-effect free; move runtime work to services or handlers."
    )
    full_rule_id = f"architecture-pattern-boundary:{rule_id}"

    findings: list[dict[str, Any]] = []
    for item in scanned_files:
        relative_path = str(item["path"])
        if _is_test_file(relative_path) or not _path_matches_any(relative_path, paths):
            continue
        lines = item.get("lines")
        if not isinstance(lines, list):
            continue
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, str):
                continue
            for pattern_index, pattern in enumerate(compiled):
                if not pattern.search(line):
                    continue
                findings.append(
                    _finding(
                        category="architecture",
                        severity=severity,
                        confidence="medium",
                        file=relative_path,
                        line=index,
                        rule_id=f"{full_rule_id}:{pattern_index}",
                        evidence=line,
                        expected_improvement=expected,
                        risk=risk,
                        verification=_verification_for_path(relative_path),
                        remediation_bucket="architecture contract",
                    )
                )
    return findings


def _extract_import_specifiers(line: str) -> list[str]:
    specifiers: list[str] = []
    for match in FROM_IMPORT_RE.finditer(line):
        specifiers.append(match.group(1))
    side_effect = SIDE_EFFECT_IMPORT_RE.match(line)
    if side_effect is not None:
        specifiers.append(side_effect.group(1))
    for match in REQUIRE_RE.finditer(line):
        specifiers.append(match.group(1))
    for match in DYNAMIC_IMPORT_RE.finditer(line):
        specifiers.append(match.group(1))
    return specifiers


def _import_violates_boundary(
    *,
    source_file: str,
    specifier: str,
    disallowed_patterns: list[str],
    allowed_patterns: list[str],
) -> bool:
    candidates = _import_match_candidates(source_file, specifier)
    disallowed = any(
        _path_matches_glob(candidate, pattern)
        for candidate in candidates
        for pattern in disallowed_patterns
    )
    if not disallowed:
        return False
    if not allowed_patterns:
        return True
    return not any(
        _path_matches_glob(candidate, pattern)
        for candidate in candidates
        for pattern in allowed_patterns
    )


def _import_match_candidates(source_file: str, specifier: str) -> list[str]:
    raw = specifier.strip()
    if not raw:
        return []
    candidates = [raw]
    for resolved in _resolve_relative_import(source_file, raw):
        if resolved not in candidates:
            candidates.append(resolved)
    return candidates


def _resolve_relative_import(source_file: str, specifier: str) -> list[str]:
    if not specifier.startswith("."):
        return []
    source_dir = posixpath.dirname(source_file.strip("/"))
    joined = posixpath.normpath(posixpath.join(source_dir, specifier)).lstrip("./")
    if not joined or joined.startswith(".."):
        return []
    if posixpath.splitext(joined)[1]:
        return [joined]
    resolved = [joined]
    for extension in SOURCE_EXTENSIONS:
        resolved.append(f"{joined}{extension}")
        resolved.append(posixpath.join(joined, f"index{extension}"))
    return resolved


def _path_matches_any(relative_path: str, patterns: list[str]) -> bool:
    return any(_path_matches_glob(relative_path, pattern) for pattern in patterns)


def _path_matches_glob(relative_path: str, pattern: str) -> bool:
    normalized_path = relative_path.strip("/")
    normalized_pattern = pattern.strip().strip("/")
    if not normalized_path or not normalized_pattern:
        return False
    if "/" not in normalized_pattern and not any(char in normalized_pattern for char in "*?[]"):
        return normalized_pattern in normalized_path.split("/")
    if fnmatchcase(normalized_path, normalized_pattern):
        return True
    if normalized_pattern.endswith("/**"):
        base = normalized_pattern[:-3].rstrip("/")
        if normalized_path == base or normalized_path.startswith(f"{base}/"):
            return True
        return fnmatchcase(normalized_path, base)
    return False
