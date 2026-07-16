from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from quality_runner.code_quality_findings import _finding
from quality_runner.ui_quality_helpers import _cue_type, _mapping, _stable, _strings, _text

UI_QUALITY_REPORT_SCHEMA = "quality-runner-ui-quality-report-v0.1"
_THEMES = ("light", "dark")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$")
_CHECKS = (
    ("primitive-semantic-component-ownership", "ui-token-ownership-"),
    ("resolvable-light-dark-roles", "ui-theme-role-"),
    ("wcag-contrast-thresholds", "ui-contrast-"),
    ("composed-modifiers", "ui-modifier-"),
    ("non-color-state-cues", "ui-state-"),
)
_DEFAULT_EXPECTED = "Keep the UI contract explicit and rerun the fixture-scoped check."
_DEFAULT_RISK = (
    "Incomplete UI contract evidence can hide hierarchy, accessibility, or extension regressions."
)


def load_ui_quality_fixture(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid UI quality fixture JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("UI quality fixture must be a JSON object")
    return cast(dict[str, object], payload)


def build_ui_quality_report(
    *, run_id: str, fixture: Mapping[str, object], fixture_path: str
) -> dict[str, object]:
    """Evaluate one UI contract fixture without activating a source scan or corpus entry."""

    run = _text(run_id, "run_id")
    fixture_id = _text(fixture.get("fixture_id"), "fixture_id")
    path = _text(fixture_path, "fixture_path")
    tokens = _mapping(fixture.get("tokens"), "tokens")
    primitives = _mapping(tokens.get("primitives"), "tokens.primitives")
    roles = _mapping(tokens.get("semantic_roles"), "tokens.semantic_roles")
    components = _mapping(fixture.get("components"), "components")
    modifiers = _mapping(fixture.get("modifiers"), "modifiers")
    states = _mapping(fixture.get("states"), "states")

    findings: list[dict[str, Any]] = []
    findings.extend(_ownership(path, primitives, roles, components))
    findings.extend(_contrast(path, primitives, roles, fixture.get("contrast_pairs")))
    findings.extend(_modifiers(path, modifiers, fixture.get("compositions")))
    findings.extend(_states(path, states))
    findings.sort(key=lambda item: (str(item["rule_id"]), str(item["evidence"])))
    for index, finding in enumerate(findings, start=1):
        finding["id"] = f"UI-{index:04d}"

    checks = _check_summaries(findings)
    report: dict[str, object] = {
        "schema": UI_QUALITY_REPORT_SCHEMA,
        "status": "report-only",
        "implementation_allowed": False,
        "scope": "fixture-only",
        "run_id": run,
        "fixture_id": fixture_id,
        "fixture_path": path,
        "result": "passed" if not findings else "findings",
        "checks": checks,
        "findings": findings,
        "summary": _summary(checks, findings),
    }
    validation = validate_ui_quality_report(report)
    if validation["passed"] is not True:
        raise ValueError("invalid UI quality report: " + "; ".join(_strings(validation["errors"])))
    return report


def validate_ui_quality_report(report: Mapping[str, object]) -> dict[str, object]:
    checks = report.get("checks")
    findings = report.get("findings")
    valid = (
        report.get("schema") == UI_QUALITY_REPORT_SCHEMA
        and report.get("status") == "report-only"
        and report.get("implementation_allowed") is False
        and report.get("scope") == "fixture-only"
        and isinstance(checks, list)
        and isinstance(findings, list)
        and report.get("result") == ("passed" if not findings else "findings")
    )
    count = len(findings) if isinstance(findings, list) else 0
    return {
        "passed": valid,
        "errors": [] if valid else ["invalid UI quality report"],
        "finding_count": count,
    }


def _ownership(
    path: str,
    primitives: Mapping[str, object],
    roles: Mapping[str, object],
    components: Mapping[str, object],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for role_name, raw_role in sorted(roles.items()):
        if not isinstance(raw_role, Mapping):
            continue
        for theme in _THEMES:
            if theme not in raw_role:
                findings.append(
                    _issue(
                        path, "ui-theme-role-missing-theme", f"semantic.{role_name} has no {theme}"
                    )
                )
                continue
            value = raw_role.get(theme)
            if not isinstance(value, str) or not value.startswith(("primitive.", "semantic.")):
                findings.append(
                    _issue(
                        path,
                        "ui-token-ownership-raw-semantic-value",
                        f"semantic.{role_name}.{theme} -> {value!r}",
                    )
                )
                continue
            prefix, target = value.split(".", 1)
            if target not in (primitives if prefix == "primitive" else roles):
                findings.append(
                    _issue(
                        path,
                        "ui-token-ownership-unknown-reference",
                        f"semantic.{role_name}.{theme} -> {value}",
                    )
                )
                continue
            _value, error = _resolve_role(role_name, theme, primitives, roles, ())
            if error:
                findings.append(
                    _issue(
                        path, "ui-theme-role-unresolvable", f"semantic.{role_name}.{theme}: {error}"
                    )
                )

    for component_name, raw_component in sorted(components.items()):
        if not isinstance(raw_component, Mapping):
            continue
        role_refs = raw_component.get("role_refs")
        if not isinstance(role_refs, list) or not role_refs:
            findings.append(
                _issue(
                    path,
                    "ui-token-ownership-component-without-roles",
                    f"component {component_name}",
                )
            )
            continue
        for reference in role_refs:
            rule = "ui-token-ownership-component-bypass"
            if (
                isinstance(reference, str)
                and reference.startswith("semantic.")
                and reference.removeprefix("semantic.") in roles
            ):
                continue
            findings.append(_issue(path, rule, f"component {component_name} -> {reference!r}"))
    return findings


def _contrast(
    path: str,
    primitives: Mapping[str, object],
    roles: Mapping[str, object],
    raw_pairs: object,
) -> list[dict[str, Any]]:
    if not isinstance(raw_pairs, list) or not raw_pairs:
        return [_issue(path, "ui-contrast-missing-pairs", "contrast_pairs is empty")]
    findings: list[dict[str, Any]] = []
    for index, raw_pair in enumerate(raw_pairs, start=1):
        if not isinstance(raw_pair, Mapping):
            findings.append(_issue(path, "ui-contrast-invalid-pair", f"contrast pair {index}"))
            continue
        pair_id = str(raw_pair.get("id") or f"pair-{index}")
        kind = raw_pair.get("kind")
        if kind not in {"text", "ui"}:
            findings.append(_issue(path, "ui-contrast-invalid-pair", f"{pair_id}: kind={kind!r}"))
            continue
        threshold = (
            3.0 if kind == "ui" or str(raw_pair.get("size", "normal")).lower() == "large" else 4.5
        )
        for theme in _pair_themes(raw_pair.get("themes")):
            foreground, foreground_error = _contrast_endpoint(
                raw_pair.get("foreground"), theme, primitives, roles
            )
            background, background_error = _contrast_endpoint(
                raw_pair.get("background"), theme, primitives, roles
            )
            if foreground_error or background_error:
                detail = "; ".join(item for item in (foreground_error, background_error) if item)
                findings.append(
                    _issue(path, "ui-contrast-unresolvable", f"{pair_id} @ {theme}: {detail}")
                )
                continue
            foreground_rgb = _parse_hex(foreground)
            background_rgb = _parse_hex(background)
            if foreground_rgb is None or background_rgb is None:
                findings.append(
                    _issue(
                        path, "ui-contrast-unverifiable", f"{pair_id} @ {theme}: non-hex endpoint"
                    )
                )
                continue
            ratio = _ratio(foreground_rgb, background_rgb)
            if ratio + 1e-9 < threshold:
                rule_id = "ui-contrast-text" if kind == "text" else "ui-contrast-ui"
                findings.append(
                    _issue(
                        path,
                        rule_id,
                        f"{pair_id} @ {theme}: {ratio:.2f}:1 < {threshold:.2f}:1",
                        expected=f"Meet at least {threshold:.1f}:1 for this {kind} pair.",
                    )
                )
    return findings


def _modifiers(
    path: str, modifiers: Mapping[str, object], raw_compositions: object
) -> list[dict[str, Any]]:
    if not modifiers or not isinstance(raw_compositions, list) or not raw_compositions:
        return [
            _issue(
                path,
                "ui-modifier-missing-contract",
                "modifiers or compositions are missing",
                severity="observation",
                confidence="medium",
            )
        ]
    findings: list[dict[str, Any]] = []
    for name, raw_modifier in sorted(modifiers.items()):
        if not isinstance(raw_modifier, Mapping):
            continue
        for requirement in _strings(raw_modifier.get("requires")):
            if not isinstance(requirement, str) or requirement not in modifiers:
                findings.append(
                    _issue(
                        path,
                        "ui-modifier-unknown-requirement",
                        f"modifier {name} requires {requirement!r}",
                    )
                )

    for index, raw_composition in enumerate(raw_compositions, start=1):
        if not isinstance(raw_composition, Mapping):
            continue
        composition_id = str(raw_composition.get("id") or f"composition-{index}")
        names = _strings(raw_composition.get("modifiers"))
        if not names:
            findings.append(
                _issue(
                    path, "ui-modifier-invalid-composition", f"{composition_id} has no modifiers"
                )
            )
            continue
        included = set(names)
        merged: dict[str, object] = {}
        for name in names:
            raw_modifier = modifiers.get(name)
            if not isinstance(raw_modifier, Mapping):
                findings.append(
                    _issue(
                        path, "ui-modifier-unknown-composed", f"{composition_id} includes {name}"
                    )
                )
                continue
            missing = sorted(_dependencies(name, modifiers) - included)
            if missing:
                findings.append(
                    _issue(
                        path,
                        "ui-modifier-dependency-omitted",
                        f"{composition_id} omits {', '.join(missing)}",
                    )
                )
            properties = raw_modifier.get("properties", {})
            if not isinstance(properties, Mapping):
                continue
            for property_name, value in properties.items():
                if property_name in merged and merged[property_name] != value:
                    findings.append(
                        _issue(
                            path,
                            "ui-modifier-conflict",
                            f"{composition_id} conflicts on {property_name}",
                        )
                    )
                merged[property_name] = value
        expected = raw_composition.get("expected_properties")
        if not isinstance(expected, Mapping):
            findings.append(
                _issue(
                    path, "ui-modifier-missing-expectation", f"{composition_id} expected_properties"
                )
            )
        elif dict(expected) != merged:
            findings.append(
                _issue(
                    path,
                    "ui-modifier-composition-mismatch",
                    f"{composition_id}: {_stable(dict(expected))} != {_stable(merged)}",
                )
            )
    return findings


def _states(path: str, states: Mapping[str, object]) -> list[dict[str, Any]]:
    if not states:
        return [_issue(path, "ui-state-missing-catalog", "states is empty")]
    findings: list[dict[str, Any]] = []
    for name, raw_state in sorted(states.items()):
        cues = raw_state.get("cues") if isinstance(raw_state, Mapping) else []
        if not isinstance(cues, list):
            cues = []
        if not any(_cue_type(cue) not in {None, "color", "colour"} for cue in cues):
            findings.append(
                _issue(
                    path, "ui-state-missing-non-color-cue", f"state {name}: cues={_stable(cues)}"
                )
            )
    return findings


def _resolve_role(
    name: str,
    theme: str,
    primitives: Mapping[str, object],
    roles: Mapping[str, object],
    stack: tuple[tuple[str, str], ...],
) -> tuple[str | None, str | None]:
    marker = (name, theme)
    if marker in stack:
        return None, "semantic alias cycle"
    role = roles.get(name)
    if not isinstance(role, Mapping):
        return None, "role mapping is missing"
    value = role.get(theme)
    if not isinstance(value, str):
        return None, f"{theme} mapping is missing or not a string"
    if value.startswith("primitive."):
        primitive = primitives.get(value.removeprefix("primitive."))
        return (
            (primitive, None)
            if isinstance(primitive, str)
            else (None, "primitive is missing or not a string")
        )
    if value.startswith("semantic."):
        return _resolve_role(
            value.removeprefix("semantic."), theme, primitives, roles, (*stack, marker)
        )
    return None, "role reference must start with primitive. or semantic."


def _contrast_endpoint(
    reference: object,
    theme: str,
    primitives: Mapping[str, object],
    roles: Mapping[str, object],
) -> tuple[str | None, str | None]:
    return (
        _resolve_role(reference.removeprefix("semantic."), theme, primitives, roles, ())
        if isinstance(reference, str) and reference.startswith("semantic.")
        else (None, "contrast endpoint must reference semantic.*")
    )


def _dependencies(name: str, modifiers: Mapping[str, object]) -> set[str]:
    pending = [name]
    seen: set[str] = set()
    dependencies: set[str] = set()
    while pending:
        raw_modifier = modifiers.get(pending.pop())
        if not isinstance(raw_modifier, Mapping):
            continue
        for requirement in _strings(raw_modifier.get("requires")):
            if requirement not in seen:
                seen.add(requirement)
                dependencies.add(requirement)
                pending.append(requirement)
    return dependencies


def _pair_themes(value: object) -> list[str]:
    themes = [item for item in value if item in _THEMES] if isinstance(value, list) else []
    return themes or list(_THEMES)


def _parse_hex(value: str | None) -> tuple[float, float, float] | None:
    if value is None or _HEX_COLOR.fullmatch(value) is None:
        return None
    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(character * 2 for character in digits)
    red, green, blue = (int(digits[index : index + 2], 16) / 255 for index in (0, 2, 4))
    return red, green, blue


def _ratio(foreground: tuple[float, float, float], background: tuple[float, float, float]) -> float:
    def luminance(rgb: tuple[float, float, float]) -> float:
        channels = tuple(
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in rgb
        )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    first, second = luminance(foreground), luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def _check_summaries(findings: list[dict[str, Any]]) -> list[dict[str, object]]:
    return [
        {
            "id": check_id,
            "enforceability": "deterministic",
            "scope": "fixture-only",
            "status": "passed"
            if not any(str(item["rule_id"]).startswith(prefix) for item in findings)
            else "matched",
            "finding_count": sum(str(item["rule_id"]).startswith(prefix) for item in findings),
        }
        for check_id, prefix in _CHECKS
    ]


def _summary(checks: Sequence[object], findings: Sequence[object]) -> dict[str, int]:
    return {
        "check_count": len(checks),
        "passed_check_count": sum(
            isinstance(item, Mapping) and item.get("status") == "passed" for item in checks
        ),
        "finding_count": len(findings),
        "deterministic_check_count": sum(
            isinstance(item, Mapping) and item.get("enforceability") == "deterministic"
            for item in checks
        ),
        "judgment_only_check_count": 0,
    }


def _issue(
    path: str,
    rule_id: str,
    evidence: str,
    *,
    expected: str | None = None,
    risk: str | None = None,
    severity: str = "warning",
    confidence: str = "high",
) -> dict[str, Any]:
    return _finding(
        category="ui_structural",
        severity=severity,
        confidence=confidence,
        file=path,
        line=1,
        rule_id=rule_id,
        evidence=evidence,
        expected_improvement=expected or _DEFAULT_EXPECTED,
        risk=risk or _DEFAULT_RISK,
        verification="Review the fixture-scoped contract and rerun the QR UI quality check.",
        remediation_bucket="UI design-system quality",
    )
