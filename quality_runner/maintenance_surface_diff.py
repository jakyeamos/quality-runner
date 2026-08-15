from __future__ import annotations

import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

WORKTREE_REF = "WORKTREE"
MAX_PATCH_BYTES = 2_000_000

_TEST_PATH = re.compile(r"(^|/)(tests?|specs?|__tests__)(/|$)|(^|/)(test_|.*[._](?:test|spec)\.)")
_PRODUCTION_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java"}
_PUBLIC_DECLARATION = re.compile(
    r"^(?:export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+"
    r"|(?:async\s+)?def\s+|class\s+|pub\s+(?:async\s+)?(?:fn|struct|enum|trait|type|const)\s+"
    r"|(?:func|type|const|var)\s+[A-Z])"
)
_COMPATIBILITY = re.compile(r"(?i)\b(?:compat(?:ibility)?|legacy|deprecated|shim|adapter)\b")
_CONFIG_OR_FLAG = re.compile(
    r"(?i)\b(?:feature[_-]?flags?|flags?|config(?:uration)?|process\.env|os\.environ|getenv|env::var)\b"
)


@dataclass(frozen=True)
class Comparison:
    requested_base: str
    requested_head: str
    base_commit: str
    head_commit: str
    comparison_base_commit: str
    working_tree: bool


