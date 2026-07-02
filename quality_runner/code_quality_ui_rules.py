from __future__ import annotations

import re
from typing import Any

from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import _is_ui_file, _verification_for_path


def _ui_structural_findings(
    relative_path: str, line: str, line_number: int
) -> list[dict[str, Any]]:
    if not _is_ui_file(relative_path):
        return []
    findings: list[dict[str, Any]] = []
    strict_specs = [
        (
            "nonsemantic-click-target",
            bool(re.search(r"<(?:div|span)\b[^>]*\bonClick\s*=", line)),
            "Use a button/link or add the complete keyboard and ARIA contract.",
            "Click-only div/span controls are not reliably keyboard or screen-reader accessible.",
        ),
        (
            "positive-tabindex",
            bool(re.search(r"\btabIndex=\{?[1-9]\d*\}?|\btabindex=['\"][1-9]\d*['\"]", line)),
            "Use natural DOM order with tabindex 0 or -1 only when needed.",
            "Positive tabindex creates a fragile, surprising focus order.",
        ),
        (
            "removed-focus-outline",
            "outline: none" in line or "outline:none" in line or "focus:outline-none" in line,
            "Preserve a visible focus style with focus-visible or equivalent.",
            "Removing focus outlines blocks keyboard users from seeing their position.",
        ),
        (
            "off-scale-spacing",
            _has_off_scale_spacing(line),
            "Use the project's spacing scale instead of arbitrary raw values.",
            "Off-scale spacing values make UI rhythm harder to maintain.",
        ),
    ]
    for rule_id, matched, expected, risk in strict_specs:
        if matched:
            findings.append(
                _finding(
                    category="ui_structural",
                    severity="warning",
                    confidence="medium",
                    file=relative_path,
                    line=line_number,
                    rule_id=rule_id,
                    evidence=line,
                    expected_improvement=expected,
                    risk=risk,
                    verification=_verification_for_path(relative_path),
                    remediation_bucket="UI accessibility and structural quality",
                )
            )

    if _icon_only_button_without_label(line):
        findings.append(
            _finding(
                category="ui_structural",
                severity="warning",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="icon-button-missing-label",
                evidence=line,
                expected_improvement="Add an accessible name via visible text or aria-label.",
                risk="Icon-only buttons without names are announced as anonymous controls.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="UI accessibility and structural quality",
            )
        )

    specs = [
        (
            "gradient-text",
            "background-clip" in line and "text" in line and "gradient(" in line,
            "Use a solid text color; reserve gradients for meaningful surfaces.",
            "Gradient text is a common low-signal visual trope.",
        ),
        (
            "decorative-grid-background",
            "linear-gradient" in line
            and "1px" in line
            and ("90deg" in line or line.count("linear-gradient") > 1),
            "Remove decorative grid backgrounds unless the surface is a real canvas/map/measurement tool.",
            "Decorative grids read as generic AI decoration.",
        ),
        (
            "side-stripe-border",
            bool(re.search(r"border-(?:left|right)\s*:\s*(?:[2-9]|\d{2,})px", line)),
            "Use full borders, background tints, icons, or no accent instead.",
            "Side-stripe accents are a repetitive card/callout trope.",
        ),
        (
            "excessive-border-radius",
            bool(re.search(r"border-radius\s*:\s*(?:3[2-9]|[4-9]\d|\d{3,})px", line)),
            "Keep cards and panels within the project's radius scale.",
            "Over-rounded containers make interfaces feel generic.",
        ),
        (
            "arbitrary-z-index",
            bool(re.search(r"z-index\s*:\s*(?:999|9999|\d{4,})", line)),
            "Use a semantic z-index scale.",
            "Arbitrary stacking values make overlays fragile.",
        ),
        (
            "nested-card-markup",
            line.count('className="card') + line.count("className='card") >= 2,
            "Avoid nesting cards inside cards; flatten the layout or use sections.",
            "Nested cards create heavy, unclear visual hierarchy.",
        ),
        (
            "risky-hidden-reveal",
            bool(
                re.search(r"\b(?:opacity\s*:\s*0|visibility\s*:\s*hidden|display\s*:\s*none)", line)
            ),
            "Ensure reveal animations enhance visible content rather than gating it.",
            "Hidden default content can ship blank in paused/headless renderers.",
        ),
        (
            "placeholder-copy",
            bool(
                re.search(
                    r"\b(?:lorem ipsum|sample text|dummy text|replace me|todo copy|"
                    r"placeholder (?:copy|text|content))\b",
                    line,
                    re.IGNORECASE,
                )
            ),
            "Use realistic product copy so wrapping, hierarchy, and edge cases are visible.",
            "Placeholder copy hides real layout and comprehension problems.",
        ),
    ]
    findings.extend(
        _finding(
            category="ui_structural",
            severity="observation",
            confidence="medium",
            file=relative_path,
            line=line_number,
            rule_id=rule_id,
            evidence=line,
            expected_improvement=expected,
            risk=risk,
            verification=_verification_for_path(relative_path),
            remediation_bucket="UI structural quality",
        )
        for rule_id, matched, expected, risk in specs
        if matched
    )
    return findings


