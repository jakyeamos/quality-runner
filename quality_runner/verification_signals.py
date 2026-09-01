"""Discover explicit test-effectiveness declarations without claiming results.

The scan can prove that a repository declares a coverage or mutation command,
but it cannot prove that the command ran successfully.  Keeping those states
separate prevents a configured-but-stale report from becoming a quality pass.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

SIGNAL_IDS = ("coverage", "mutation")

_SIGNAL_PATTERNS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "coverage": (
        (
            "coverage flag",
            re.compile(r"(?<![\w-])--coverage(?:\b|=)", re.IGNORECASE),
        ),
        (
            "cov flag",
            re.compile(r"(?<![\w-])--cov(?:\b|=)", re.IGNORECASE),
        ),
        (
            "coverage tool",
            re.compile(
                r"(?<![\w-])(?:pytest-cov|coverage(?:\s+(?:run|report|xml|html))?|c8|nyc|lcov|istanbul)(?![\w-])",
                re.IGNORECASE,
            ),
        ),
        (
            "coverage-named command",
            re.compile(r"(?<![\w-])(?:test:)?coverage(?![\w-])", re.IGNORECASE),
        ),
    ),
    "mutation": (
        (
            "mutation runner",
            re.compile(
                r"(?<![\w-])(?:stryker|mutmut|cosmic[-_ ]ray|cargo[-_ ]mutants|pitest)(?![\w-])",
                re.IGNORECASE,
            ),
        ),
        (
            "mutation flag",
            re.compile(r"(?<![\w-])--mutate(?:\b|=)", re.IGNORECASE),
        ),
        (
            "mutation-named command",
            re.compile(
                r"(?<![\w-])(?:test:)?(?:mutation|mutants?|mutation-testing)(?![\w-])",
                re.IGNORECASE,
            ),
        ),
    ),
}


def analyze_verification_signals(
    *,
    scripts: Mapping[str, str],
    quality_commands: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Return explicit coverage and mutation declarations found in a scan.

    ``status`` describes only what the repository declares: it is not an
    execution result.  ``execution`` is intentionally always
    ``"not_observed"`` because repository discovery does not run target
    commands or validate their reports.
    """
    commands = list(quality_commands)
    observations: dict[str, list[dict[str, str]]] = {signal: [] for signal in SIGNAL_IDS}
    inspected = bool(scripts) or bool(commands)

    for name, command in sorted(scripts.items()):
        _collect_observations(
            text=f"{name} {command}",
            source=f"package.json:scripts.{name}",
            source_type="package_script",
            observations=observations,
        )

    for command in commands:
        command_text = _string_value(command.get("command"))
        capability_id = _string_value(command.get("id"))
        if not command_text and not capability_id:
            continue
        _collect_observations(
            text=f"{capability_id} {command_text}",
            source=_string_value(command.get("source")) or "quality_command",
            source_type=_string_value(command.get("source_type")) or "quality_command",
            observations=observations,
        )

    return {
        signal: _signal_report(
            observations=observations[signal],
            inspected=inspected,
        )
        for signal in SIGNAL_IDS
    }


def _collect_observations(
    *,
    text: str,
    source: str,
    source_type: str,
    observations: dict[str, list[dict[str, str]]],
) -> None:
    for signal in SIGNAL_IDS:
        evidence = _matching_evidence(signal, text)
        if evidence is None:
            continue
        observation = {
            "source": source,
            "source_type": source_type,
            "evidence": evidence,
        }
        if observation not in observations[signal]:
            observations[signal].append(observation)


def _matching_evidence(signal: str, text: str) -> str | None:
    for label, pattern in _SIGNAL_PATTERNS[signal]:
        if pattern.search(text):
            return label
    return None


def _signal_report(
    *,
    observations: list[dict[str, str]],
    inspected: bool,
) -> dict[str, object]:
    observations.sort(key=lambda item: (item["source"], item["source_type"], item["evidence"]))
    return {
        "status": "declared" if observations else "not_declared" if inspected else "unknown",
        "execution": "not_observed",
        "observations": observations,
    }


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""
