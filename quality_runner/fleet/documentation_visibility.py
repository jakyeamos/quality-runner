from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.fleet.documentation_visibility_support import (
    collect_diagrams,
    collect_executable_understanding,
    collect_newcomer_evidence,
    collect_orientation,
    collect_rationale_markers,
    collect_self_documentation,
    collect_semantic_naming,
    collect_traceability,
    lane,
    unique_evidence,
)
from quality_runner.fleet.legibility_evidence import collect_freshness_evidence

DEVELOPER_LEGIBILITY_SCHEMA = "quality-runner-developer-legibility/v1"


def assess_developer_legibility(
    root: Path,
    documents: dict[str, str],
    link_evidence: dict[str, Any],
    as_of: str,
) -> dict[str, Any]:
    """Assess whether a newcomer can understand and safely change a repository.

    Static evidence can establish a defined or enforced contract. Level 4 is
    reserved for a commit-bound newcomer exercise; comments or doc coverage
    alone never certify semantic understanding.
    """

    resolved_root = root.expanduser().resolve()
    orientation = collect_orientation(documents)
    traceability = collect_traceability(resolved_root, documents)
    diagrams = collect_diagrams(resolved_root, documents, link_evidence)
    naming = collect_semantic_naming(resolved_root)
    public_contracts = collect_self_documentation(resolved_root)
    rationale = collect_rationale_markers(resolved_root)
    executable = collect_executable_understanding(resolved_root, documents)
    freshness = collect_freshness_evidence(documents, as_of)
    newcomer = collect_newcomer_evidence(resolved_root)

    lanes = [
        _orientation_lane(orientation),
        _navigation_lane(documents, link_evidence, traceability),
        _architecture_lane(diagrams),
        _naming_lane(naming),
        _public_contract_lane(public_contracts),
        _rationale_lane(rationale, public_contracts),
        _executable_lane(executable),
        _freshness_lane(freshness),
    ]
    applicable = [item for item in lanes if item["applicable"]]
    if not applicable:
        score: int | None = None
        status = "not_applicable"
    else:
        score = round(sum(int(item["score"]) for item in applicable) / len(applicable))
        if not orientation["quick_start_present"] or (
            public_contracts["declaration_count"] and public_contracts["documented_ratio"] < 0.60
        ):
            score = min(score, 2)
        if newcomer["valid"] and score >= 3 and all(int(item["score"]) >= 2 for item in applicable):
            score = 4
        else:
            score = min(score, 3)
        status = (
            "blocked"
            if any(item["status"] == "blocked" for item in applicable)
            else "newcomer_verified"
            if score == 4
            else "enforced"
            if score == 3
            else "defined"
            if score == 2
            else "ad_hoc"
        )

    message = (
        "Developer legibility is newcomer-verified for the scanned commit."
        if score == 4
        else "Developer legibility is measured across orientation, navigation, architecture, naming, contracts, rationale, executable examples, and freshness."
        if score is not None
        else "No documentation or source surface was found in the bounded audit."
    )
    evidence = unique_evidence(
        [item for item_lane in applicable for item in item_lane.get("evidence", [])]
    )[:16]
    return {
        "schema": DEVELOPER_LEGIBILITY_SCHEMA,
        "score": score,
        "status": status,
        "message": message,
        "evidence": evidence or [{"path": ".", "detail": message}],
        "lanes": lanes,
        "orientation": orientation,
        "traceability": traceability,
        "diagrams": diagrams,
        "semantic_naming": naming,
        "public_contracts": public_contracts,
        "rationale_comments": rationale,
        "executable_understanding": executable,
        "freshness": freshness,
        "newcomer_evidence": newcomer,
        "maturity_scale": {
            "0": "unknown",
            "1": "ad hoc",
            "2": "defined",
            "3": "enforced",
            "4": "newcomer verified",
        },
        "limitations": [
            "Static naming checks identify vague public names but cannot prove domain semantics.",
            "Public-contract coverage measures doc comments and docstrings near declarations, not prose quality.",
            "Rationale checks target unexplained suppressions and debt markers; they do not reward comment volume.",
            "Architecture and source links prove checkout-local resolution, not runtime correctness.",
        ],
    }


def assess_documentation_visibility(
    root: Path, documents: dict[str, str], link_evidence: dict[str, Any], as_of: str
) -> dict[str, Any]:
    """Compatibility entry point for callers of the earlier five-lane prototype."""
    return assess_developer_legibility(root, documents, link_evidence, as_of)


def _orientation_lane(data: dict[str, Any]) -> dict[str, Any]:
    score = sum(
        bool(data[key])
        for key in ("purpose_present", "quick_start_present", "verification_present", "map_present")
    )
    score = 3 if score == 4 else 2 if score >= 2 else 1
    return lane(
        "orientation",
        "Orientation and quick start",
        True,
        score,
        _status(score),
        [
            {
                "path": data["readme_path"] or ".",
                "detail": f"purpose={data['purpose_present']}; quick_start={data['quick_start_present']}; verification={data['verification_present']}; map={data['map_present']}",
            }
        ],
    )