def _ui_file_level_findings(
    relative_path: str, text: str, lines: list[str]
) -> list[dict[str, Any]]:
    if not _is_ui_file(relative_path):
        return []

    findings: list[dict[str, Any]] = []
    findings.extend(_image_element_findings(relative_path, lines))

    fetches_data = _fetches_ui_data(relative_path, text)
    if fetches_data and not re.search(r"\b(?:isLoading|loading|isPending|Skeleton)\b", text):
        line_number, evidence = _first_matching_line(
            lines, r"\b(?:useQuery\s*\(|trpc\.|fetch\s*\()"
        )
        findings.append(
            _ui_state_finding(
                relative_path,
                line_number,
                "missing-loading-state",
                evidence,
                "Render an explicit loading or skeleton state near the data boundary.",
                "Data-backed UI can flash blank or stale content without a loading state.",
            )
        )
    if fetches_data and not re.search(r"\b(?:isError|error|ErrorState|role=['\"]alert)\b", text):
        line_number, evidence = _first_matching_line(
            lines, r"\b(?:useQuery\s*\(|trpc\.|fetch\s*\()"
        )
        findings.append(
            _ui_state_finding(
                relative_path,
                line_number,
                "missing-error-state",
                evidence,
                "Render a specific error state with a recovery path.",
                "Data-backed UI without error handling strands users on failed requests.",
            )
        )
    map_line = _first_data_backed_map_line(relative_path, text, lines)
    if map_line is not None and not re.search(
        r"\b(?:empty|no results|no items|length\s*===\s*0|length\s*<\s*1)\b",
        text,
        re.IGNORECASE,
    ):
        line_number, evidence = map_line
        findings.append(
            _ui_state_finding(
                relative_path,
                line_number,
                "missing-empty-state",
                evidence,
                "Render a deliberate empty state before mapping collection data.",
                "Empty collections otherwise collapse into blank UI.",
            )
        )

    forwarded_props: dict[str, list[tuple[int, str]]] = {}
    for index, line in enumerate(lines, start=1):
        if re.search(r"<[A-Z][A-Za-z0-9_.]*\b", line) is None:
            continue
        for match in re.finditer(r"\b([A-Za-z_$][\w$]*)=\{\1\}", line):
            prop = match.group(1)
            if prop not in {"key", "ref"}:
                forwarded_props.setdefault(prop, []).append((index, line))
    for prop, occurrences in sorted(forwarded_props.items()):
        if len(occurrences) < 4:
            continue
        line_number, evidence = occurrences[0]
        findings.append(
            _finding(
                category="ui_structural",
                severity="observation",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="deep-prop-drilling",
                evidence=f"{prop} forwarded {len(occurrences)} times; first: {evidence}",
                expected_improvement="Introduce composition, context, or a narrower owner boundary.",
                risk="Repeated prop forwarding makes component trees brittle to state changes.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="UI component architecture",
            )
        )
    return findings


def _image_element_findings(relative_path: str, lines: list[str]) -> list[dict[str, Any]]:
    if not _is_jsx_like_file(relative_path):
        return []
    findings: list[dict[str, Any]] = []
    for line_number, snippet in _jsx_image_elements(lines):
        if not re.search(r"\balt\s*=", snippet):
            findings.append(
                _image_finding(
                    relative_path,
                    line_number,
                    "image-missing-alt",
                    snippet,
                    "Add meaningful alt text or an explicit empty alt for decorative images.",
                    "Images without alt text disappear from screen-reader context.",
                )
            )
        if not _has_stable_image_dimensions(snippet):
            findings.append(
                _image_finding(
                    relative_path,
                    line_number,
                    "image-missing-dimensions",
                    snippet,
                    "Set explicit image dimensions or a stable aspect-ratio.",
                    "Images without stable dimensions can cause layout shift.",
                )
            )
        if re.search(r"\b(?:hero|lcp|above[-_ ]?fold)\b", snippet, re.IGNORECASE) and re.search(
            r"\bloading\s*=\s*['\"]lazy['\"]", snippet
        ):
            findings.append(
                _image_finding(
                    relative_path,
                    line_number,
                    "hero-image-lazy-loading",
                    snippet,
                    "Do not lazy-load the LCP or hero image; prioritize it deliberately.",
                    "Lazy-loading above-the-fold imagery delays LCP.",
                )
            )
    return findings


def _jsx_image_elements(lines: list[str]) -> list[tuple[int, str]]:
    elements: list[tuple[int, str]] = []
    active_start: int | None = None
    active_lines: list[str] = []
    for index, line in enumerate(lines, start=1):
        if active_start is None:
            if re.search(r"<(?:img|Image)\b", line) is None:
                continue
            active_start = index
            active_lines = [line]
        else:
            active_lines.append(line)

        if ">" not in line:
            continue
        snippet = "\n".join(active_lines)
        elements.append((active_start, snippet))
        active_start = None
        active_lines = []
    return elements


