from __future__ import annotations

import re

from quality_runner.source_evidence_lexer import (
    LexedSource,
    SourceToken,
    log_call_ranges,
    overlapping_tokens,
)
from quality_runner.source_evidence_rendering import RedactionTargets

_SENSITIVE_LOG_VALUE = re.compile(r"(?i)password|secret|token|api[_-]?key|private[_-]?key")
_TOKENLESS_LITERAL = re.compile(r"[A-Za-z0-9_-]{8,}")
_UNTERMINATED_REGEX = re.compile(r"(?<![/\w$)\]}])/[A-Za-z0-9_$][^/\n;)]*(?:[;)]|$)")


def has_interpolated_template(value: str) -> bool:
    return "`" in value and "${" in value


def has_unterminated_regex(value: str) -> bool:
    return _UNTERMINATED_REGEX.search(value) is not None


def is_yaml_mapping_key(lexed: LexedSource, name_start: int) -> bool:
    line_start = lexed.source.rfind("\n", 0, name_start) + 1
    return lexed.source[line_start:name_start].strip() in {"", "-"}


def is_docker_env_key(lexed: LexedSource, name_start: int) -> bool:
    line_start = lexed.source.rfind("\n", 0, name_start) + 1
    return lexed.source[line_start:name_start].strip().upper() == "ENV"


def tokenless_value_requires_redaction(
    lexed: LexedSource,
    *,
    name_start: int,
    value_start: int,
    start: int,
    end: int,
) -> bool:
    line_start = lexed.source.rfind("\n", 0, name_start) + 1
    prefix = lexed.source[line_start:name_start].strip().lower()
    return (
        lexed.source[value_start - 1 : value_start] == ":"
        and is_yaml_mapping_key(lexed, name_start)
        or prefix.startswith("export ")
        or is_docker_env_key(lexed, name_start)
        or _TOKENLESS_LITERAL.fullmatch(lexed.source[start:end].strip()) is not None
    )


def has_unsafe_literal_tokens(
    lexed: LexedSource,
    tokens: list[SourceToken],
    *,
    allow_short_regex: bool = False,
) -> bool:
    for token in tokens:
        value = lexed.source[token.start : token.end]
        if token.kind == "comment" or (
            token.kind == "regex"
            and not _safe_quoted_regex(value)
            and (not allow_short_regex or _regex_body_length(value) >= 8)
        ):
            return True
    return False


def log_redaction_targets(lexed: LexedSource) -> RedactionTargets:
    targets: RedactionTargets = {}
    for start, end in log_call_ranges(lexed):
        value = lexed.source[start:end]
        if not _SENSITIVE_LOG_VALUE.search(value):
            continue
        call_start = lexed.code.find("(", start, end)
        if any(token.kind == "comment" for token in overlapping_tokens(lexed, start, call_start)):
            targets[(start, end)] = "opaque"
            continue
        tokens = [
            token for token in overlapping_tokens(lexed, start, end) if token.start >= call_start
        ]
        if (
            has_interpolated_template(value)
            or has_unterminated_regex(lexed.source[call_start:end])
            or has_unsafe_literal_tokens(lexed, tokens, allow_short_regex=True)
        ):
            targets[(start, end)] = "opaque"
            continue
        for token in tokens:
            token_value = lexed.source[token.start : token.end]
            if token.kind == "string" or (
                token.kind == "regex" and _safe_quoted_regex(token_value)
            ):
                targets[(token.start, token.end)] = token.kind
    return targets


def _safe_quoted_regex(value: str) -> bool:
    ending = value.rfind("/")
    quote = value[1:2]
    return (
        quote in {'"', "'"}
        and ending > 2
        and value[ending - 1 : ending] == quote
        and value.count(quote) == 2
    )


def _regex_body_length(value: str) -> int:
    ending = value.rfind("/")
    return max(0, ending - 1)
