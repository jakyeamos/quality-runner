from __future__ import annotations

from quality_runner.source_evidence_lexer import LexedSource

RedactionTargets = dict[tuple[int, int], str]


def render_redactions(
    lexed: LexedSource,
    targets: RedactionTargets,
    *,
    placeholder: str,
) -> str:
    if not targets:
        return lexed.source
    token_kinds = {(token.start, token.end): token.kind for token in lexed.tokens}
    parts: list[str] = []
    position = 0
    for start, end, kind in _merged_targets(targets):
        if start < position:
            continue
        parts.append(lexed.source[position:start])
        parts.append(
            redacted_token_text(
                lexed.source[start:end],
                kind=kind if kind == "opaque" else token_kinds.get((start, end), kind),
                placeholder=placeholder,
            )
        )
        position = end
    parts.append(lexed.source[position:])
    return "".join(parts)


def _merged_targets(targets: RedactionTargets) -> list[tuple[int, int, str]]:
    merged: list[tuple[int, int, str]] = []
    for (start, end), kind in sorted(targets.items()):
        if start >= end:
            continue
        if merged and start < merged[-1][1]:
            previous_start, previous_end, previous_kind = merged[-1]
            merged[-1] = (
                previous_start,
                max(previous_end, end),
                previous_kind if previous_kind == kind else "opaque",
            )
        else:
            merged.append((start, end, kind))
    return merged


def redacted_token_text(value: str, *, kind: str, placeholder: str) -> str:
    if kind in {"comment", "regex"}:
        redacted = _redact_quoted_fragments(value, placeholder=placeholder)
        if redacted is not None:
            return redacted
        if kind == "regex":
            return value
    return "\n".join(f'"{placeholder}"' for _ in range(value.count("\n") + 1))


def _redact_quoted_fragments(value: str, *, placeholder: str) -> str | None:
    parts: list[str] = []
    position = 0
    index = 0
    changed = False
    while index < len(value):
        if value[index] not in {'"', "'", "`"}:
            index += 1
            continue
        quote = value[index]
        end = _quoted_fragment_end(value, index, quote)
        if end is None:
            return None
        parts.append(value[position:index])
        parts.append(f'"{placeholder}"')
        position = end
        index = end
        changed = True
    if not changed:
        return None
    parts.append(value[position:])
    return "".join(parts)


def _quoted_fragment_end(value: str, start: int, quote: str) -> int | None:
    index = start + 1
    while index < len(value):
        if value[index] == "\\":
            index += 2
        elif value[index] == quote:
            return index + 1
        else:
            index += 1
    return None
