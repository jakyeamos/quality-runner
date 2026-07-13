from __future__ import annotations

import bisect
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceToken:
    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class LexedSource:
    source: str
    code: str
    tokens: list[SourceToken]
    token_ends: dict[int, int]
    token_starts: list[int]
    line_starts: list[int]


_FSTRING_PREFIX = re.compile(r"(?i)(?<![A-Za-z0-9_])(?:fr|rf|f)(?=[\"'])")
_JS_DECLARATION = re.compile(r"(?<![\w$])(?:const|let|var|function|class|export|import)\b")
_LOG_CALL_START = re.compile(r"""(?ix)\b(?:
    (?:console|logger)\s*(?:\?\s*\.\s*|\.\s*)[A-Za-z_]\w*\s*\(
    | (?:console|logger)\s*(?:\?\s*\.\s*)?\[\s*V\s*\]\s*(?:\?\s*\.\s*)?\(
    | print\s*\(
    | logging\s*\.\s*[A-Za-z_]\w*\s*\(
    )""")
_SENSITIVE_COMMENT = re.compile(r"(?i)//\s*(?:api.?key|secret|password|token|private.?key)\s*[=:]")


def lex_source(source: str) -> LexedSource:
    code = list(source)
    tokens: list[SourceToken] = []
    token_ends: dict[int, int] = {}
    index = 0
    line_start = True
    line_has_js_declaration = False
    pending_js_class = False
    class_body_depths: list[int] = []
    brace_depth = 0

    while index < len(source):
        character = source[index]
        if character == "\n":
            line_start = True
            line_has_js_declaration = False
            index += 1
            continue
        if source.startswith("//", index) and _starts_line_comment(
            source, code, index, line_start, line_has_js_declaration
        ):
            end = source.find("\n", index)
            if end < 0:
                end = len(source)
            _add_token(code, source, tokens, token_ends, "comment", index, end)
            index = end
            continue
        if source.startswith("/*", index):
            closing = source.find("*/", index + 2)
            end = len(source) if closing < 0 else closing + 2
            _add_token(code, source, tokens, token_ends, "comment", index, end)
            line_start = source.rfind("\n", index, end) >= 0
            index = end
            continue
        if character == "#" and not _is_js_private_name(source, index, class_body_depths):
            end = source.find("\n", index)
            if end < 0:
                end = len(source)
            _add_token(code, source, tokens, token_ends, "comment", index, end)
            index = end
            continue
        if source.startswith(('"""', "'''"), index):
            delimiter = source[index : index + 3]
            end = _scan_quoted_token(source, index, delimiter)
            _add_token(code, source, tokens, token_ends, "string", index, end)
            line_start = source.rfind("\n", index, end) >= 0
            index = end
            continue
        if character in {'"', "'", "`"}:
            end = _scan_quoted_token(source, index, character)
            _add_token(code, source, tokens, token_ends, "string", index, end)
            line_start = source.rfind("\n", index, end) >= 0
            index = end
            continue
        if character == "/" and _looks_like_regex_start(code, index):
            end = _scan_regex_token(source, index)
            if end is not None:
                _add_token(code, source, tokens, token_ends, "regex", index, end)
                line_start = source.rfind("\n", index, end) >= 0
                index = end
                continue
        if _JS_DECLARATION.match(source, index):
            line_has_js_declaration = True
            pending_js_class = pending_js_class or source.startswith("class", index)
        if character == "{":
            brace_depth += 1
            if pending_js_class:
                class_body_depths.append(brace_depth)
                pending_js_class = False
        elif character == "}":
            if class_body_depths and class_body_depths[-1] == brace_depth:
                class_body_depths.pop()
            brace_depth = max(0, brace_depth - 1)
        if not character.isspace():
            line_start = False
        index += 1

    line_starts = [0]
    line_starts.extend(index + 1 for index, character in enumerate(source) if character == "\n")
    return LexedSource(
        source=source,
        code="".join(code),
        tokens=tokens,
        token_ends=token_ends,
        token_starts=[token.start for token in tokens],
        line_starts=line_starts,
    )


def overlapping_tokens(lexed: LexedSource, start: int, end: int) -> list[SourceToken]:
    index = bisect.bisect_left(lexed.token_starts, start)
    if index > 0 and lexed.tokens[index - 1].end > start:
        index -= 1
    tokens: list[SourceToken] = []
    while index < len(lexed.tokens):
        token = lexed.tokens[index]
        if token.start >= end:
            break
        if token.end > start:
            tokens.append(token)
        index += 1
    return tokens