def _navigation_lane(
    documents: dict[str, str], links: dict[str, Any], trace: dict[str, Any]
) -> dict[str, Any]:
    if not documents:
        return lane(
            "navigation_traceability",
            "Navigation and traceability",
            False,
            None,
            "not_applicable",
            [],
        )
    if links.get("invalid_count", 0) or trace["invalid_count"]:
        score, status = 1, "blocked"
    elif trace["valid_count"] and links.get("links"):
        score, status = 3, "enforced"
    elif links.get("links"):
        score, status = 2, "defined"
    else:
        score, status = 1, "ad_hoc"
    return lane(
        "navigation_traceability",
        "Navigation and traceability",
        True,
        score,
        status,
        [
            {
                "path": "documentation",
                "detail": f"invalid_links={links.get('invalid_count', 0)}; valid_source_anchors={trace['valid_count']}; floating_source_anchors={trace['floating_count']}",
            }
        ],
    )


def _architecture_lane(data: dict[str, Any]) -> dict[str, Any]:
    if not data["applicable"]:
        return lane(
            "architecture_visibility", "Architecture visibility", False, None, "not_applicable", []
        )
    score = (
        3
        if data["diagram_count"] and (data["linked_count"] or data["inline_count"])
        else 2
        if data["diagram_count"]
        else 1
    )
    return lane(
        "architecture_visibility",
        "Architecture visibility",
        True,
        score,
        _status(score),
        [
            {
                "path": ".",
                "detail": f"diagrams={data['diagram_count']}; linked={data['linked_count']}; infrastructure_markers={len(data['infrastructure_markers'])}",
            }
        ],
    )


def _naming_lane(data: dict[str, Any]) -> dict[str, Any]:
    if not data["declaration_count"]:
        return lane("semantic_naming", "Semantic naming", False, None, "not_applicable", [])
    ratio = data["vague_name_count"] / data["declaration_count"]
    score = 3 if not data["vague_name_count"] else 2 if ratio <= 0.10 else 1
    return lane(
        "semantic_naming",
        "Semantic naming",
        True,
        score,
        _status(score),
        [
            {
                "path": item["path"],
                "detail": f"vague public name {item['name']} near line {item['line']}",
            }
            for item in data["vague_examples"][:8]
        ]
        or [
            {
                "path": "source",
                "detail": f"no known vague names across {data['declaration_count']} public declarations; semantic review still required",
            }
        ],
    )


def _public_contract_lane(data: dict[str, Any]) -> dict[str, Any]:
    if not data["declaration_count"]:
        return lane(
            "public_contracts", "Public contracts and docstrings", False, None, "not_applicable", []
        )
    ratio = float(data["documented_ratio"])
    score = 3 if ratio >= 0.90 else 2 if ratio >= 0.60 else 1
    return lane(
        "public_contracts",
        "Public contracts and docstrings",
        True,
        score,
        _status(score),
        [
            {
                "path": "source",
                "detail": f"{data['documented_count']}/{data['declaration_count']} public declarations have a nearby doc marker ({ratio:.0%})",
            },
            *[
                {
                    "path": item["path"],
                    "detail": f"undocumented public declaration {item['name']} near line {item['line']}",
                }
                for item in data["undocumented_examples"][:6]
            ],
        ],
    )


def _rationale_lane(data: dict[str, Any], contracts: dict[str, Any]) -> dict[str, Any]:
    applicable = bool(data["marker_count"] or contracts["declaration_count"])
    if not applicable:
        return lane(
            "rationale_invariants",
            "Rationale and invariant comments",
            False,
            None,
            "not_applicable",
            [],
        )
    score = 3 if not data["unexplained_count"] else 2 if data["unexplained_count"] <= 2 else 1
    return lane(
        "rationale_invariants",
        "Rationale and invariant comments",
        True,
        score,
        _status(score),
        [
            {
                "path": item["path"],
                "detail": f"suppression or debt marker near line {item['line']} lacks a reason, issue, or removal condition",
            }
            for item in data["unexplained_examples"][:8]
        ]
        or [
            {
                "path": "source",
                "detail": "no unexplained suppression or debt markers found; absence of comments is not rewarded",
            }
        ],
    )


def _executable_lane(data: dict[str, Any]) -> dict[str, Any]:
    score = (
        3
        if data["test_surface_present"] and data["documented_command_present"]
        else 2
        if data["test_surface_present"] or data["documented_command_present"]
        else 1
    )
    return lane(
        "executable_understanding",
        "Executable understanding",
        True,
        score,
        _status(score),
        [
            {
                "path": data["test_paths"][0] if data["test_paths"] else "documentation",
                "detail": f"test_surface={data['test_surface_present']}; documented_command={data['documented_command_present']}",
            }
        ],
    )


def _freshness_lane(data: dict[str, Any]) -> dict[str, Any]:
    status = data.get("status")
    score = 3 if status == "known" else 2 if status in {"unknown", "stale"} else 1
    return lane(
        "ownership_freshness",
        "Ownership and freshness",
        True,
        score,
        "stale" if status == "stale" else _status(score),
        [
            {"path": path, "detail": "bounded review marker"}
            for path in data.get("reviewed_paths", [])[:8]
        ]
        or [{"path": "documentation", "detail": "no fresh bounded review marker was found"}],
    )


def _status(score: int) -> str:
    return "enforced" if score == 3 else "defined" if score == 2 else "ad_hoc"
