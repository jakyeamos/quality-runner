from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.contracts import MAX_DOCUMENT_BYTES, relative_path

MAX_SKILLS = 120


def assess_skill_contract_quality(root: Path) -> dict[str, Any]:
    root = root.resolve()
    skill_root = root / "skills"
    conventional = list(skill_root.glob("*/SKILL.md")) if skill_root.is_dir() else []
    paths = sorted(set(conventional) | set(_declared_hosted_skill_paths(root)))[:MAX_SKILLS]
    if not paths:
        return {
            "score": None,
            "status": "not_applicable",
            "message": "No published or hosted skill surface was detected.",
            "evidence": [
                {
                    "path": "skills/",
                    "detail": "Hosting-specific assessment is not applicable without skill contracts.",
                }
            ],
        }

    findings: list[dict[str, str]] = []
    analyzed = 0
    for path in paths:
        if path.is_symlink():
            findings.append(
                {
                    "path": relative_path(root, path),
                    "detail": "host-specific assumption: symlinked skill source was not followed",
                }
            )
            continue
        try:
            if path.stat().st_size > MAX_DOCUMENT_BYTES:
                findings.append(
                    {
                        "path": relative_path(root, path),
                        "detail": "excessive mandatory structure: contract exceeds bounded audit size",
                    }
                )
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            findings.append(
                {
                    "path": relative_path(root, path),
                    "detail": "observable output missing: contract could not be read",
                }
            )
            continue
        analyzed += 1
        findings.extend(_static_findings(root, path, text))

    issue_count = len(findings)
    severe = any(
        item["detail"].startswith(("precedence hazard", "contradictory approval"))
        for item in findings
    )
    if analyzed == 0 or severe:
        score, status = 1, "blocked"
    elif issue_count:
        score, status = 2, "static_gaps"
    else:
        score, status = 3, "static_validated"
    return {
        "score": score,
        "status": status,
        "message": (
            f"Static review found {issue_count} bounded skill-contract gap(s); "
            "behavioral parity remains unproven."
            if issue_count
            else "Static skill contracts are clear; behavioral parity remains unproven."
        ),
        "evidence": findings[:16]
        or [
            {
                "path": "skills/",
                "detail": f"{analyzed} skill contract(s) passed bounded static review.",
            }
        ],
    }


def _declared_hosted_skill_paths(root: Path) -> list[Path]:
    manifest_path = root / ".agents/agent-usability.json"
    try:
        if (
            not manifest_path.is_file()
            or manifest_path.is_symlink()
            or manifest_path.stat().st_size > MAX_DOCUMENT_BYTES
        ):
            return []
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    payload = cast(dict[str, Any], payload)
    skills = payload.get("skills")
    if not isinstance(skills, list):
        return []

    paths: list[Path] = []
    for raw in cast(list[object], skills):
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, Any], raw)
        if item.get("source") != "hosted":
            continue
        contract_path = item.get("contract_path")
        if not isinstance(contract_path, str) or not contract_path:
            continue
        candidate = root / contract_path
        try:
            candidate.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        if candidate.name == "SKILL.md" and candidate.is_file():
            paths.append(candidate)
    return paths


def _static_findings(root: Path, path: Path, text: str) -> list[dict[str, str]]:
    lower = text.lower()
    lines = text.splitlines()
    relative = relative_path(root, path)
    details: list[str] = []
    frontmatter = "\n".join(lines[:12]).lower()
    description = next(
        (
            line.split(":", 1)[1].strip().lower()
            for line in lines[:12]
            if line.startswith("description:")
        ),
        "",
    )
    if re.search(r"\b(any task|all tasks|always use|whenever you)\b", description):
        details.append("overbroad trigger: frontmatter does not establish a narrow task boundary")
    if not any(
        term in lower
        for term in (
            "output",
            "report",
            "return",
            "produce",
            "show",
            "end with",
            "artifact",
            "ledger",
            "recommendation",
            "candidate portfolio",
        )
    ):
        details.append(
            "missing observable output: the contract does not name a user-visible result"
        )
    if not any(
        term in lower
        for term in (
            "definition of done",
            "done when",
            "complete when",
            "acceptance criteria",
            "## completion",
            "stopping condition",
            "completion criterion",
            "verification_and_done",
            "before finalizing",
            "verification rule",
            "require a succeeded response",
        )
    ):
        details.append("unclear definition of done: completion criteria are not explicit")
    observable_verification = any(
        term in lower
        for term in (
            "observed result",
            "verification signal",
            "evidence reference",
            "postcondition",
            "readback",
            "verifier",
            "verification.state",
        )
    )
    if any(term in lower for term in ("verify", "validate", "test")) and not (
        "```" in text
        or re.search(r"\b(?:pnpm|npm|pytest|cargo|python3|make)\b", lower)
        or observable_verification
    ):
        details.append("vague verification: verification is named without an observable command")
    read_lines = [
        index
        for index, line in enumerate(lines, start=1)
        if re.search(r"\b(read|load)\b.+\bbefore\b", line.lower())
    ]
    if read_lines and min(read_lines) > 120:
        details.append("buried required reads: required context appears after line 120")
    if ("ask before" in lower or "require approval" in lower) and (
        "do not ask" in lower or "without asking" in lower
    ):
        details.append("contradictory approval instructions: ask and no-ask rules coexist")
    if re.search(r"/users/[^/\s]+/|~/(?:\\.claude|\\.codex|\\.agents)", lower):
        details.append("host-specific assumption: an absolute or provider-home path is required")
    if any(
        term in lower
        for term in ("ignore previous instructions", "override higher", "supersede system")
    ):
        details.append("precedence hazard: contract appears to override higher-level instructions")
    mandatory = len(re.findall(r"\b(?:must|always|never|required)\b", lower))
    word_count = max(1, len(re.findall(r"\b\w+\b", lower)))
    if mandatory > 30 and mandatory / word_count > 0.03:
        details.append(
            f"excessive mandatory structure: {mandatory} mandatory terms reduce routing clarity"
        )
    if "name:" not in frontmatter or "description:" not in frontmatter:
        details.append(
            "host-specific assumption: portable name and description metadata are incomplete"
        )
    return [{"path": relative, "detail": detail} for detail in details]