def previous_significant(lexed: LexedSource, index: int, minimum: int = 0) -> int | None:
    while index >= minimum:
        if not lexed.code[index].isspace():
            return index
        index -= 1
    return None


def next_significant(lexed: LexedSource, index: int) -> int | None:
    while index < len(lexed.code):
        token_end = lexed.token_ends.get(index)
        if token_end is not None and lexed.code[index].isspace():
            index = token_end
            continue
        if not lexed.code[index].isspace():
            return index
        index += 1
    return None


def matching_bracket(lexed: LexedSource, start: int) -> int | None:
    depth = 1
    index = start + 1
    while index < len(lexed.code):
        token_end = lexed.token_ends.get(index)
        if token_end is not None:
            index = token_end
            continue
        if lexed.code[index] == "[":
            depth += 1
        elif lexed.code[index] == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def dictionary_key_start(lexed: LexedSource, colon: int) -> int | None:
    depth = 0
    index = colon - 1
    while index >= 0:
        character = lexed.code[index]
        if character in ")]}":
            depth += 1
        elif character in "([{":
            if character == "{" and depth == 0:
                return index + 1
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            return index + 1
        elif character in ";=" and depth == 0:
            return None
        index -= 1
    return None


def line_number(lexed: LexedSource, index: int) -> int:
    return bisect.bisect_right(lexed.line_starts, index)


def log_call_ranges(lexed: LexedSource) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    scanned_until = 0
    for match in _LOG_CALL_START.finditer(lexed.code):
        if match.start() < scanned_until:
            continue
        header = lexed.source[match.start() : match.end()]
        if (
            header.startswith("console")
            and "[" in lexed.code[match.start() : match.end()]
            and not re.search(r"(?i)[\"']log[\"']", header)
        ):
            continue
        depth = 1
        index = match.end()
        while index < len(lexed.code):
            token_end = lexed.token_ends.get(index)
            if token_end is not None:
                index = token_end
                continue
            character = lexed.code[index]
            if character in "([{":
                depth += 1
            elif character in ")]}":
                depth -= 1
                index += 1
                if depth == 0:
                    break
                continue
            index += 1
        ranges.append((match.start(), index))
        scanned_until = index
    return ranges


def template_literal_end(source: str, start: int, limit: int) -> int | None:
    if start >= limit or source[start] != "`":
        return None
    index = start + 1
    while index < limit:
        character = source[index]
        if character == "\\":
            index += 2
        elif character == "`":
            return index + 1
        elif source.startswith("${", index):
            index = _template_expression_end(source, index + 2, limit)
        else:
            index += 1
    return None


def fstring_literal_end(source: str, start: int, limit: int) -> int | None:
    index = start
    while index < limit and source[index] in "fFrR":
        index += 1
    if index >= limit or source[index] not in {'"', "'"}:
        return None
    delimiter = source[index] * (3 if source.startswith(source[index] * 3, index) else 1)
    index += len(delimiter)
    while index < limit:
        if source[index] == "\\":
            index += 2
        elif source.startswith(delimiter, index):
            return index + len(delimiter)
        elif source[index] == "{":
            index = _template_expression_end(source, index + 1, limit)
        else:
            index += 1
    return None


def ambiguous_literal_range(source: str, start: int, limit: int) -> tuple[int, int] | None:
    if start >= limit:
        return None
    if source[start] == "`":
        end = template_literal_end(source, start, limit)
        if end is None:
            return start, limit
        return (start, end) if "${" in source[start:end] else None
    prefix = _FSTRING_PREFIX.match(source, start)
    if prefix is None:
        return None
    end = fstring_literal_end(source, start, limit)
    if end is None:
        return prefix.end(), limit
    return (prefix.end(), end) if "{" in source[start:end] else None


def ambiguous_literal_targets(source: str) -> set[tuple[int, int]]:
    targets: set[tuple[int, int]] = set()
    index = 0
    while index < len(source):
        target = ambiguous_literal_range(source, index, len(source))
        if target is None:
            index += 1
            continue
        targets.add(target)
        index = max(index + 1, target[1])
    return targets


