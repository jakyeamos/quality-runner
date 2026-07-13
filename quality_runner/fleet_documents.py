from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_safe_directory, write_text


def write_fleet_documents(*, output_dir: Path, results: list[dict[str, Any]]) -> dict[str, str]:
    output_dir = prepare_safe_directory(output_dir)
    per_repo_dir = prepare_safe_directory(output_dir / "per-repo-summaries")

    repo_docs: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        repo_name = _repo_name(result)
        slug = _slug(result.get("repo_slug") or repo_name, fallback=f"repo-{index}")
        doc_path = per_repo_dir / f"{index:03d}-{slug}.md"
        context = _repo_context(result=result, repo_name=repo_name, doc_path=doc_path)
        write_text(doc_path, _render_repo_doc(context))
        repo_docs.append(context)

    index_path = per_repo_dir / "INDEX.md"
    phase_path = output_dir / "fleet-remediation-phases.md"
    write_text(index_path, _render_index(repo_docs=repo_docs, phase_path=phase_path))
    write_text(phase_path, _render_phase_draft(repo_docs=repo_docs, index_path=index_path))
    return {
        "per_repo_dir": str(per_repo_dir),
        "index_md": str(index_path),
        "phase_md": str(phase_path),
    }


def _repo_context(*, result: dict[str, Any], repo_name: str, doc_path: Path) -> dict[str, Any]:
    run_dir = _path_or_none(result.get("artifact_path"))
    audit = _load_json(run_dir / "quality-audit.json") if run_dir else {}
    remediation = _load_json(run_dir / "remediation-plan.json") if run_dir else {}
    capability = _load_json(run_dir / "capability-matrix.json") if run_dir else {}
    findings = _dict_items(audit.get("findings"))
    slices = _dict_items(remediation.get("slices"))
    missing = _missing_capabilities(capability, result)
    categories = Counter(
        str(finding["category"]) for finding in findings if isinstance(finding.get("category"), str)
    )
    severities = Counter(
        str(finding["severity"]) for finding in findings if isinstance(finding.get("severity"), str)
    )
    finding_count = len(findings)
    if not findings:
        finding_count = _summary_finding_count(result)
    context = {
        "name": repo_name,
        "doc_path": doc_path,
        "repo_path": result.get("repo_path"),
        "run_id": result.get("final_run_id") or result.get("run_id_prefix"),
        "run_dir": str(run_dir) if run_dir else "",
        "status": result.get("status"),
        "report_status": result.get("report_status"),
        "classification": result.get("classification"),
        "validation_errors": result.get("validation_errors") or [],
        "finding_count": finding_count,
        "findings_by_category": dict(sorted(categories.items())),
        "findings_by_severity": dict(sorted(severities.items())),
        "missing_capabilities": missing,
        "findings": findings,
        "slices": slices,
        "artifact_paths": _artifact_paths(run_dir),
        "result": result,
    }
    context["phase"] = _phase_for(context)
    return context


def _render_repo_doc(context: dict[str, Any]) -> str:
    lines = [
        f"# {context['name']}",
        "",
        f"- Repo path: `{context.get('repo_path')}`",
        f"- Run id: `{context.get('run_id')}`",
        f"- Run directory: `{context.get('run_dir') or 'unavailable'}`",
        f"- Phase candidate: `{context['phase']}`",
        f"- Status: `{context.get('status')}`",
        f"- Report status: `{context.get('report_status')}`",
        f"- Classification: `{context.get('classification')}`",
        f"- Findings: {context['finding_count']}",
        f"- Severity: {_dict_text(context['findings_by_severity'])}",
        f"- Categories: {_dict_text(context['findings_by_category'])}",
        f"- Missing capabilities: {_list_text(context['missing_capabilities'])}",
        "",
        "## Artifacts",
    ]
    artifact_paths = context["artifact_paths"]
    if artifact_paths:
        for label, path in artifact_paths.items():
            lines.append(f"- {label}: `{path}`")
    else:
        lines.append("- No run artifact directory was recorded.")

    validation_errors = context.get("validation_errors")
    if validation_errors:
        lines.extend(["", "## Validation Errors"])
        lines.extend(f"- {error}" for error in validation_errors)

    lines.extend(["", "## Top Findings"])
    top_findings = _top_findings(context["findings"])
    if not top_findings:
        lines.append("- none")
    for finding in top_findings:
        lines.append(_finding_line(finding))

    lines.extend(["", "## Remediation Clusters"])
    top_slices = _top_slices(context["slices"])
    if not top_slices:
        lines.append("- none")
    for slice_item in top_slices:
        lines.extend(_slice_lines(slice_item))
    lines.append("")
    return "\n".join(lines)


