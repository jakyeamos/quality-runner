from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, cast

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


def distribution_archive_check(
    root: Path,
    dist_dir: Path,
    artifact_policy: object,
    content_policy: object,
) -> tuple[dict[str, Any], Path | None]:
    if not isinstance(artifact_policy, dict):
        return _blocked("distribution_archives", "artifact allowlist is missing"), None
    artifact_policy = cast(dict[str, Any], artifact_policy)
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
    check["artifacts"] = [
        {
            "kind": kind,
            "path": _repository_relative_path(root, path),
            "sha256": _sha256_path(path),
            "size_bytes": path.stat().st_size,
        }
        for kind, candidates in (("wheel", wheels), ("sdist", sdists))
        for path in candidates
        if len(candidates) == 1
    ]
    return check, wheels[0] if len(wheels) == 1 else None


def _inspect_wheel(
    wheel: Path, policy: object, patterns: list[tuple[str, re.Pattern[str]]]
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if not isinstance(policy, dict):
        return [{"rule": "wheel-allowlist-missing", "path": wheel.name}]
    policy = cast(dict[str, Any], policy)
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
    policy = cast(dict[str, Any], policy)
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
                if not name or member.isdir():
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


def clean_room_install_check(wheel: Path) -> dict[str, Any]:
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
        return [], [
            {
                "rule": "tracked-content-policy-missing",
                "path": ".agents/change-surface-matrix.json",
            }
        ]
    policy = cast(dict[str, Any], policy)
    patterns: list[tuple[str, re.Pattern[str]]] = []
    errors: list[dict[str, Any]] = []
    rules = policy.get("forbidden_patterns")
    if not isinstance(rules, list) or not rules:
        return [], [
            {
                "rule": "forbidden-patterns-missing",
                "path": ".agents/change-surface-matrix.json",
            }
        ]
    rules = cast(list[object], rules)
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(
                {"rule": "invalid-forbidden-pattern", "path": f"forbidden_patterns[{index}]"}
            )
            continue
        rule = cast(dict[str, Any], rule)
        if not isinstance(rule.get("id"), str) or not isinstance(rule.get("pattern"), str):
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


def _scan_archive_text(
    name: str, content: bytes, patterns: list[tuple[str, re.Pattern[str]]]
) -> list[dict[str, Any]]:
    if len(content) > MAX_SCANNED_FILE_BYTES:
        return [{"rule": "archive-text-too-large", "path": name}]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return [{"rule": "archive-text-unreadable", "path": name}]
    violations: list[dict[str, Any]] = []
    for rule_id, pattern in patterns:
        for match in pattern.finditer(text):
            violations.append(
                {"rule": rule_id, "path": name, "line": text.count("\n", 0, match.start()) + 1}
            )
    return violations


def _artifact_path_allowed(path: str, policy: dict[str, Any]) -> bool:
    exact = set(_string_list(policy.get("allow_paths")))
    prefixes = tuple(_string_list(policy.get("allow_prefixes")))
    globs = _string_list(policy.get("allow_globs"))
    return (
        path in exact
        or path.startswith(prefixes)
        or any(fnmatch.fnmatchcase(path, pattern) for pattern in globs)
    )


def _repository_relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _safe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _is_text_archive_path(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in TEXT_ARCHIVE_SUFFIXES or name.endswith(
        ("METADATA", "PKG-INFO")
    )


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
    values = cast(list[object], value)
    return [str(item).strip() for item in values if isinstance(item, str) and item.strip()]


def _check(check_id: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "passed" if not violations else "blocked",
        "violations": violations,
    }


def _blocked(check_id: str, reason: str, **details: object) -> dict[str, Any]:
    return {"id": check_id, "status": "blocked", "reason": reason, **details}
