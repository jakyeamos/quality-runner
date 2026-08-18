from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import DEPLOYMENT_MARKERS, MAX_DOCUMENT_BYTES, relative_path

_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
_DIAGRAM_SUFFIXES = {".drawio", ".mmd", ".mermaid", ".puml", ".plantuml", ".svg"}
_DIAGRAM_MARKERS = (
    "architecture",
    "deployment",
    "diagram",
    "infrastructure",
    "network",
    "topology",
    "c4",
)
_SKIP_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
_MARKDOWN_LINK = re.compile(r"!?(?:\[[^\]]*\])\(([^)]+)\)")
_LINE_FRAGMENT = re.compile(r"^L(?P<start>\d+)(?:-L?(?P<end>\d+))?$")
_PINNED_GITHUB_SOURCE = re.compile(
    r"^https?://github\.com/[^/]+/[^/]+/blob/"
    r"(?P<commit>[0-9a-fA-F]{40})/(?P<path>[^#]+)#(?P<fragment>L\d+(?:-L?\d+)?)$"
)
_FLOATING_GITHUB_SOURCE = re.compile(
    r"^https?://github\.com/[^/]+/[^/]+/(?:blob|tree)/[^/]+/(?P<path>[^#]+)"
)
_VAGUE_NAMES = {
    "data",
    "do_work",
    "handler",
    "helper",
    "info",
    "manager",
    "process",
    "processor",
    "run",
    "stuff",
    "thing",
    "util",
    "utils",
}
_RATIONALE_MARKER = re.compile(
    r"(?:eslint-disable|noqa|type:\s*ignore|noinspection|nolint|noinspection|TODO|FIXME)",
    re.IGNORECASE,
)
_RATIONALE_DETAIL = re.compile(
    r"(?:because|reason|until|remove when|https?://|#[0-9]+|[A-Z]{2,}-[0-9]+)",
    re.IGNORECASE,
)
_NEWCOMER_SCHEMA = "quality-runner-developer-legibility-evidence/v1"
_NEWCOMER_TASKS = {"orient", "run", "locate_behavior", "explain_invariant", "bounded_change"}


def collect_orientation(documents: dict[str, str]) -> dict[str, Any]:
    readme_path = next(
        (path for path in documents if Path(path).name.lower() in {"readme.md", "readme.mdx"}),
        None,
    )
    text = documents.get(readme_path, "") if readme_path else ""
    lower = text.lower()
    return {
        "readme_path": readme_path,
        "purpose_present": bool(
            re.search(r"^#\s+.+", text, re.MULTILINE) and len(text.split()) >= 12
        ),
        "quick_start_present": bool(
            re.search(r"(?:quick\s*start|getting started|installation|development|setup)", lower)
            and re.search(
                r"```[^\n]*\n[^`]*(?:npm|pnpm|yarn|cargo|pytest|uv|make|go\s+(?:test|run)|python)",
                text,
                re.IGNORECASE,
            )
        ),
        "verification_present": bool(re.search(r"(?:test|verify|check|lint|typecheck)", lower)),
        "map_present": bool(
            re.search(r"(?:architecture|repository map|project structure|codebase|layout)", lower)
        ),
    }


def collect_semantic_naming(root: Path) -> dict[str, Any]:
    declarations = 0
    vague: list[dict[str, Any]] = []
    for path in iter_repository_files(root):
        if path.suffix.lower() not in _SOURCE_SUFFIXES or is_test_path(root, path):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines):
            name = public_declaration(path.suffix.lower(), line)
            if name is None:
                continue
            declarations += 1
            if name.lower() in _VAGUE_NAMES and len(vague) < 24:
                vague.append({"path": relative_path(root, path), "line": index + 1, "name": name})
    return {
        "declaration_count": declarations,
        "vague_name_count": len(vague),
        "vague_examples": vague,
        "semantic_review_required": True,
    }


