from __future__ import annotations

import re
from pathlib import Path

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
