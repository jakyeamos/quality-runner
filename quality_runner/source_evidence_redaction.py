from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from quality_runner.evidence_redaction_contract import (
    REDACTED_LITERAL,
    SECRET_ASSIGNMENT_PATTERN,
    SECRET_FALLBACK_PATTERN,
    SECRET_LOG_PATTERN,
)
from quality_runner.source_evidence_contexts import (
    has_interpolated_template,
    has_unsafe_literal_tokens,
    has_unterminated_regex,
    is_docker_env_key,
    is_yaml_mapping_key,
    log_redaction_targets,
    tokenless_value_requires_redaction,
)
from quality_runner.source_evidence_lexer import (
    LexedSource,
    ambiguous_literal_targets,
    ambiguous_literal_token_targets,
    dictionary_key_start,
    has_ambiguous_literal,
    lex_source,
    line_number,
    matching_bracket,
    next_significant,
    overlapping_tokens,
    previous_significant,
)
from quality_runner.source_evidence_names import (
    decode_escaped_name,
    is_sensitive_name,
    source_secret_name_matches,
)
from quality_runner.source_evidence_rendering import RedactionTargets, render_redactions

_LEGACY_EVIDENCE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (SECRET_ASSIGNMENT_PATTERN, SECRET_FALLBACK_PATTERN, SECRET_LOG_PATTERN)
)
_VALUE_TOKEN_KINDS = frozenset({"string", "comment", "regex"})
_CONTINUATION_END = frozenset("=+-*/%?&|,.:([{\\")
_CONTINUATION_START = frozenset("+-*/%?&|,.:([{")


@dataclass(frozen=True)
class SecretAssignmentSpan:
    start_line: int
    end_line: int


@dataclass(frozen=True)
class SecretSourceAnalysis:
    lines: list[str]
    assignment_spans: list[SecretAssignmentSpan]
    fallback_spans: list[SecretAssignmentSpan]


@dataclass(frozen=True)
class _SourceSpan:
    kind: str
    start: int
    value_start: int
    end: int
    start_line: int
    end_line: int
    candidate: bool


def redact_source_literals(value: str, *, force: bool = False) -> str:
    if not force and not any(pattern.search(value) for pattern in _LEGACY_EVIDENCE_PATTERNS):
        return value
    if has_ambiguous_literal(value):
        return "\n".join(f'"{REDACTED_LITERAL}"' for _ in range(value.count("\n") + 1))
    lexed = lex_source(value)
    targets: RedactionTargets = {
        (token.start, token.end): token.kind
        for token in lexed.tokens
        if token.kind == "string"
        or (
            token.kind in {"comment", "regex"}
            and any(quote in lexed.source[token.start : token.end] for quote in ('"', "'", "`"))
        )
    }
    return render_redactions(lexed, targets, placeholder=REDACTED_LITERAL)


def analyze_secret_like_source_lines(lines: Sequence[str]) -> SecretSourceAnalysis:
    if not lines:
        return SecretSourceAnalysis(lines=[], assignment_spans=[], fallback_spans=[])
    source = "\n".join(lines)
    lexed = lex_source(source)
    assignment_spans = _assignment_spans(lexed)
    fallback_spans = _fallback_spans(lexed)
    source_spans = [*assignment_spans, *fallback_spans]
    targets: RedactionTargets = {
        target: "opaque"
        for target in ambiguous_literal_targets(source)
        if "${" in source[target[0] : target[1]]
        and any(target[0] < span.end and target[1] > span.value_start for span in source_spans)
    }
    targets.update(_span_targets(lexed, source_spans))
    targets.update(_quoted_secret_assignment_targets(lexed))
    targets.update(log_redaction_targets(lexed))
    _add_legacy_line_targets(lexed, assignment_spans, targets)
    redacted = render_redactions(lexed, targets, placeholder=REDACTED_LITERAL)
    return SecretSourceAnalysis(
        lines=_restore_input_shape(redacted, lines),
        assignment_spans=_candidate_spans(assignment_spans),
        fallback_spans=_candidate_spans(fallback_spans),
    )