def ambiguous_literal_token_targets(
    lexed: LexedSource,
    start: int,
    end: int,
) -> set[tuple[int, int]]:
    targets: set[tuple[int, int]] = set()
    for token in overlapping_tokens(lexed, start, end):
        if token.kind != "string":
            continue
        starts = [token.start]
        starts.extend(index for index in (token.start - 1, token.start - 2) if index >= start)
        for literal_start in starts:
            target = ambiguous_literal_range(lexed.source, literal_start, len(lexed.source))
            if target is not None:
                targets.add(target)
    return targets


def has_ambiguous_literal(value: str) -> bool:
    return bool(ambiguous_literal_targets(value))


def _add_token(
    code: list[str],
    source: str,
    tokens: list[SourceToken],
    token_ends: dict[int, int],
    kind: str,
    start: int,
    end: int,
) -> None:
    for index in range(start, end):
        if source[index] != "\n":
            code[index] = " "
    if kind in {"string", "regex"}:
        code[start] = "V"
    tokens.append(SourceToken(kind, start, end))
    token_ends[start] = end


def _scan_quoted_token(source: str, start: int, delimiter: str) -> int:
    index = start + len(delimiter)
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source.startswith(delimiter, index):
            return index + len(delimiter)
        else:
            index += 1
    return len(source)


def _looks_like_regex_start(code: list[str], index: int) -> bool:
    previous = index - 1
    while previous >= 0 and code[previous].isspace():
        previous -= 1
    if previous < 0:
        return True
    if code[previous] in "=(:,[!&|?;{+-*%~<>":
        return True
    word_end = previous + 1
    while previous >= 0 and (code[previous].isalnum() or code[previous] in "_$"):
        previous -= 1
    return "".join(code[previous + 1 : word_end]) in {
        "await",
        "case",
        "delete",
        "do",
        "else",
        "in",
        "instanceof",
        "new",
        "of",
        "return",
        "throw",
        "typeof",
        "void",
        "yield",
    }


def _starts_line_comment(
    source: str,
    code: list[str],
    index: int,
    line_start: bool,
    line_has_js_declaration: bool,
) -> bool:
    if line_start or line_has_js_declaration or _SENSITIVE_COMMENT.match(source, index):
        return True
    previous = index - 1
    while previous >= 0 and code[previous].isspace():
        previous -= 1
    return previous >= 0 and code[previous] in ";{}])"


def _is_js_private_name(source: str, index: int, class_body_depths: list[int]) -> bool:
    return (
        bool(class_body_depths)
        and index + 1 < len(source)
        and (source[index + 1].isalpha() or source[index + 1] in "_$")
    )


def _scan_regex_token(source: str, start: int) -> int | None:
    in_character_class = False
    index = start + 1
    while index < len(source):
        character = source[index]
        if character == "\\":
            index += 2
        elif character == "\n":
            return None
        elif character == "[":
            in_character_class = True
            index += 1
        elif character == "]":
            in_character_class = False
            index += 1
        elif character == "/" and not in_character_class:
            index += 1
            while index < len(source) and source[index].isalpha():
                index += 1
            return index
        else:
            index += 1
    return None


def _template_expression_end(source: str, start: int, limit: int) -> int:
    depth = 1
    index = start
    while index < limit and depth:
        character = source[index]
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = limit if newline < 0 else newline + 1
        elif source.startswith("/*", index):
            closing = source.find("*/", index + 2)
            index = limit if closing < 0 else closing + 2
        elif character in {'"', "'"}:
            index = _skip_quoted_source(source, index, character, limit)
        elif character == "`":
            nested_end = template_literal_end(source, index, limit)
            index = nested_end if nested_end is not None else limit
        elif character == "/":
            regex_end = _scan_regex_token(source, index)
            index = regex_end if regex_end is not None else index + 1
        elif character == "{":
            depth += 1
            index += 1
        elif character == "}":
            depth -= 1
            index += 1
        else:
            index += 1
    return index


def _skip_quoted_source(source: str, start: int, quote: str, limit: int) -> int:
    delimiter = quote * (3 if source.startswith(quote * 3, start) else 1)
    index = start + len(delimiter)
    while index < limit:
        if source[index] == "\\":
            index += 2
        elif source.startswith(delimiter, index):
            return index + len(delimiter)
        else:
            index += 1
    return limit