def collect_rationale_markers(root: Path) -> dict[str, Any]:
    marker_count = 0
    unexplained: list[dict[str, Any]] = []
    for path in iter_repository_files(root):
        if path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines):
            if not _RATIONALE_MARKER.search(line):
                continue
            marker_count += 1
            context = " ".join(lines[max(0, index - 1) : index + 1])
            if not _RATIONALE_DETAIL.search(context) and len(unexplained) < 24:
                unexplained.append({"path": relative_path(root, path), "line": index + 1})
    return {
        "marker_count": marker_count,
        "unexplained_count": len(unexplained),
        "unexplained_examples": unexplained,
    }


def collect_executable_understanding(root: Path, documents: dict[str, str]) -> dict[str, Any]:
    combined = "\n".join(documents.values())
    test_paths = [
        relative_path(root, path)
        for path in iter_repository_files(root)
        if re.search(r"(?:^|/)(?:tests?|specs?|examples?)(?:/|$)", relative_path(root, path))
    ]
    commands = sorted(
        set(
            re.findall(
                r"(?:^|\n)\s*(?:\$\s*)?((?:npm|pnpm|yarn|cargo|pytest|uv|make|go)\s+[^\n`]+)",
                combined,
                re.IGNORECASE,
            )
        )
    )
    return {
        "test_surface_present": bool(test_paths),
        "test_paths": test_paths[:16],
        "documented_commands": commands[:16],
        "documented_command_present": bool(commands),
    }


def collect_newcomer_evidence(root: Path) -> dict[str, Any]:
    path = root / ".quality-runner/developer-legibility.json"
    if not path.is_file():
        return {"status": "missing", "path": relative_path(root, path), "valid": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "status": "invalid",
            "path": relative_path(root, path),
            "valid": False,
            "reason": str(error),
        }
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    passed = {
        str(item.get("id"))
        for item in tasks or []
        if isinstance(item, dict) and item.get("status") == "passed" and item.get("evidence")
    }
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        head = None
    valid = (
        payload.get("schema") == _NEWCOMER_SCHEMA
        and payload.get("target_commit") == head
        and passed >= _NEWCOMER_TASKS
    )
    return {
        "status": "validated" if valid else "invalid",
        "path": relative_path(root, path),
        "valid": valid,
        "target_commit": payload.get("target_commit"),
        "observed_commit": head,
        "passed_tasks": sorted(passed),
    }


def collect_traceability(root: Path, documents: dict[str, str]) -> dict[str, Any]:
    source_surface_present = any(
        is_source_file(path.as_posix()) for path in iter_repository_files(root)
    )
    valid: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    floating: list[dict[str, str]] = []
    for relative, content in sorted(documents.items()):
        for raw_target in _MARKDOWN_LINK.findall(content):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            parsed = parse_source_target(root, relative, target)
            if parsed is None:
                continue
            kind, detail, state = parsed
            item = {"source": relative, "detail": detail}
            if state == "valid" and kind == "source":
                valid.append(item)
            elif state == "floating":
                floating.append(item)
            elif state == "invalid":
                invalid.append(item)
    return {
        "source_surface_present": source_surface_present,
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "floating_count": len(floating),
        "valid": valid[:16],
        "invalid": invalid[:16],
        "floating": floating[:16],
    }