def _assignment_spans(lexed: LexedSource) -> list[_SourceSpan]:
    spans: list[_SourceSpan] = []
    for start, end in source_secret_name_matches(lexed.code):
        operator = _assignment_operator_after_name(lexed, start, end)
        if operator is not None:
            spans.append(_span_for_value(lexed, "assignment", start, operator + 1, 8))
    spans.extend(_key_assignment_spans(lexed))
    return _dedupe_spans(spans)


def _fallback_spans(lexed: LexedSource) -> list[_SourceSpan]:
    spans: list[_SourceSpan] = []
    index = 0
    while index < len(lexed.code) - 1:
        if lexed.code.startswith(("??", "||"), index):
            spans.append(_span_for_value(lexed, "fallback", index, index + 2, 12))
            index += 2
        else:
            index += 1
    return _dedupe_spans(spans)


def _assignment_operator_after_name(lexed: LexedSource, name_start: int, start: int) -> int | None:
    following = next_significant(lexed, start)
    if is_docker_env_key(lexed, name_start) and (
        following is None or lexed.code[following] not in "=:"
    ):
        return start
    colon: int | None = None
    index = start
    while index < len(lexed.code):
        token_end = lexed.token_ends.get(index)
        if token_end is not None:
            index = token_end
            continue
        character = lexed.code[index]
        if character == ";" or character in ")]},({":
            return None
        if character == "=" and _is_assignment_equals(lexed.code, index):
            return index
        if character == ":":
            if is_yaml_mapping_key(lexed, name_start):
                return index
            colon = index
            index += 1
            continue
        if character == "\n":
            following = next_significant(lexed, index + 1)
            if following is None:
                return colon
            if lexed.code[following] in "=:":
                index = following
                continue
            if colon is None:
                return None
        elif not character.isspace():
            if colon is None:
                return None
            if not (character.isalnum() or character in "._?[]<>|&,"):
                return None
        index += 1
    return colon


def _key_assignment_spans(lexed: LexedSource) -> list[_SourceSpan]:
    spans: list[_SourceSpan] = []
    for index, character in enumerate(lexed.code):
        if character == "[":
            key_start = next_significant(lexed, index + 1)
            if key_start is None or lexed.source[key_start] not in "'\"`\\(fFrR":
                continue
            closing = matching_bracket(lexed, index)
            if closing is None or not _key_expression_is_sensitive(lexed, index + 1, closing):
                continue
            assignment = next_significant(lexed, closing + 1)
            if assignment is not None and _is_assignment_equals(lexed.code, assignment):
                spans.append(_span_for_value(lexed, "assignment", index + 1, assignment + 1, 8))
        elif character == ":":
            key_end = previous_significant(lexed, index - 1)
            if key_end is None:
                continue
            if lexed.code[key_end] not in "V)":
                start = _bare_sensitive_key_start(lexed, key_end, index)
                if start is not None:
                    spans.append(_span_for_value(lexed, "assignment", start, index + 1, 8))
                continue
            if lexed.code[key_end] != ")" and (lexed.source[key_end] not in "'\"`"):
                continue
            start = dictionary_key_start(lexed, index)
            if start is not None and _key_expression_is_sensitive(lexed, start, index):
                spans.append(_span_for_value(lexed, "assignment", start, index + 1, 8))
    return spans


def _bare_sensitive_key_start(lexed: LexedSource, end: int, colon: int) -> int | None:
    if not (lexed.code[end].isalnum() or lexed.code[end] in "_$"):
        return None
    start = end
    while start > 0 and (lexed.code[start - 1].isalnum() or lexed.code[start - 1] in "_$"):
        start -= 1
    key = lexed.source[start : end + 1]
    dictionary_start = dictionary_key_start(lexed, colon)
    if (
        is_sensitive_name(key)
        and dictionary_start is not None
        and lexed.source[dictionary_start:colon].strip() == key
    ):
        return start
    return None