def _render_index(*, repo_docs: list[dict[str, Any]], phase_path: Path) -> str:
    phase_counts = Counter(str(repo["phase"]) for repo in repo_docs)
    lines = [
        "# QR Per-Repo Summaries",
        "",
        f"- Phase draft: `{phase_path}`",
        f"- Repo documents: {len(repo_docs)}",
        "",
        "## Phase Counts",
    ]
    for phase, count in sorted(phase_counts.items()):
        lines.append(f"- {phase}: {count}")
    lines.extend(["", "## Repos"])
    for repo in sorted(repo_docs, key=lambda item: str(item["name"])):
        lines.append(
            f"- [`{repo['name']}`]({repo['doc_path'].name}): "
            f"{repo['finding_count']} findings; phase `{repo['phase']}`"
        )
    lines.append("")
    return "\n".join(lines)


def _render_phase_draft(*, repo_docs: list[dict[str, Any]], index_path: Path) -> str:
    phase_repos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for repo in repo_docs:
        phase_repos[str(repo["phase"])].append(repo)
    lines = [
        "# QR Fleet Remediation Phases",
        "",
        f"- Per-repo index: `{index_path}`",
        "",
        (
            "Use these as planning phases only. QR remains advisory-only; "
            "execution should happen repo-by-repo with normal commits and verification."
        ),
        "",
    ]
    for phase in _phase_order():
        members = sorted(
            phase_repos.get(phase, []),
            key=lambda repo: (int(repo["finding_count"]), str(repo["name"])),
        )
        lines.extend([f"## {phase}", "", _phase_description(phase), ""])
        if not members:
            lines.append("- none")
        for repo in members:
            lines.append(
                f"- [`{repo['name']}`]({repo['doc_path'].name}): "
                f"{repo['finding_count']} findings; "
                f"missing {_list_text(repo['missing_capabilities'])}; "
                f"categories {_dict_text(repo['findings_by_category'])}"
            )
        lines.append("")
    return "\n".join(lines)


def _phase_for(context: dict[str, Any]) -> str:
    name = str(context["name"]).lower()
    missing = context["missing_capabilities"]
    categories = context["findings_by_category"]
    structural_count = sum(int(value) for key, value in categories.items() if key != "capability")
    finding_count = int(context["finding_count"])
    if (
        context.get("status") in {"error", "invalid-repo"}
        or context.get("report_status") == "rejected"
    ):
        return "Phase 0 - Control Plane And Branch Hygiene"
    if name.startswith("bbdse"):
        return "Phase 4 - BBDSE Cluster"
    if finding_count <= 5:
        return "Phase 1 - Quick Closers"
    if len(missing) >= 6 and structural_count <= 2:
        return "Phase 2 - Capability Baselines"
    if finding_count >= 20 and not missing:
        return "Phase 5 - Large Structural Apps"
    return "Phase 3 - Mixed Medium Repos"


def _phase_order() -> list[str]:
    return [
        "Phase 0 - Control Plane And Branch Hygiene",
        "Phase 1 - Quick Closers",
        "Phase 2 - Capability Baselines",
        "Phase 3 - Mixed Medium Repos",
        "Phase 4 - BBDSE Cluster",
        "Phase 5 - Large Structural Apps",
    ]