def parse_source_target(root: Path, source: str, target: str) -> tuple[str, str, str] | None:
    if target.startswith(("mailto:", "#")):
        return None
    pinned = _PINNED_GITHUB_SOURCE.match(target)
    if pinned:
        path = pinned.group("path")
        fragment = pinned.group("fragment")
        if not _LINE_FRAGMENT.match(fragment):
            return "source", f"pinned source link has an invalid line range: {target}", "invalid"
        local_target = root / path
        try:
            local_target = local_target.resolve()
            local_target.relative_to(root)
        except (OSError, ValueError):
            local_target = None
        if local_target is not None and local_target.is_file():
            line_state = validate_local_anchor(root, path, fragment)
            if line_state == "invalid":
                return (
                    "source",
                    f"pinned source link has an invalid local line range: {target}",
                    "invalid",
                )
        return "source", f"commit-pinned source anchor: {path}#{fragment}", "valid"
    floating = _FLOATING_GITHUB_SOURCE.match(target)
    if floating:
        return (
            "source",
            f"source link is branch/ref based and not commit-pinned: {floating.group('path')}",
            "floating",
        )
    if target.startswith(("http://", "https://")):
        return None
    path_part, _, fragment = target.partition("#")
    candidate = (root / source).parent / path_part
    try:
        candidate = candidate.resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return "source", f"source link escapes the repository: {target}", "invalid"
    if (
        not is_source_file(candidate.as_posix())
        and candidate.suffix.lower() not in _SOURCE_SUFFIXES
    ):
        return None
    if not candidate.is_file():
        return (
            "source",
            f"source target does not exist: {relative_path(root, candidate)}",
            "invalid",
        )
    if not fragment:
        return (
            "source",
            f"source link has no line-range anchor: {relative_path(root, candidate)}",
            "floating",
        )
    if (
        not _LINE_FRAGMENT.match(fragment)
        or validate_local_anchor(root, relative_path(root, candidate), fragment) == "invalid"
    ):
        return "source", f"source link has an invalid line range: {target}", "invalid"
    return (
        "source",
        f"checkout-local source anchor: {relative_path(root, candidate)}#{fragment}",
        "valid",
    )


def validate_local_anchor(root: Path, relative: str, fragment: str) -> str:
    path = root / relative
    match = _LINE_FRAGMENT.match(fragment)
    if not path.is_file() or not match:
        return "invalid"
    try:
        line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return "invalid"
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    return "valid" if 1 <= start <= end <= line_count else "invalid"


def collect_diagrams(
    root: Path, documents: dict[str, str], link_evidence: dict[str, Any]
) -> dict[str, Any]:
    diagram_files = [
        relative_path(root, path)
        for path in iter_repository_files(root)
        if path.suffix.lower() in _DIAGRAM_SUFFIXES
        and any(marker in path.as_posix().lower() for marker in _DIAGRAM_MARKERS)
    ][:64]
    linked_paths = [
        str(item["target"])
        for item in link_evidence.get("links", [])
        if isinstance(item, dict) and str(item.get("target", "")) in diagram_files
    ]
    combined = "\n".join(documents.values()).lower()
    inline_count = len(
        re.findall(
            r"```(?:mermaid|plantuml)\b[^\n]*\n(?:flowchart|graph|sequencediagram|c4\w*)",
            combined,
        )
    )
    infrastructure_markers = [marker for marker in DEPLOYMENT_MARKERS if (root / marker).exists()]
    infrastructure_markers.extend(
        marker
        for marker in ("infrastructure", "deployment", "network", "terraform", "kubernetes")
        if marker in combined
    )
    return {
        "applicable": bool(diagram_files or inline_count or infrastructure_markers),
        "diagram_count": len(diagram_files) + inline_count,
        "diagram_files": diagram_files,
        "linked_count": len(linked_paths),
        "linked_paths": linked_paths,
        "inline_count": inline_count,
        "infrastructure_markers": sorted(set(infrastructure_markers))[:16],
    }


def collect_self_documentation(root: Path) -> dict[str, Any]:
    declarations = 0
    documented = 0
    files_scanned: list[str] = []
    undocumented_examples: list[dict[str, Any]] = []
    for path in iter_repository_files(root):
        if path.suffix.lower() not in _SOURCE_SUFFIXES or is_test_path(root, path):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(content.encode("utf-8", errors="replace")) > MAX_DOCUMENT_BYTES:
            continue
        relative = relative_path(root, path)
        files_scanned.append(relative)
        lines = content.splitlines()
        for index, line in enumerate(lines):
            name = public_declaration(path.suffix.lower(), line)
            if name is None:
                continue
            declarations += 1
            if has_documentation_marker(lines, index):
                documented += 1
            elif len(undocumented_examples) < 24:
                undocumented_examples.append({"path": relative, "line": index + 1, "name": name})
    ratio = documented / declarations if declarations else 0.0
    return {
        "files_scanned": sorted(files_scanned)[:160],
        "file_count": len(files_scanned),
        "declaration_count": declarations,
        "documented_count": documented,
        "documented_ratio": round(ratio, 3),
        "undocumented_examples": undocumented_examples,
    }