def _key_expression_is_sensitive(lexed: LexedSource, start: int, end: int) -> bool:
    pieces = [
        _key_token_text(lexed.source[token.start : token.end])
        for token in overlapping_tokens(lexed, start, end)
        if token.kind == "string"
    ]
    if pieces:
        return is_sensitive_name("".join(pieces))
    key = lexed.source[start:end].strip()
    return "\\" in key and is_sensitive_name(decode_escaped_name(key))


def _key_token_text(value: str) -> str:
    if len(value) < 2 or value[0] not in {'"', "'", "`"}:
        return ""
    return decode_escaped_name(re.sub(r"[\"'`${}+\s]", "", value[1:-1]))


def _span_for_value(
    lexed: LexedSource,
    kind: str,
    start: int,
    value_start: int,
    minimum_literal_length: int,
) -> _SourceSpan:
    end = _yaml_block_scalar_end(lexed, value_start) or _expression_end(lexed, value_start)
    value_tokens = [
        token
        for token in overlapping_tokens(lexed, value_start, end)
        if token.kind in _VALUE_TOKEN_KINDS
    ]
    return _SourceSpan(
        kind=kind,
        start=start,
        value_start=value_start,
        end=end,
        start_line=line_number(lexed, start),
        end_line=line_number(lexed, max(start, end - 1)),
        candidate=any(
            _literal_length(lexed.source[token.start : token.end]) >= minimum_literal_length
            for token in value_tokens
        ),
    )


def _expression_end(lexed: LexedSource, start: int) -> int:
    depth = 0
    index = start
    while index < len(lexed.code):
        token_end = lexed.token_ends.get(index)
        if token_end is not None:
            index = token_end
            continue
        character = lexed.code[index]
        if character in "([{":
            depth += 1
        elif character in ")]}":
            if depth == 0:
                return index
            depth -= 1
        elif character == ";" and depth == 0:
            return index + 1
        elif character == "\n" and depth == 0 and _line_break_terminates(lexed, start, index):
            return index
        index += 1
    return len(lexed.code)


def _yaml_block_scalar_end(lexed: LexedSource, start: int) -> int | None:
    marker = next_significant(lexed, start)
    if marker is None or lexed.code[marker] not in "|>":
        return None
    line_start = lexed.source.rfind("\n", 0, marker) + 1
    indent = len(lexed.source[line_start:marker]) - len(lexed.source[line_start:marker].lstrip())
    index = lexed.source.find("\n", marker)
    while index >= 0:
        next_start = index + 1
        end = lexed.source.find("\n", next_start)
        end = len(lexed.source) if end < 0 else end
        line = lexed.source[next_start:end]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            return next_start
        index = -1 if end == len(lexed.source) else end
    return len(lexed.source)


def _line_break_terminates(lexed: LexedSource, start: int, newline: int) -> bool:
    previous = previous_significant(lexed, newline - 1, start)
    following = next_significant(lexed, newline + 1)
    if previous is None:
        return False
    if following is None:
        return True
    if lexed.code[previous] in _CONTINUATION_END or lexed.code[following] in _CONTINUATION_START:
        return False
    return not lexed.code.startswith(("??", "||", "&&"), following)


def _quoted_secret_assignment_targets(lexed: LexedSource) -> RedactionTargets:
    targets: RedactionTargets = {}
    for token in lexed.tokens:
        if token.kind != "string":
            continue
        name, separator, value = lexed.source[token.start + 1 : token.end - 1].partition("=")
        if separator and value.strip() and is_sensitive_name(decode_escaped_name(name.strip())):
            targets[(token.start, token.end)] = token.kind
    return targets