def _phase_description(phase: str) -> str:
    descriptions = {
        "Phase 0 - Control Plane And Branch Hygiene": (
            "Resolve invalid repos, rejected controller reports, dirty-state caveats, "
            "and branch hygiene before depending on these repos for remediation batches."
        ),
        "Phase 1 - Quick Closers": (
            "Small, bounded repos with zero to five findings; use these to validate the workflow."
        ),
        "Phase 2 - Capability Baselines": (
            "Repos dominated by missing formatter, lint, typecheck, test, build, dead-code, "
            "runtime, or pre-PR gates."
        ),
        "Phase 3 - Mixed Medium Repos": (
            "Moderate repos with capability and structural findings; plan one coherent batch per repo."
        ),
        "Phase 4 - BBDSE Cluster": (
            "BBDSE parent, children, and directory entries should be handled as a cluster."
        ),
        "Phase 5 - Large Structural Apps": (
            "High-volume structural apps with gates mostly present; plan cluster-oriented remediation."
        ),
    }
    return descriptions[phase]


def _artifact_paths(run_dir: Path | None) -> dict[str, str]:
    if run_dir is None:
        return {}
    return {
        "Quality audit": str(run_dir / "quality-audit.json"),
        "Remediation plan": str(run_dir / "remediation-plan.json"),
        "Agent handoff": str(run_dir / "agent-handoff.md"),
        "Resolution ledger": str(run_dir / "resolution-ledger.md"),
        "Code-quality scan": str(run_dir / "code-quality-scan.json"),
        "Run manifest": str(run_dir / "run-manifest.json"),
    }


def _top_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"blocker": 0, "warning": 1, "observation": 2}
    return sorted(
        findings,
        key=lambda item: (
            severity_rank.get(str(item.get("severity")), 9),
            -_int_value(item.get("score")),
            str(item.get("id")),
        ),
    )[:8]


def _top_slices(slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        slices,
        key=lambda item: (
            priority_rank.get(str(item.get("priority")), 9),
            -_int_value(item.get("score")),
            str(item.get("id")),
        ),
    )[:6]


def _finding_line(finding: dict[str, Any]) -> str:
    evidence = finding.get("evidence")
    evidence_items = evidence if isinstance(evidence, list) else []
    evidence_text = "; ".join(str(item) for item in evidence_items[:3]) or "no evidence listed"
    return (
        f"- `{finding.get('id')}` {finding.get('severity')} {finding.get('category')}: "
        f"{finding.get('summary')} Fix: {finding.get('recommended_fix')} "
        f"Evidence: {evidence_text}"
    )


def _slice_lines(slice_item: dict[str, Any]) -> list[str]:
    lines = [
        f"- `{slice_item.get('id')}` {slice_item.get('priority')} "
        f"score {slice_item.get('score')}: {slice_item.get('title')}"
    ]
    actions = _string_items(slice_item.get("actions"))
    gates = _string_items(slice_item.get("verification_gates"))
    if actions:
        lines.append(f"  Actions: {'; '.join(actions[:3])}")
    if gates:
        lines.append(f"  Verification: {'; '.join(gates[:2])}")
    return lines


def _repo_name(result: dict[str, Any]) -> str:
    value = result.get("repo_name")
    if isinstance(value, str) and value:
        return value
    repo_path = result.get("repo_path")
    if isinstance(repo_path, str) and repo_path:
        return Path(repo_path).name
    return "unknown-repo"


def _missing_capabilities(capability: dict[str, Any], result: dict[str, Any]) -> list[str]:
    missing = capability.get("missing")
    if isinstance(missing, list):
        return [
            item["id"]
            for item in missing
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
    return _string_items(result.get("missing_capabilities"))


def _summary_finding_count(result: dict[str, Any]) -> int:
    value = result.get("finding_counts")
    if isinstance(value, dict):
        return _int_value(value.get("total"))
    return 0


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict_items(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_items(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _path_or_none(value: object) -> Path | None:
    return Path(value) if isinstance(value, str) and value else None


def _dict_text(values: dict[str, Any]) -> str:
    if not values:
        return "none"
    return ", ".join(f"`{key}` {value}" for key, value in sorted(values.items()))


def _list_text(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _slug(value: object, *, fallback: str) -> str:
    text = value if isinstance(value, str) else fallback
    slug = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in text)
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or fallback


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0
