from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.fleet.change_matrix import MATRIX_SCHEMA, SURFACE_DISTRIBUTIONS
from quality_runner.release_boundary_artifacts import (
    clean_room_install_check as _clean_room_install_check,
)
from quality_runner.release_boundary_artifacts import (
    distribution_archive_check as _distribution_archive_check,
)

RELEASE_BOUNDARY_SCHEMA = "quality-runner-release-boundary/v2"
DEFAULT_MATRIX_PATH = Path(".agents/change-surface-matrix.json")
DEFAULT_REPORT_PATH = Path(".quality-runner/release-boundary.json")
MAX_SCANNED_FILE_BYTES = 2 * 1024 * 1024


def _object_list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def release_boundary_payload(
    *,
    repo_root: Path,
    dist_dir: Path,
    run_clean_room: bool = True,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Fail closed when a public release surface is unclassified or leaks local state."""

    root = repo_root.expanduser().resolve()
    matrix_path = root / DEFAULT_MATRIX_PATH
    matrix = _read_object(matrix_path)
    checks: list[dict[str, Any]] = []
    branch, head_sha, dirty_path_count = _git_provenance(root, dist_dir)
    checks.append(_source_provenance_check(branch, head_sha, dirty_path_count))
    checks.append(_surface_classification_check(matrix, matrix_path=DEFAULT_MATRIX_PATH.as_posix()))

    release_policy = matrix.get("release_boundary")
    if not isinstance(release_policy, dict):
        checks.append(_blocked("release_policy", "release_boundary policy is missing"))
        checks.append(_blocked("tracked_public_content", "release policy is unavailable"))
        checks.append(_blocked("public_adapter_fixtures", "release policy is unavailable"))
        checks.append(_blocked("distribution_archives", "release policy is unavailable"))
        checks.append(_blocked("clean_room_install", "release policy is unavailable"))
    else:
        release_policy = cast(dict[str, Any], release_policy)
        content_policy = release_policy.get("tracked_content")
        checks.append(_tracked_content_check(root, content_policy))
        checks.append(_adapter_fixture_check(root, matrix, content_policy))
        archive_check, wheel = _distribution_archive_check(
            root,
            dist_dir.expanduser().resolve(),
            release_policy.get("artifacts"),
            content_policy,
        )
        checks.append(archive_check)
        if run_clean_room and wheel is not None and archive_check["status"] == "passed":
            checks.append(_clean_room_install_check(wheel))
        elif run_clean_room:
            checks.append(_blocked("clean_room_install", "a validated wheel is unavailable"))
        else:
            checks.append(_blocked("clean_room_install", "clean-room verification was not run"))

    blocked = [check for check in checks if check.get("status") != "passed"]
    subject = matrix.get("subject")
    repository_id = cast(dict[str, Any], subject).get("id") if isinstance(subject, dict) else None
    artifacts: list[object] = []
    for check in checks:
        if check.get("id") == "distribution_archives":
            artifacts = _object_list(check.get("artifacts", []))
            break
    return {
        "schema": RELEASE_BOUNDARY_SCHEMA,
        "status": "passed" if not blocked else "blocked",
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "producer": {"name": "quality-runner", "version": __version__},
        "repository": {
            "id": repository_id or root.name,
            "branch": branch,
            "head_sha": head_sha,
            "dirty_path_count": dirty_path_count,
        },
        "matrix": {
            "path": DEFAULT_MATRIX_PATH.as_posix(),
            "sha256": _sha256_path(matrix_path),
        },
        "distribution_classes": sorted(SURFACE_DISTRIBUTIONS),
        "artifacts": artifacts,
        "checks": checks,
        "blocking_check_ids": [str(check["id"]) for check in blocked],
    }


def write_release_boundary_report(report: dict[str, Any], output_path: Path) -> Path:
    """Atomically persist the sanitized release receipt for downstream consumers."""

    path = output_path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _git_provenance(root: Path, dist_dir: Path) -> tuple[str | None, str | None, int]:
    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

    try:
        branch = git("symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() or None
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # CI providers commonly check out a detached commit. In that case the
        # branch name must be recovered from an actual local Git ref below.
        branch = None

    try:
        head_sha = git("rev-parse", "--verify", "HEAD").stdout.strip() or None
        status = git("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None, None, 0

    if branch is None and head_sha is not None:
        try:
            ref_output = git(
                "for-each-ref",
                "--format=%(refname)%00%(objectname)%00%(*objectname)",
                "refs/heads",
                "refs/remotes",
                "refs/tags",
            ).stdout
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            ref_output = ""

        refs_at_head: set[str] = set()
        for line in ref_output.splitlines():
            parts = line.split("\0")
            if len(parts) != 3:
                continue
            ref_name, object_name, peeled_object_name = parts
            if head_sha in {object_name, peeled_object_name} and not ref_name.endswith("/HEAD"):
                refs_at_head.add(ref_name)

        def short_ref(ref_name: str) -> str:
            for prefix in ("refs/heads/", "refs/remotes/"):
                if ref_name.startswith(prefix):
                    return ref_name[len(prefix) :]
            return ref_name.removeprefix("refs/")

        pull_merge_refs = sorted(
            ref
            for ref in refs_at_head
            if ref.startswith("refs/remotes/pull/") and ref.endswith("/merge")
        )
        tag_refs = sorted(ref for ref in refs_at_head if ref.startswith("refs/tags/"))
        local_refs = sorted(ref for ref in refs_at_head if ref.startswith("refs/heads/"))
        if len(pull_merge_refs) == 1:
            branch = short_ref(pull_merge_refs[0])
        elif len(tag_refs) == 1:
            branch = short_ref(tag_refs[0])
        elif len(local_refs) == 1:
            branch = short_ref(local_refs[0])
        elif len(refs_at_head) == 1:
            branch = short_ref(next(iter(refs_at_head)))

    excluded_prefixes = {DEFAULT_REPORT_PATH.as_posix()}
    try:
        relative_dist = dist_dir.expanduser().resolve().relative_to(root).as_posix().rstrip("/")
    except ValueError:
        relative_dist = ""
    if relative_dist:
        excluded_prefixes.add(f"{relative_dist}/")
    dirty_paths: list[str] = []
    for entry in status.split("\0"):
        if len(entry) < 4:
            continue
        path = entry[3:].split(" -> ")[-1]
        if any(path == prefix or path.startswith(prefix) for prefix in excluded_prefixes):
            continue
        dirty_paths.append(path)
    return branch, head_sha, len(dirty_paths)


def _source_provenance_check(
    branch: str | None, head_sha: str | None, dirty_path_count: int
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    if branch is None:
        violations.append({"rule": "branch-unavailable", "path": "repository.branch"})
    if head_sha is None:
        violations.append({"rule": "head-unavailable", "path": "repository.head_sha"})
    if dirty_path_count:
        violations.append(
            {
                "rule": "uncommitted-release-input",
                "path": "repository",
                "count": dirty_path_count,
            }
        )
    check = _check("source_provenance", violations)
    check["branch"] = branch
    check["head_sha"] = head_sha
    check["dirty_path_count"] = dirty_path_count
    return check


def _surface_classification_check(matrix: dict[str, Any], *, matrix_path: str) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    if matrix.get("schema_version") != MATRIX_SCHEMA:
        violations.append({"rule": "matrix-schema", "path": matrix_path})
    surfaces = matrix.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        violations.append({"rule": "missing-surfaces", "path": matrix_path})
        surface_items: list[object] = []
    else:
        surface_items = cast(list[object], surfaces)
    for index, surface in enumerate(surface_items):
        label = f"surfaces[{index}]"
        if not isinstance(surface, dict):
            violations.append({"rule": "invalid-surface", "path": label})
            continue
        surface = cast(dict[str, Any], surface)
        if surface.get("status", "applicable") == "not_applicable":
            continue
        distribution = surface.get("distribution")
        if distribution not in SURFACE_DISTRIBUTIONS:
            violations.append({"rule": "unclassified-distribution", "path": label})
        if distribution == "public_adapter" and not _string_list(surface.get("contract_fixtures")):
            violations.append({"rule": "missing-contract-fixture", "path": label})
    return _check("surface_classification", violations)


def _tracked_content_check(root: Path, policy: object) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return _blocked("tracked_public_content", "tracked content policy is missing")
    policy = cast(dict[str, Any], policy)
    include_globs = _string_list(policy.get("include_globs"))
    local_only_globs = _string_list(policy.get("local_only_globs"))
    patterns, pattern_errors = _content_patterns(policy)
    violations = list(pattern_errors)
    if not include_globs:
        violations.append({"rule": "missing-include-globs", "path": str(DEFAULT_MATRIX_PATH)})
        return _check("tracked_public_content", violations)
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return _blocked("tracked_public_content", "tracked file inventory is unavailable")
    tracked = [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    tracked_local_only = [path for path in tracked if _matches_any(path, local_only_globs)]
    violations.extend(
        {"rule": "tracked-local-only-content", "path": path} for path in tracked_local_only
    )
    selected = [
        path
        for path in tracked
        if _matches_any(path, include_globs) and path not in tracked_local_only
    ]
    for relative in selected:
        violations.extend(_scan_text_path(root / relative, relative, patterns))
    check = _check("tracked_public_content", violations)
    check["files_scanned"] = len(selected)
    return check


def _adapter_fixture_check(
    root: Path, matrix: dict[str, Any], content_policy: object
) -> dict[str, Any]:
    patterns, pattern_errors = _content_patterns(content_policy)
    violations = list(pattern_errors)
    fixture_paths: set[str] = set()
    surfaces = matrix.get("surfaces")
    if isinstance(surfaces, list):
        for surface in cast(list[object], surfaces):
            if not isinstance(surface, dict):
                continue
            surface = cast(dict[str, Any], surface)
            if surface.get("distribution") != "public_adapter":
                continue
            fixture_paths.update(_string_list(surface.get("contract_fixtures")))
    if not fixture_paths:
        violations.append(
            {"rule": "missing-public-adapter-fixtures", "path": str(DEFAULT_MATRIX_PATH)}
        )
    for relative in sorted(fixture_paths):
        fixture = root / relative
        if not fixture.is_file():
            violations.append({"rule": "fixture-missing", "path": relative})
            continue
        try:
            json.loads(fixture.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            violations.append({"rule": "fixture-invalid-json", "path": relative})
            continue
        violations.extend(_scan_text_path(fixture, relative, patterns))
    check = _check("public_adapter_fixtures", violations)
    check["fixtures"] = [
        {
            "path": relative,
            "sha256": _sha256_path(root / relative),
        }
        for relative in sorted(fixture_paths)
        if (root / relative).is_file()
    ]
    return check


def _content_patterns(
    policy: object,
) -> tuple[list[tuple[str, re.Pattern[str]]], list[dict[str, Any]]]:
    if not isinstance(policy, dict):
        return [], [{"rule": "tracked-content-policy-missing", "path": str(DEFAULT_MATRIX_PATH)}]
    policy = cast(dict[str, Any], policy)
    patterns: list[tuple[str, re.Pattern[str]]] = []
    errors: list[dict[str, Any]] = []
    rules = policy.get("forbidden_patterns")
    if not isinstance(rules, list) or not rules:
        return [], [{"rule": "forbidden-patterns-missing", "path": str(DEFAULT_MATRIX_PATH)}]
    for index, rule in enumerate(cast(list[object], rules)):
        if (
            not isinstance(rule, dict)
            or not isinstance(cast(dict[str, Any], rule).get("id"), str)
            or not isinstance(cast(dict[str, Any], rule).get("pattern"), str)
        ):
            errors.append(
                {"rule": "invalid-forbidden-pattern", "path": f"forbidden_patterns[{index}]"}
            )
            continue
        rule = cast(dict[str, Any], rule)
        try:
            patterns.append((str(rule["id"]), re.compile(str(rule["pattern"]), re.IGNORECASE)))
        except re.error:
            errors.append(
                {"rule": "invalid-forbidden-regex", "path": f"forbidden_patterns[{index}]"}
            )
    return patterns, errors


def _scan_text_path(
    path: Path, display_path: str, patterns: list[tuple[str, re.Pattern[str]]]
) -> list[dict[str, Any]]:
    try:
        if path.stat().st_size > MAX_SCANNED_FILE_BYTES:
            return [{"rule": "tracked-file-too-large", "path": display_path}]
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [{"rule": "tracked-file-unreadable", "path": display_path}]
    return _pattern_violations(content, display_path, patterns)


def _pattern_violations(
    content: str, display_path: str, patterns: list[tuple[str, re.Pattern[str]]]
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for rule_id, pattern in patterns:
        for match in pattern.finditer(content):
            violations.append(
                {
                    "rule": rule_id,
                    "path": display_path,
                    "line": content.count("\n", 0, match.start()) + 1,
                }
            )
    return violations


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _sha256_path(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()
        for item in cast(list[object], value)
        if isinstance(item, str) and item.strip()
    ]


def _check(check_id: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "passed" if not violations else "blocked",
        "violations": violations,
    }


def _blocked(check_id: str, reason: str, **details: object) -> dict[str, Any]:
    return {"id": check_id, "status": "blocked", "reason": reason, **details}
