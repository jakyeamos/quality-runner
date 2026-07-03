from __future__ import annotations

import re
from pathlib import Path

CODE_EXTENSIONS = {".cjs", ".css", ".html", ".js", ".jsx", ".mjs", ".py", ".sh", ".ts", ".tsx"}
TEXT_EXTENSIONS = {*CODE_EXTENSIONS, ".json", ".md", ".toml", ".yaml", ".yml"}
IGNORED_DIRS = {
    ".aider",
    ".cache",
    ".continue",
    ".cursor",
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
    "public",
    "target",
    "test-results",
    "vendor",
}
IGNORED_DIR_PREFIXES = (".next",)
IGNORED_PATH_PREFIXES = (
    ".claude/worktrees",
    ".codex/worktrees",
    ".aios/shadow-worktrees",
    ".worktrees",
    ".tmp",
)
IGNORED_PATH_PARTS = {
    "site-packages",
}
IGNORED_TOP_LEVEL_DIRS = {
    ".pnpm-store",
    "data",
    "logs",
    "staging",
}
IGNORED_TOP_LEVEL_SUFFIXES = ("-benchmark",)


def _ignored_directory_reason(
    relative_path: str,
    *,
    include_ignored_paths: set[str],
) -> str | None:
    normalized = relative_path.strip("/")
    if not normalized or _is_included_or_included_parent(normalized, include_ignored_paths):
        return None

    name = Path(normalized).name
    parts = set(Path(normalized).parts)
    top_level = "/" not in normalized
    if top_level and (
        name in IGNORED_TOP_LEVEL_DIRS
        or any(name.endswith(suffix) for suffix in IGNORED_TOP_LEVEL_SUFFIXES)
    ):
        return "ignored directory"
    if name in IGNORED_DIRS:
        return "ignored directory"
    if any(name.startswith(prefix) for prefix in IGNORED_DIR_PREFIXES):
        return "ignored directory"
    if any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in IGNORED_PATH_PREFIXES
    ):
        return "ignored directory"
    if parts & IGNORED_PATH_PARTS:
        return "ignored directory"
    return None


def _is_included_or_included_parent(relative_path: str, include_ignored_paths: set[str]) -> bool:
    normalized = relative_path.strip("/")
    return any(
        normalized == included
        or normalized.startswith(f"{included}/")
        or included.startswith(f"{normalized}/")
        for included in include_ignored_paths
    )


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
    if Path(relative_path).suffix in {
        ".cjs",
        ".css",
        ".html",
        ".js",
        ".jsx",
        ".mjs",
        ".ts",
        ".tsx",
    }:
        return (
            "Run the relevant JavaScript formatter, typecheck, and tests for the touched package."
        )
    return "Run the relevant formatter, typecheck, and tests for the touched package."


def _is_deep_nesting(stripped: str, block_depth: int) -> bool:
    return block_depth >= 3 and stripped.startswith(
        ("if ", "if(", "for ", "for(", "while ", "while(", "switch", "try", "catch")
    )


def _nested_ternary(line: str) -> bool:
    return _ternary_question_count(line) >= 2 and ":" in line


def _ternary_question_count(line: str) -> int:
    line = _mask_regex_literals(line)
    count = 0
    for index, char in enumerate(line):
        if char != "?":
            continue
        previous_char = line[index - 1] if index > 0 else ""
        next_char = line[index + 1] if index + 1 < len(line) else ""
        if previous_char == "?" or next_char in {"?", ".", ":"}:
            continue
        count += 1
    return count


def _mask_regex_literals(line: str) -> str:
    masked: list[str] = []
    index = 0
    previous_significant = ""
    while index < len(line):
        char = line[index]
        next_char = line[index + 1] if index + 1 < len(line) else ""
        if char == "/" and next_char not in {"/", "*"} and previous_significant in {
            "",
            "(",
            "=",
            ":",
            ",",
            "[",
            "{",
            "!",
            "&",
            "|",
            "?",
            "return",
        }:
            end = _regex_literal_end(line, index + 1)
            if end is not None:
                masked.append("/" + ("x" * (end - index - 1)))
                index = end + 1
                previous_significant = "/"
                continue
        masked.append(char)
        if not char.isspace():
            previous_significant = _previous_token(previous_significant, char)
        index += 1
    return "".join(masked)


def _regex_literal_end(line: str, start: int) -> int | None:
    escaped = False
    in_class = False
    for index in range(start, len(line)):
        char = line[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "[":
            in_class = True
            continue
        if char == "]":
            in_class = False
            continue
        if char == "/" and not in_class:
            return index
    return None


def _previous_token(previous: str, char: str) -> str:
    if char.isalnum() or char == "_":
        return f"{previous}{char}"[-6:]
    return char


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