def comparison_for(root: Path, *, base_ref: str, head_ref: str) -> Comparison:
    git_output(root, "rev-parse", "--is-inside-work-tree")
    base_commit = git_output(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    if head_ref == WORKTREE_REF:
        head_commit = git_output(root, "rev-parse", "--verify", "HEAD^{commit}")
        comparison_base = base_commit
        working_tree = True
    else:
        head_commit = git_output(root, "rev-parse", "--verify", f"{head_ref}^{{commit}}")
        comparison_base = git_output(root, "merge-base", base_commit, head_commit)
        working_tree = False
    return Comparison(base_ref, head_ref, base_commit, head_commit, comparison_base, working_tree)


def changed_files(root: Path, comparison: Comparison) -> list[dict[str, Any]]:
    target = [] if comparison.working_tree else [comparison.head_commit]
    numstat = git_output(
        root, "diff", "--numstat", "--no-renames", comparison.comparison_base_commit, *target
    )
    stats: dict[str, tuple[int, int]] = {}
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            stats[parts[2]] = (_number(parts[0]), _number(parts[1]))

    name_status = git_output(
        root, "diff", "--name-status", "-M", comparison.comparison_base_commit, *target
    )
    changes: list[dict[str, Any]] = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        raw_status = parts[0]
        path = parts[-1]
        old_path = parts[1] if raw_status.startswith("R") and len(parts) > 2 else None
        if old_path:
            added = stats.get(path, (0, 0))[0]
            removed = stats.get(old_path, (0, 0))[1]
        else:
            added, removed = stats.get(path, (0, 0))
        changes.append(
            {
                "path": path,
                "old_path": old_path,
                "status": _status(raw_status),
                "added": added,
                "removed": removed,
                "category": _path_category(path),
                "untracked": False,
            }
        )
    if comparison.working_tree:
        tracked = {item["path"] for item in changes}
        for path in git_output(root, "ls-files", "--others", "--exclude-standard", "-z").split(
            "\0"
        ):
            if not path or path in tracked:
                continue
            full_path = root / path
            added = _count_lines(full_path) if full_path.is_file() else 0
            changes.append(
                {
                    "path": path,
                    "old_path": None,
                    "status": "added",
                    "added": added,
                    "removed": 0,
                    "category": _path_category(path),
                    "untracked": True,
                }
            )
    return sorted(changes, key=lambda item: item["path"])


def diff_patch(root: Path, comparison: Comparison) -> str:
    target = [] if comparison.working_tree else [comparison.head_commit]
    patch = git_output(
        root,
        "diff",
        "--unified=0",
        "--no-color",
        "--no-ext-diff",
        comparison.comparison_base_commit,
        *target,
    )
    encoded = patch.encode("utf-8")
    if len(encoded) > MAX_PATCH_BYTES:
        return encoded[:MAX_PATCH_BYTES].decode("utf-8", errors="ignore")
    return patch


def patch_candidates(
    root: Path, patch: str, changes: list[dict[str, Any]]
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {
        "public_surfaces": [],
        "flags_or_config": [],
        "compatibility": [],
    }
    current_path = ""
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
            continue
        if not current_path or not line.startswith("+") or line.startswith("+++"):
            continue
        _append_candidates(result, path=current_path, source=line[1:].strip())
    for item in changes:
        if not item["untracked"]:
            continue
        try:
            content = (root / item["path"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in content.splitlines():
            _append_candidates(result, path=item["path"], source=line.strip())
    return {key: _unique_candidates(items) for key, items in result.items()}


def dependency_delta(
    root: Path, comparison: Comparison, changes: list[dict[str, Any]]
) -> list[dict[str, str]]:
    manifests = {
        item["path"]
        for item in changes
        if PurePosixPath(item["path"]).name
        in {"package.json", "pyproject.toml", "Cargo.toml", "go.mod"}
        or PurePosixPath(item["path"]).name.startswith("requirements")
    }
    added: list[dict[str, str]] = []
    for path in sorted(manifests):
        before = _file_at(root, comparison.comparison_base_commit, path)
        after = _head_file(root, comparison, path)
        before_dependencies = _manifest_dependencies(path, before)
        after_dependencies = _manifest_dependencies(path, after)
        for name in sorted(after_dependencies - before_dependencies):
            added.append({"name": name, "manifest": path})
    return added


def file_summary(changes: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "total": len(changes),
        "added": 0,
        "modified": 0,
        "deleted": 0,
        "renamed": 0,
        "paths": changes,
    }
    for item in changes:
        result[item["status"]] += 1
    return result


def line_summary(changes: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    result = {key: {"added": 0, "removed": 0} for key in ("production", "test", "other")}
    for item in changes:
        category = item["category"]
        result[category]["added"] += item["added"]
        result[category]["removed"] += item["removed"]
    return result


def git_output(root: Path, *args: str, allow_no_match: bool = False) -> str:
    result = _git_result(root, *args)
    if result.returncode != 0 and not (allow_no_match and result.returncode == 1):
        detail = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise ValueError(detail)
    return result.stdout.rstrip("\n")


def _append_candidates(result: dict[str, list[dict[str, str]]], *, path: str, source: str) -> None:
    candidate = {"path": path, "evidence": source[:240]}
    if _path_category(path) == "production" and _PUBLIC_DECLARATION.match(source):
        result["public_surfaces"].append(candidate)
    if _CONFIG_OR_FLAG.search(source):
        result["flags_or_config"].append(candidate)
    if _COMPATIBILITY.search(source):
        result["compatibility"].append(candidate)


def _manifest_dependencies(path: str, content: str | None) -> set[str]:
    if not content:
        return set()
    name = PurePosixPath(path).name
    try:
        if name == "package.json":
            raw_payload: object = json.loads(content)
            if not isinstance(raw_payload, dict):
                return set()
            payload = cast(dict[str, object], raw_payload)
            return {
                key
                for section in (
                    "dependencies",
                    "devDependencies",
                    "peerDependencies",
                    "optionalDependencies",
                )
                if isinstance(payload.get(section), dict)
                for key in cast(dict[str, object], payload[section])
            }
        if name == "pyproject.toml":
            payload = cast(dict[str, object], tomllib.loads(content))
            raw_project = payload.get("project", {})
            project = cast(dict[str, object], raw_project) if isinstance(raw_project, dict) else {}
            raw_dependencies = project.get("dependencies", [])
            dependencies = (
                cast(list[object], raw_dependencies) if isinstance(raw_dependencies, list) else []
            )
            names = {_requirement_name(item) for item in dependencies if isinstance(item, str)}
            groups = payload.get("dependency-groups", {})
            if isinstance(groups, dict):
                names.update(
                    _requirement_name(item)
                    for values in cast(dict[str, object], groups).values()
                    if isinstance(values, list)
                    for item in cast(list[object], values)
                    if isinstance(item, str)
                )
            return {item for item in names if item}
        if name == "Cargo.toml":
            payload = cast(dict[str, object], tomllib.loads(content))
            return {
                key
                for section in ("dependencies", "dev-dependencies", "build-dependencies")
                if isinstance(payload.get(section), dict)
                for key in cast(dict[str, object], payload[section])
            }
        if name == "go.mod":
            return set(re.findall(r"(?m)^\s*([\w./-]+)\s+v\d", content))
        if name.startswith("requirements"):
            return {
                item for line in content.splitlines() if (item := _requirement_name(line.strip()))
            }
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, TypeError):
        return set()
    return set()


def _file_at(root: Path, commit: str, path: str) -> str | None:
    result = _git_result(root, "show", f"{commit}:{path}")
    return result.stdout if result.returncode == 0 else None


def _head_file(root: Path, comparison: Comparison, path: str) -> str | None:
    if comparison.working_tree:
        target = root / path
        try:
            return target.read_text(encoding="utf-8") if target.is_file() else None
        except (OSError, UnicodeDecodeError):
            return None
    return _file_at(root, comparison.head_commit, path)


def _git_result(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _path_category(path: str) -> str:
    if _TEST_PATH.search(path):
        return "test"
    pure = PurePosixPath(path)
    if pure.suffix in _PRODUCTION_SUFFIXES and not path.startswith(("docs/", "examples/")):
        return "production"
    return "other"


def _status(value: str) -> str:
    return {"A": "added", "D": "deleted", "R": "renamed"}.get(value[0], "modified")


def _number(value: str) -> int:
    return int(value) if value.isdigit() else 0


def _count_lines(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    if len(data) > MAX_PATCH_BYTES or b"\0" in data:
        return 0
    return len(data.splitlines())


def _requirement_name(value: str) -> str:
    candidate = value.split(";", 1)[0].strip()
    if not candidate or candidate.startswith(("#", "-")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", candidate)
    return match.group(1).lower() if match else ""


def _unique_candidates(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return list({(item["path"], item["evidence"]): item for item in items}.values())