def _image_finding(
    relative_path: str,
    line_number: int,
    rule_id: str,
    evidence: str,
    expected_improvement: str,
    risk: str,
) -> dict[str, Any]:
    return _finding(
        category="ui_structural",
        severity="warning",
        confidence="medium",
        file=relative_path,
        line=line_number,
        rule_id=rule_id,
        evidence=evidence,
        expected_improvement=expected_improvement,
        risk=risk,
        verification=_verification_for_path(relative_path),
        remediation_bucket="UI accessibility and structural quality",
    )


def _has_stable_image_dimensions(snippet: str) -> bool:
    return (
        re.search(r"\bwidth\s*=", snippet) is not None
        and re.search(r"\bheight\s*=", snippet) is not None
    ) or re.search(r"\b(?:fill|sizes|aspect-|size-|w-\d|h-\d)\b", snippet) is not None


def _is_jsx_like_file(relative_path: str) -> bool:
    return relative_path.endswith((".html", ".jsx", ".tsx"))


def _fetches_ui_data(relative_path: str, text: str) -> bool:
    if "/api/" in f"/{relative_path}":
        return False
    if re.search(r"\b(?:useQuery\s*\(|trpc\.[\w.]+\.useQuery\s*\(|useSWR\s*\()", text):
        return True
    is_client_surface = '"use client"' in text or "'use client'" in text
    has_client_fetch = (
        re.search(r"\bfetch\s*\(", text) is not None
        and re.search(
            r"\b(?:useEffect|useState|useReducer)\s*\(",
            text,
        )
        is not None
    )
    return is_client_surface and has_client_fetch


def _first_data_backed_map_line(
    relative_path: str, text: str, lines: list[str]
) -> tuple[int, str] | None:
    if not _fetches_ui_data(relative_path, text):
        return None
    for index, line in enumerate(lines, start=1):
        if ".map(" not in line or "Array.from" in line:
            continue
        receiver = _map_receiver(line)
        if receiver and _looks_static_collection(receiver):
            continue
        return index, line
    return None


def _fetches_ui_text(text: str) -> bool:
    return (
        re.search(r"\b(?:useQuery\s*\(|trpc\.[\w.]+\.useQuery\s*\(|useSWR\s*\(|fetch\s*\()", text)
        is not None
    )


def _map_receiver(line: str) -> str | None:
    match = re.search(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.map\s*\(", line)
    return match.group(1) if match else None


def _looks_static_collection(receiver: str) -> bool:
    static_names = (
        "actions",
        "breadcrumbs",
        "features",
        "links",
        "menu",
        "nav",
        "routes",
        "sections",
        "social",
        "tabs",
    )
    normalized = receiver.split(".")[-1].lower()
    return any(name in normalized for name in static_names)


def _ui_state_finding(
    relative_path: str,
    line_number: int,
    rule_id: str,
    evidence: str,
    expected_improvement: str,
    risk: str,
) -> dict[str, Any]:
    return _finding(
        category="ui_structural",
        severity="warning",
        confidence="medium",
        file=relative_path,
        line=line_number,
        rule_id=rule_id,
        evidence=evidence,
        expected_improvement=expected_improvement,
        risk=risk,
        verification=_verification_for_path(relative_path),
        remediation_bucket="UI state coverage",
    )


def _first_matching_line(lines: list[str], pattern: str) -> tuple[int, str]:
    for index, line in enumerate(lines, start=1):
        if re.search(pattern, line, re.IGNORECASE):
            return index, line
    return 1, lines[0] if lines else ""


def _has_off_scale_spacing(line: str) -> bool:
    for match in re.finditer(
        r"\b(?:padding|margin|gap|inset|top|right|bottom|left)(?:-[a-z]+)?\s*:\s*"
        r"([0-9]*\.?[0-9]+)(px|rem)\b",
        line,
    ):
        amount = float(match.group(1))
        unit = match.group(2)
        if amount == 0:
            continue
        if unit == "px" and amount > 1 and amount % 4 != 0:
            return True
        if unit == "rem" and (amount * 4) % 1 != 0:
            return True
    return (
        re.search(
            r"\b(?:p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml|gap)-\[(?:"
            r"(?!0(?:px|rem)\])(?:[0-9]*\.?[0-9]+)(?:px|rem))\]",
            line,
        )
        is not None
    )


def _icon_only_button_without_label(line: str) -> bool:
    if "<button" not in line or "aria-label=" in line or "title=" in line:
        return False
    return (
        re.search(
            r"<button\b[^>]*>\s*(?:<[A-Z][A-Za-z0-9]*(?:\s[^>]*)?\s*/?>|{[^}]*Icon[^}]*})\s*</button>",
            line,
        )
        is not None
    )
