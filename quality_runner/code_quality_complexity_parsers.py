from __future__ import annotations

import ast
import re
from collections import Counter
from typing import Any


def python_complexity_metrics(text: str) -> list[tuple[int, str, int, Counter[str]]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    contexts = _python_function_contexts(tree)
    result: list[tuple[int, str, int, Counter[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        visitor = _PythonComplexityVisitor()
        for statement in node.body:
            visitor.visit(statement)
        context = contexts.get(node, ())
        symbol = ".".join((*context, node.name))
        result.append((node.lineno, symbol, 1 + sum(visitor.decisions.values()), visitor.decisions))
    return result


def _python_function_contexts(tree: ast.AST) -> dict[ast.AST, tuple[str, ...]]:
    contexts: dict[ast.AST, tuple[str, ...]] = {}

    def visit(parent: ast.AST, prefix: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(parent):
            child_prefix = prefix
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                contexts[child] = prefix
                child_prefix = (*prefix, child.name)
            visit(child, child_prefix)

    visit(tree, ())
    return contexts


class _PythonComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.decisions: Counter[str] = Counter()

    def visit_If(self, node: ast.If) -> None:
        self.decisions["if"] += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.decisions["conditional-expression"] += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.decisions["for"] += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.decisions["for"] += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.decisions["while"] += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.decisions["except"] += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.decisions["boolean"] += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.decisions["comprehension"] += 1 + len(node.ifs)
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.decisions["match-case"] += max(0, len(node.cases) - 1)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def javascript_complexity_metrics(text: str) -> list[tuple[int, str, int, Counter[str]]]:
    masked = _mask_javascript(text)
    regions = _javascript_function_regions(masked)
    result: list[tuple[int, str, int, Counter[str]]] = []
    for region in regions:
        body = _without_nested_functions(masked, region, regions)
        decisions = _javascript_decisions(body)
        result.append(
            (
                region["line"],
                region["name"],
                1 + sum(decisions.values()),
                decisions,
            )
        )
    return result


_JS_FUNCTION_RE = re.compile(
    r"\b(?:async\s+)?function(?:\s*\*)?\s*"
    r"(?P<name>[A-Za-z_$][\w$]*)?(?:\s*<[^>{}()]*>)?\s*\([^)]*\)\s*\{",
    re.DOTALL,
)
_JS_ARROW_RE = re.compile(
    r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{",
    re.DOTALL,
)
_JS_METHOD_RE = re.compile(
    r"(?:^|[{};\n])\s*"
    r"(?:(?:public|private|protected|static|async|get|set|override|abstract)\s+)*"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",
    re.DOTALL,
)
_JS_CONTROL_NAMES = {"if", "for", "while", "switch", "catch", "with"}


def _javascript_function_regions(masked: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for pattern in (_JS_FUNCTION_RE, _JS_ARROW_RE, _JS_METHOD_RE):
        for match in pattern.finditer(masked):
            opening = match.end() - 1
            closing = _matching_brace(masked, opening)
            if closing is None:
                continue
            name = match.groupdict().get("name")
            if pattern is _JS_METHOD_RE and name in _JS_CONTROL_NAMES:
                continue
            if not name and pattern is _JS_FUNCTION_RE:
                name = _assigned_function_name(masked, match.start())
            line = masked.count("\n", 0, match.start()) + 1
            candidates.append(
                {"start": match.start(), "end": closing, "line": line, "name": name or "anonymous"}
            )
    unique: dict[tuple[int, int], dict[str, Any]] = {}
    for candidate in candidates:
        unique[(int(candidate["start"]), int(candidate["end"]))] = candidate
    return sorted(unique.values(), key=lambda item: (int(item["start"]), int(item["end"])))


def _assigned_function_name(masked: str, start: int) -> str | None:
    prefix = masked[max(0, start - 120) : start]
    match = re.search(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*$", prefix)
    return match.group(1) if match else None


def _matching_brace(text: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _without_nested_functions(
    masked: str, region: dict[str, Any], regions: list[dict[str, Any]]
) -> str:
    start = int(region["start"])
    end = int(region["end"])
    body = list(masked[start:end])
    for child in regions:
        child_start = int(child["start"])
        child_end = int(child["end"])
        if child_start <= start or child_end >= end:
            continue
        for index in range(child_start - start, child_end - start + 1):
            if 0 <= index < len(body) and body[index] != "\n":
                body[index] = " "
    return "".join(body)


def _javascript_decisions(body: str) -> Counter[str]:
    decisions: Counter[str] = Counter()
    decisions["if"] = len(re.findall(r"\bif\s*\(", body))
    decisions["for"] = len(re.findall(r"\bfor\s*\(", body))
    decisions["while"] = len(re.findall(r"\bwhile\s*\(", body))
    decisions["catch"] = len(re.findall(r"\bcatch\s*\(", body))
    decisions["case"] = len(re.findall(r"\bcase\b", body))
    decisions["ternary"] = len(re.findall(r"(?<![?.])\?(?![.?])", body))
    decisions["boolean"] = len(re.findall(r"&&|\|\|", body))
    return Counter({key: value for key, value in decisions.items() if value})


def _mask_javascript(text: str) -> str:
    chars = list(text)
    index = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    while index < len(chars):
        char = chars[index]
        following = chars[index + 1] if index + 1 < len(chars) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            else:
                chars[index] = " "
            index += 1
            continue
        if block_comment:
            if char == "*" and following == "/":
                chars[index] = " "
                chars[index + 1] = " "
                block_comment = False
                index += 2
                continue
            if char != "\n":
                chars[index] = " "
            index += 1
            continue
        if quote is not None:
            if char == "\n" and quote != "`":
                quote = None
                index += 1
                continue
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            if char != "\n":
                chars[index] = " "
            index += 1
            continue
        if char == "/" and following == "/":
            chars[index] = " "
            chars[index + 1] = " "
            line_comment = True
            index += 2
            continue
        if char == "/" and following == "*":
            chars[index] = " "
            chars[index + 1] = " "
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
            chars[index] = " "
            index += 1
            continue
        if char == "/" and _looks_like_regex_start("".join(chars), index):
            index = _mask_regex(chars, index)
            continue
        index += 1
    return "".join(chars)


def _looks_like_regex_start(text: str, index: int) -> bool:
    previous = ""
    for candidate in reversed(text[:index]):
        if not candidate.isspace():
            previous = candidate
            break
    return not previous or previous in "=([{,:;!?&|+-*%~<>"


def _mask_regex(chars: list[str], start: int) -> int:
    index = start + 1
    escaped = False
    in_class = False
    while index < len(chars):
        char = chars[index]
        if char == "\n":
            return index
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            index += 1
            while index < len(chars) and chars[index].isalpha():
                index += 1
            for position in range(start, index):
                if chars[position] != "\n":
                    chars[position] = " "
            return index
        index += 1
    return index