def _span_targets(lexed: LexedSource, spans: list[_SourceSpan]) -> RedactionTargets:
    targets: RedactionTargets = {}
    for span in spans:
        tokens = [
            token
            for token in overlapping_tokens(lexed, span.value_start, span.end)
            if token.kind in _VALUE_TOKEN_KINDS
        ]
        value = lexed.source[span.value_start : span.end]
        opaque_start = _opaque_start(lexed, span)
        template_start = lexed.source.find("`${", opaque_start, _line_end(lexed, opaque_start))
        template_end = _interpolated_template_end(lexed, template_start)
        opaque_end = max(_opaque_end(lexed, span), template_end or 0)
        ambiguous_targets = ambiguous_literal_token_targets(
            lexed,
            opaque_start,
            max(span.end, _line_end(lexed, span.value_start)),
        )
        if (
            has_unsafe_literal_tokens(lexed, tokens)
            or has_unterminated_regex(value)
            or template_end is not None
            or has_interpolated_template(value)
            or "<<" in value
        ):
            targets[(opaque_start, opaque_end)] = "opaque"
        elif ambiguous_targets:
            targets.update({target: "opaque" for target in ambiguous_targets})
        elif not tokens and tokenless_value_requires_redaction(
            lexed,
            name_start=span.start,
            value_start=span.value_start,
            start=opaque_start,
            end=opaque_end,
        ):
            targets[(opaque_start, opaque_end)] = "opaque"
        else:
            targets.update({(token.start, token.end): token.kind for token in tokens})
    return targets


def _opaque_start(lexed: LexedSource, span: _SourceSpan) -> int:
    start = span.value_start
    while start < span.end and lexed.source[start].isspace():
        start += 1
    return start


def _opaque_end(lexed: LexedSource, span: _SourceSpan) -> int:
    return span.end - 1 if lexed.source[span.end - 1 : span.end] == ";" else span.end


def _line_end(lexed: LexedSource, start: int) -> int:
    line_end = lexed.source.find("\n", start)
    return len(lexed.source) if line_end < 0 else line_end


def _interpolated_template_end(lexed: LexedSource, start: int) -> int | None:
    if start < 0:
        return None
    end = lexed.source.find("`;", start + 2)
    return len(lexed.source) if end < 0 else end + 1


def _add_legacy_line_targets(
    lexed: LexedSource,
    assignment_spans: list[_SourceSpan],
    targets: RedactionTargets,
) -> None:
    assignment_lines = {
        span.start_line for span in assignment_spans if span.start_line == span.end_line
    }
    for line_number_value, start in enumerate(lexed.line_starts, start=1):
        end = lexed.source.find("\n", start)
        end = len(lexed.source) if end < 0 else end
        line = lexed.source[start:end]
        if line_number_value not in assignment_lines and not any(
            pattern.search(line) for pattern in _LEGACY_EVIDENCE_PATTERNS
        ):
            continue
        for token in overlapping_tokens(lexed, start, end):
            if token.kind == "string" or (
                token.kind in {"comment", "regex"}
                and any(quote in lexed.source[token.start : token.end] for quote in ('"', "'", "`"))
            ):
                targets.setdefault((token.start, token.end), token.kind)


def _restore_input_shape(redacted: str, lines: Sequence[str]) -> list[str]:
    physical_lines = redacted.split("\n")
    restored: list[str] = []
    index = 0
    for line in lines:
        count = line.count("\n") + 1
        restored.append("\n".join(physical_lines[index : index + count]))
        index += count
    return restored


def _candidate_spans(spans: list[_SourceSpan]) -> list[SecretAssignmentSpan]:
    return [
        SecretAssignmentSpan(start_line=span.start_line, end_line=span.end_line)
        for span in spans
        if span.candidate
    ]


def _literal_length(value: str) -> int:
    if value.startswith(('"""', "'''")) and value.endswith(value[:3]):
        return len(value[3:-3])
    if len(value) >= 2:
        return len(value[1:-1])
    return 0


def _is_assignment_equals(value: str, index: int) -> bool:
    before = value[index - 1] if index > 0 else ""
    after = value[index + 1] if index + 1 < len(value) else ""
    return (not before or before not in "=!<>") and (not after or after not in "=>")


def _dedupe_spans(spans: list[_SourceSpan]) -> list[_SourceSpan]:
    unique: dict[tuple[str, int, int], _SourceSpan] = {}
    for span in spans:
        unique[(span.kind, span.value_start, span.end)] = span
    return list(unique.values())
