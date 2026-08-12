from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quality_runner.ci_gate_rules import RULES, Rule

CI_GATE_AUDIT_SCHEMA = "quality-runner-ci-gate-candidates/v1"
MAX_FILES = 4_000
MAX_TEXT_FILES = 240
MAX_TEXT_BYTES = 128_000
MAX_CANDIDATES = 16

EXCLUDED_DIRECTORIES = {
    ".build",
    ".cache",
    ".git",
    ".gradle",
    ".idea",
    ".mypy_cache",
    ".next",
    ".nox",
    ".pnpm-store",
    ".pytest_cache",
    ".quality-runner",
    ".ruff_cache",
    ".swiftpm",
    ".tox",
    ".turbo",
    ".venv",
    "DerivedData",
    "__pycache__",
    "artifacts",
    "build",
    "coverage",
    "data",
    "dist",
    "node_modules",
    "runs",
    "target",
    "vendor",
    "worktrees",
}

_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".mjs",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
_TEXT_NAMES = {"dockerfile", "makefile", "justfile", "package.json", "pyproject.toml"}


@dataclass(frozen=True)
class Signal:
    kind: str
    path: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "path": self.path, "reason": self.reason}


def audit_ci_gate_candidates(
    repo_root: Path,
    *,
    generated_at: str,
    branch: str | None = None,
    head_sha: str | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")
    resolved_branch = branch or _git_value(root, "rev-parse", "--abbrev-ref", "HEAD")
    resolved_head = head_sha or _git_value(root, "rev-parse", "HEAD")
    files, truncated = _inventory(root)
    texts = _read_texts(root, files)
    workflow_contexts = _workflow_contexts(files, texts)
    semantic_files = [relative for relative in files if _is_semantic_source(relative)]
    semantic_texts = {
        relative: content for relative, content in texts.items() if _is_semantic_source(relative)
    }
    candidates = [
        candidate
        for rule in RULES
        if (
            candidate := _evaluate_rule(
                rule, semantic_files, semantic_texts, files, texts, workflow_contexts
            )
        )
        is not None
    ][:MAX_CANDIDATES]
    report: dict[str, Any] = {
        "schema": CI_GATE_AUDIT_SCHEMA,
        "status": "partial" if truncated else "complete",
        "generated_at": generated_at,
        "repository": {
            "name": root.name,
            "branch": resolved_branch,
            "head_sha": resolved_head,
        },
        "policy": {
            "authority": "recommendation_only",
            "implementation_allowed": False,
            "promotion_requirement": (
                "A repository-owned CI profile must explicitly accept a candidate before it becomes required."
            ),
        },
        "inventory": {
            "file_count": len(files),
            "text_file_count": len(texts),
            "truncated": truncated,
            "excluded_directories": sorted(EXCLUDED_DIRECTORIES),
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    report["provenance_hash"] = _digest(report)
    return report


def _inventory(root: Path) -> tuple[list[str], bool]:
    files: list[str] = []
    truncated = False
    for current, directories, names in os.walk(root):
        directories[:] = sorted(
            directory for directory in directories if directory not in EXCLUDED_DIRECTORIES
        )
        current_path = Path(current)
        for name in sorted(names):
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                continue
            files.append(path.relative_to(root).as_posix())
            if len(files) >= MAX_FILES:
                truncated = True
                return files, truncated
    return files, truncated


def _read_texts(root: Path, files: Iterable[str]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for relative in files:
        path = root / relative
        if path.suffix.casefold() not in _TEXT_SUFFIXES and path.name.casefold() not in _TEXT_NAMES:
            continue
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                continue
            texts[relative] = path.read_text(encoding="utf-8", errors="ignore").casefold()
        except OSError:
            continue
        if len(texts) >= MAX_TEXT_FILES:
            break
    return texts


def _evaluate_rule(
    rule: Rule,
    semantic_files: list[str],
    semantic_texts: Mapping[str, str],
    all_files: list[str],
    all_texts: Mapping[str, str],
    workflow_contexts: list[dict[str, str]],
) -> dict[str, Any] | None:
    groups: list[dict[str, Any]] = []
    all_signals: list[Signal] = []
    first_group_structural_anchor = False
    for index, (label, terms) in enumerate(rule.signal_groups):
        signals = _signals_for_terms(label, terms, semantic_files, semantic_texts)
        if signals:
            groups.append({"label": label, "evidence": [item.as_dict() for item in signals[:3]]})
            all_signals.extend(signals[:3])
            if index == 0:
                first_group_structural_anchor = any(item.kind == "path" for item in signals)
    if len(groups) < 2 or not first_group_structural_anchor:
        return None
    confidence = "high" if len(groups) == len(rule.signal_groups) else "medium"
    recommendation = (
        "required_candidate"
        if confidence == "high" and rule.impact == "high"
        else "optional_candidate"
        if rule.trigger_event in {"release", "scheduled"}
        else "review_required"
    )
    matching_contexts = _matching_contexts(rule, workflow_contexts)
    negative_controls = _negative_controls(rule, all_files, all_texts)
    blockers: list[str] = []
    if not matching_contexts:
        blockers.append("No matching CI check context was discovered.")
    if not negative_controls:
        blockers.append("No candidate-specific negative control was discovered.")
    blockers.append("Repository-owned policy has not accepted this candidate as a requirement.")
    blockers.append("A fresh candidate-commit check result has not been observed.")
    admission_state = (
        "implementation_detected" if matching_contexts and negative_controls else "proposal_only"
    )
    evidence = _deduplicate_signals(all_signals)
    return {
        "id": rule.gate_id,
        "label": rule.label,
        "recommendation": recommendation,
        "confidence": confidence,
        "invariant": rule.invariant,
        "failure_mode": rule.failure_mode,
        "evidence": [signal.as_dict() for signal in evidence[:8]],
        "suggested_trigger": {
            "event": rule.trigger_event,
            "paths": list(rule.trigger_paths),
        },
        "suggested_check_context": rule.check_context,
        "existing_check": {
            "status": "related_context_found" if matching_contexts else "not_found",
            "contexts": matching_contexts[:8],
        },
        "negative_controls": negative_controls[:8],
        "admission": {"state": admission_state, "blockers": blockers},
        "next_step": (
            "Review the invariant, add a failing negative control and exact CI context, then explicitly "
            "accept or reject the gate in the repository-owned CI profile."
        ),
    }


def _signals_for_terms(
    label: str,
    terms: tuple[str, ...],
    files: Iterable[str],
    texts: Mapping[str, str],
) -> list[Signal]:
    signals: list[Signal] = []
    for relative in files:
        lowered = f"/{relative.casefold()}"
        matched = next((term for term in terms if term in lowered), None)
        if matched:
            signals.append(Signal("path", relative, f"{label}: path matches {matched}"))
            if len(signals) >= 3:
                return signals
    for relative, content in texts.items():
        matched = next((term for term in terms if term in content), None)
        if matched:
            signals.append(Signal("semantic", relative, f"{label}: declares {matched}"))
            if len(signals) >= 3:
                break
    return signals


def _workflow_contexts(files: Iterable[str], texts: Mapping[str, str]) -> list[dict[str, str]]:
    contexts: list[dict[str, str]] = []
    for relative in files:
        lowered = relative.casefold()
        if not lowered.startswith(".github/workflows/") or not lowered.endswith((".yml", ".yaml")):
            continue
        content = texts.get(relative, "")
        name_match = re.search(r"(?m)^name:\s*([^#\n]+)", content)
        if name_match:
            value = name_match.group(1).strip().strip("'\"")
            if value and "${{" not in value:
                contexts.append({"context": value[:100], "path": relative})
        jobs_match = re.search(
            r"(?ms)^jobs:\s*\n(?P<jobs>.*?)(?=^[a-z][a-z0-9_-]*:\s*$|\Z)", content
        )
        if jobs_match:
            for job in re.finditer(r"(?m)^  ([a-z0-9_-]+):\s*$", jobs_match.group("jobs")):
                contexts.append({"context": job.group(1), "path": relative})
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for context in contexts:
        unique[(context["context"], context["path"])] = context
    return list(unique.values())[:80]


def _matching_contexts(rule: Rule, contexts: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    terms = {
        part
        for part in re.split(r"[^a-z0-9]+", f"{rule.gate_id} {rule.label}".casefold())
        if len(part) >= 4 and part not in {"custom", "contract"}
    }
    return [
        context
        for context in contexts
        if any(term in context["context"].casefold() for term in terms)
    ]


def _negative_controls(
    rule: Rule, files: Iterable[str], texts: Mapping[str, str]
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for relative in files:
        lowered = relative.casefold()
        if not any(part in lowered.split("/") for part in ("test", "tests", "fixtures", "fixture")):
            continue
        content = texts.get(relative, "")
        term = next((candidate for candidate in rule.negative_terms if candidate in content), None)
        fixture_path = any(part in {"fixture", "fixtures"} for part in lowered.split("/"))
        if fixture_path and not any(candidate in lowered for candidate in rule.negative_terms):
            continue
        negative_marker = next(
            (
                marker
                for marker in (
                    "break",
                    "corrupt",
                    "error",
                    "fail",
                    "invalid",
                    "mismatch",
                    "missing",
                    "reject",
                    "rollback",
                    "stale",
                )
                if marker in content
            ),
            None,
        )
        if term and negative_marker:
            results.append({"path": relative, "reason": f"test or fixture covers {term}"})
        if len(results) >= 8:
            break
    return results


def _deduplicate_signals(signals: Iterable[Signal]) -> list[Signal]:
    unique: dict[tuple[str, str], Signal] = {}
    for signal in signals:
        unique[(signal.kind, signal.path)] = signal
    return list(unique.values())


def _is_semantic_source(relative: str) -> bool:
    parts = Path(relative).parts
    lowered_parts = {part.casefold() for part in parts}
    if lowered_parts & {"fixtures", "fixture", "test", "tests", ".planning"}:
        return False
    if relative.casefold().startswith("docs/examples/"):
        return False
    return relative not in {
        "quality_runner/ci_gate_audit.py",
        "quality_runner/ci_gate_rules.py",
    }


def _git_value(root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=root, check=False, capture_output=True, text=True, timeout=5
    )
    value = result.stdout.strip()
    return value or None


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