def public_declaration(suffix: str, line: str) -> str | None:
    patterns = {
        ".py": r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".js": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z][A-Za-z0-9_]*)|^\s*export\s+(?:const|let)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".jsx": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z][A-Za-z0-9_]*)|^\s*export\s+(?:const|let)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".mjs": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z][A-Za-z0-9_]*)|^\s*export\s+(?:const|let)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".ts": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|interface|type)\s+([A-Za-z][A-Za-z0-9_]*)|^\s*export\s+(?:const|let)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".tsx": r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|interface|type)\s+([A-Za-z][A-Za-z0-9_]*)|^\s*export\s+(?:const|let)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".rs": r"^\s*pub\s+(?:async\s+)?(?:fn|struct|enum|trait|mod|type)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".go": r"^\s*func\s+([A-Z][A-Za-z0-9_]*)|^\s*type\s+([A-Z][A-Za-z0-9_]*)\s+(?:struct|interface)",
        ".java": r"^\s*public\s+(?:static\s+)?(?:class|interface|enum|record)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".swift": r"^\s*public\s+(?:func|class|struct|enum|protocol|typealias)\s+([A-Za-z][A-Za-z0-9_]*)",
        ".c": r"^\s*[A-Za-z_][\w\s\*]+\s+([a-zA-Z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{",
        ".cc": r"^\s*[A-Za-z_][\w\s:*<>]+\s+([a-zA-Z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{",
        ".cpp": r"^\s*[A-Za-z_][\w\s:*<>]+\s+([a-zA-Z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{",
        ".rb": r"^\s*def\s+([A-Za-z][A-Za-z0-9_!?=]*)",
    }
    match = re.search(patterns.get(suffix, r"$^"), line)
    if not match:
        return None
    name = next((group for group in match.groups() if group), None)
    if name is None or name.startswith("_"):
        return None
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs"} and not line.lstrip().startswith("export"):
        return None
    return name


def has_documentation_marker(lines: list[str], index: int) -> bool:
    for following in range(index + 1, min(len(lines), index + 4)):
        value = lines[following].strip()
        if not value:
            continue
        if value.startswith(('"""', "'''")):
            return True
        break
    for previous in range(max(0, index - 4), index):
        value = lines[previous].strip()
        if not value:
            continue
        if value.startswith(("#", "//", "/*", "*", "///", "//!", '"""', "'''")):
            return True
        if value.startswith(("@", "#[", "derive(")):
            continue
        break
    return False


def is_test_path(root: Path, path: Path) -> bool:
    relative = relative_path(root, path)
    return bool(
        re.search(
            r"(?:^|/)(?:tests?|specs?|__tests__)(?:/|$)|(?:^|/)(?:test_|.*[._](?:test|spec)\.)",
            relative,
        )
    )


def iter_repository_files(root: Path) -> list[Path]:
    files: list[Path] = []
    try:
        candidates = root.rglob("*")
    except OSError:
        return files
    for path in candidates:
        if len(files) >= 5000:
            break
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in _SKIP_DIRECTORIES for part in relative_parts):
            continue
        files.append(path)
    return sorted(files)


def is_source_file(path: str) -> bool:
    return Path(path).suffix.lower() in _SOURCE_SUFFIXES


def lane(
    identifier: str,
    label: str,
    applicable: bool,
    score: int | None,
    status: str,
    evidence: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "applicable": applicable,
        "score": score,
        "status": status,
        "evidence": evidence[:12],
    }


def unique_evidence(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for item in items:
        key = (str(item.get("path", "")), str(item.get("detail", "")))
        if key in seen:
            continue
        seen.add(key)
        unique.append({"path": key[0], "detail": key[1]})
    return unique
