from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from quality_runner.fleet.change_matrix import MATRIX_SCHEMA, SURFACE_DISTRIBUTIONS

RELEASE_BOUNDARY_SCHEMA = "quality-runner-release-boundary/v1"
DEFAULT_MATRIX_PATH = Path(".agents/change-surface-matrix.json")
MAX_SCANNED_FILE_BYTES = 2 * 1024 * 1024
TEXT_ARCHIVE_SUFFIXES = {
    ".cfg",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def release_boundary_payload(
    *,
    repo_root: Path,
    dist_dir: Path,
    run_clean_room: bool = True,
) -> dict[str, Any]:
    """Fail closed when a public release surface is unclassified or leaks local state."""

    root = repo_root.expanduser().resolve()
    matrix_path = root / DEFAULT_MATRIX_PATH
    matrix = _read_object(matrix_path)
    checks: list[dict[str, Any]] = []
    checks.append(_surface_classification_check(matrix, matrix_path=DEFAULT_MATRIX_PATH.as_posix()))

    release_policy = matrix.get("release_boundary") if isinstance(matrix, dict) else None
    if not isinstance(release_policy, dict):
        checks.append(_blocked("release_policy", "release_boundary policy is missing"))
        checks.append(_blocked("tracked_public_content", "release policy is unavailable"))
        checks.append(_blocked("public_adapter_fixtures", "release policy is unavailable"))
        checks.append(_blocked("distribution_archives", "release policy is unavailable"))
        checks.append(_blocked("clean_room_install", "release policy is unavailable"))
    else:
        content_policy = release_policy.get("tracked_content")
        checks.append(_tracked_content_check(root, content_policy))
        checks.append(_adapter_fixture_check(root, matrix, content_policy))
        archive_check, wheel = _distribution_archive_check(
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
    return {
        "schema": RELEASE_BOUNDARY_SCHEMA,
        "status": "passed" if not blocked else "blocked",
        "repository": str(root),
        "matrix_path": str(matrix_path),
        "distribution_classes": sorted(SURFACE_DISTRIBUTIONS),
        "checks": checks,
        "blocking_check_ids": [str(check["id"]) for check in blocked],
    }


def _surface_classification_check(matrix: dict[str, Any], *, matrix_path: str) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    if matrix.get("schema_version") != MATRIX_SCHEMA:
        violations.append({"rule": "matrix-schema", "path": matrix_path})
    surfaces = matrix.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        violations.append({"rule": "missing-surfaces", "path": matrix_path})
        surfaces = []
    for index, surface in enumerate(surfaces):
        label = f"surfaces[{index}]"
        if not isinstance(surface, dict):
            violations.append({"rule": "invalid-surface", "path": label})
            continue
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
        for surface in surfaces:
            if not isinstance(surface, dict) or surface.get("distribution") != "public_adapter":
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
    check["fixtures"] = sorted(fixture_paths)
    return check


def _distribution_archive_check(
    dist_dir: Path, artifact_policy: object, content_policy: object
) -> tuple[dict[str, Any], Path | None]:
    if not isinstance(artifact_policy, dict):
        return _blocked("distribution_archives", "artifact allowlist is missing"), None
    wheels = sorted(dist_dir.glob("*.whl")) if dist_dir.is_dir() else []
    sdists = sorted(dist_dir.glob("*.tar.gz")) if dist_dir.is_dir() else []
    violations: list[dict[str, Any]] = []
    if len(wheels) != 1:
        violations.append({"rule": "wheel-count", "path": str(dist_dir), "count": len(wheels)})
    if len(sdists) != 1:
        violations.append({"rule": "sdist-count", "path": str(dist_dir), "count": len(sdists)})
    patterns, pattern_errors = _content_patterns(content_policy)
    violations.extend(pattern_errors)
    if len(wheels) == 1:
        violations.extend(_inspect_wheel(wheels[0], artifact_policy.get("wheel"), patterns))
    if len(sdists) == 1:
        violations.extend(_inspect_sdist(sdists[0], artifact_policy.get("sdist"), patterns))
    check = _check("distribution_archives", violations)
    check["wheel"] = wheels[0].name if len(wheels) == 1 else None
    check["sdist"] = sdists[0].name if len(sdists) == 1 else None
    return check, wheels[0] if len(wheels) == 1 else None


def _inspect_wheel(
    wheel: Path, policy: object, patterns: list[tuple[str, re.Pattern[str]]]
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if not isinstance(policy, dict):
        return [{"rule": "wheel-allowlist-missing", "path": wheel.name}]
    try:
        with zipfile.ZipFile(wheel) as archive:
            for info in archive.infolist():
                name = info.filename.rstrip("/")
                if not name:
                    continue
                if not _safe_archive_name(name):
                    violations.append({"rule": "unsafe-archive-path", "path": name})
                    continue
                if not _artifact_path_allowed(name, policy):
                    violations.append({"rule": "wheel-path-not-allowlisted", "path": name})
                if not info.is_dir() and _is_text_archive_path(name):
                    violations.extend(_scan_archive_text(name, archive.read(info), patterns))
    except (OSError, zipfile.BadZipFile):
        violations.append({"rule": "wheel-unreadable", "path": wheel.name})
    return violations


def _inspect_sdist(
    sdist: Path, policy: object, patterns: list[tuple[str, re.Pattern[str]]]
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if not isinstance(policy, dict):
        return [{"rule": "sdist-allowlist-missing", "path": sdist.name}]
    try:
        with tarfile.open(sdist, mode="r:gz") as archive:
            for member in archive.getmembers():
                raw_name = member.name.rstrip("/")
                if not _safe_archive_name(raw_name):
                    violations.append({"rule": "unsafe-archive-path", "path": raw_name})
                    continue
                if member.issym() or member.islnk():
                    violations.append({"rule": "archive-link-not-allowed", "path": raw_name})
                    continue
                parts = PurePosixPath(raw_name).parts
                name = PurePosixPath(*parts[1:]).as_posix() if len(parts) > 1 else ""
                if not name:
                    continue
                if member.isdir():
                    continue
                if not _artifact_path_allowed(name, policy):
                    violations.append({"rule": "sdist-path-not-allowlisted", "path": name})
                if member.isfile() and _is_text_archive_path(name):
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        violations.extend(_scan_archive_text(name, extracted.read(), patterns))
    except (OSError, tarfile.TarError):
        violations.append({"rule": "sdist-unreadable", "path": sdist.name})
    return violations


def _clean_room_install_check(wheel: Path) -> dict[str, Any]:
    try:
        with tempfile.TemporaryDirectory(prefix="quality-runner-release-") as temporary:
            root = Path(temporary)
            venv = root / "venv"
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            executable_dir = venv / ("Scripts" if os.name == "nt" else "bin")
            python = executable_dir / ("python.exe" if os.name == "nt" else "python")
            quality_runner = executable_dir / (
                "quality-runner.exe" if os.name == "nt" else "quality-runner"
            )
            subprocess.run(
                [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            home = root / "home"
            home.mkdir()
            environment = {
                "HOME": str(home),
                "PATH": os.pathsep.join((str(executable_dir), os.defpath)),
                "XDG_CACHE_HOME": str(home / ".cache"),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local" / "share"),
            }
            if os.name == "nt" and "SYSTEMROOT" in os.environ:
                environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
            unavailable = [
                command
                for command in ("pronto", "leverage", "macctl")
                if shutil.which(command, path=environment["PATH"]) is not None
            ]
            if unavailable:
                return _blocked(
                    "clean_room_install",
                    "private integration executables are visible in the clean-room path",
                    integrations=unavailable,
                )
            for arguments in (("doctor", "--json"), ("release-smoke", "--json")):
                subprocess.run(
                    [str(quality_runner), *arguments],
                    cwd=home,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return _blocked("clean_room_install", "installed-wheel smoke failed")
    return {"id": "clean_room_install", "status": "passed", "integrations_present": []}


def _content_patterns(
    policy: object,
) -> tuple[list[tuple[str, re.Pattern[str]]], list[dict[str, Any]]]:
    if not isinstance(policy, dict):
        return [], [{"rule": "tracked-content-policy-missing", "path": str(DEFAULT_MATRIX_PATH)}]
    patterns: list[tuple[str, re.Pattern[str]]] = []
    errors: list[dict[str, Any]] = []
    rules = policy.get("forbidden_patterns")
    if not isinstance(rules, list) or not rules:
        return [], [{"rule": "forbidden-patterns-missing", "path": str(DEFAULT_MATRIX_PATH)}]
    for index, rule in enumerate(rules):
        if (
            not isinstance(rule, dict)
            or not isinstance(rule.get("id"), str)
            or not isinstance(rule.get("pattern"), str)
        ):
            errors.append(
                {"rule": "invalid-forbidden-pattern", "path": f"forbidden_patterns[{index}]"}
            )
            continue
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


def _scan_archive_text(
    name: str, content: bytes, patterns: list[tuple[str, re.Pattern[str]]]
) -> list[dict[str, Any]]:
    if len(content) > MAX_SCANNED_FILE_BYTES:
        return [{"rule": "archive-text-too-large", "path": name}]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return [{"rule": "archive-text-unreadable", "path": name}]
    return _pattern_violations(text, name, patterns)


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


def _artifact_path_allowed(path: str, policy: dict[str, Any]) -> bool:
    exact = set(_string_list(policy.get("allow_paths")))
    prefixes = tuple(_string_list(policy.get("allow_prefixes")))
    globs = _string_list(policy.get("allow_globs"))
    return path in exact or path.startswith(prefixes) or _matches_any(path, globs)


def _safe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _is_text_archive_path(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in TEXT_ARCHIVE_SUFFIXES or name.endswith(
        ("METADATA", "PKG-INFO")
    )


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


def _check(check_id: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "passed" if not violations else "blocked",
        "violations": violations,
    }


def _blocked(check_id: str, reason: str, **details: object) -> dict[str, Any]:
    return {"id": check_id, "status": "blocked", "reason": reason, **details}
